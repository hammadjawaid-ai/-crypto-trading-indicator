"""💠 Sure Shot Trader 2 — the deep-analysis desk (9 agents).

A bigger, deeper version of the Sure Shot Trader pipeline. Instead of one
deterministic validator, every candidate is reviewed by SEVEN specialist
analysts, then a strategist forces cross-analyst consensus, and a risk
manager applies portfolio-level checks before anything is shown:

    ANALYSTS (each returns score 0-100 + verdict + reasons)
      1. 🛰️ Scout       — proven-system stack (CONVERGENCE/SURE SHOT/ELITE)
      2. 📐 Chartist    — candle-pattern lanes + support/resistance room
      3. 📊 Quant       — backtested tier priors, lane-count edge, R:R
      4. 🌍 Macro       — regime fit, BTC fast trend, shift state
      5. 🕒 Timeframes  — 15m/1h/4h alignment (multi_tf)
      6. 📰 News        — VADER sentiment on crypto headlines + coin hits
      7. 💹 Derivatives — funding/OI velocity lane

    8. 🧩 Strategist    — weighted consensus; requires 4+ analysts backing
                          and no hard veto (any analyst <= 20 kills it)
    9. 🛡️ Risk manager  — dedupes vs open book, caps picks, sizes by
                          conviction, flags concentration

    Optional deep verdict: the top finalists go to the most capable
    Anthropic model (Fable 5 by default) which reads the FULL analyst
    report and adjudicates TRADE/WATCH/SKIP. Fail-open without a key.

Like sureshot_agents, this module does NOT scan the market itself — app.py
passes in the unified scan it already computed. Pure logic + small cached
kline fetches for S/R analysis on the top candidates only.
"""
from __future__ import annotations

import json
import time

import requests

import config
import binance_client

try:
    import multi_tf
except Exception:
    multi_tf = None

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER = SentimentIntensityAnalyzer()
except Exception:
    _VADER = None


# Analyst weights — sum to 1.0. Scout + Chartist lead (proven systems and
# price structure are the strongest deterministic evidence we have).
_ANALYST_WEIGHTS = {
    "scout":      0.18,
    "chartist":   0.18,
    "quant":      0.14,
    "macro":      0.14,
    "timeframes": 0.14,
    "news":       0.12,
    "derivs":     0.10,
}

# Consensus requirements (strategist)
_BACKING_SCORE = 60      # an analyst "backs" the trade at score >= this
_MIN_BACKING = 4         # need at least 4 of 7 analysts backing
_VETO_SCORE = 20         # any analyst at/below this hard-kills the pick

# Quality tiers on final conviction
_TIER_SURE = 72
_TIER_OK = 58


# ---------------------------------------------------------------------------
# Small cached 1h kline fetch for S/R analysis (top candidates only)
# ---------------------------------------------------------------------------
_SR_CACHE: dict = {}
_SR_TTL = 180


def _sr_klines(symbol: str):
    now = time.time()
    hit = _SR_CACHE.get(symbol)
    if hit and (now - hit["ts"]) < _SR_TTL:
        return hit["df"]
    try:
        df = binance_client.get_klines(symbol, "1h", limit=120)
    except Exception:
        df = None
    _SR_CACHE[symbol] = {"ts": now, "df": df}
    return df


def _clip(x: float) -> float:
    return float(max(0.0, min(100.0, x)))


# ===========================================================================
# ANALYST 1 — 🛰️ Scout (proven-system stack)
# ===========================================================================
def analyst_scout(cand: dict) -> dict:
    proven = cand.get("proven_systems") or []
    reasons = []
    score = 40.0
    if "CONVERGENCE" in proven:
        score += 22
        reasons.append("CONVERGENCE meta-filter (+6.8pp backtested)")
    if "SURE SHOT" in proven:
        score += 16
        reasons.append("SURE SHOT strict meta-filter")
    if "ELITE" in proven:
        score += 12
        reasons.append("ELITE composite confirms side")
    if not proven:
        reasons.append("no proven-system confirmation (lane-only)")
    return {"name": "scout", "score": _clip(score),
            "reasons": reasons}


# ===========================================================================
# ANALYST 2 — 📐 Chartist (patterns + support/resistance room)
# ===========================================================================
def analyst_chartist(cand: dict) -> dict:
    lanes = cand.get("lanes_fired") or {}
    side = (cand.get("side") or "").upper()
    reasons = []
    pattern_lanes = ("pattern_scout", "reversal_app", "breakout_coil",
                     "velocity_burst", "recovery", "early_momentum")
    fired = [(ln, float(lanes.get(ln) or 0)) for ln in pattern_lanes
             if float(lanes.get(ln) or 0) >= 55]
    if fired:
        avg = sum(v for _, v in fired) / len(fired)
        score = 35 + 0.40 * avg
        reasons.append(
            f"{len(fired)} pattern lane(s) firing, avg {avg:.0f} ("
            + ", ".join(ln for ln, _ in fired[:3]) + ")")
    else:
        score = 35.0
        reasons.append("no pattern lanes firing >= 55")

    # Support / resistance room — fetch 1h klines (cached) and measure
    # distance to the recent swing high/low (excluding the live candle).
    df = _sr_klines(cand.get("symbol"))
    if df is not None and len(df) >= 60:
        try:
            price = float(df["close"].iloc[-1])
            swing_high = float(df["high"].iloc[-53:-3].max())
            swing_low = float(df["low"].iloc[-53:-3].min())
            if price > 0:
                room_up = (swing_high - price) / price
                room_dn = (price - swing_low) / price
                if side == "LONG":
                    if room_up >= 0.02:
                        score += 12
                        reasons.append(
                            f"room to swing high +{room_up*100:.1f}%")
                    elif 0 <= room_up < 0.005:
                        score -= 10
                        reasons.append("right under resistance")
                    if 0 <= room_dn <= 0.03:
                        score += 6
                        reasons.append(
                            f"support {room_dn*100:.1f}% below")
                elif side == "SHORT":
                    if room_dn >= 0.02:
                        score += 12
                        reasons.append(
                            f"room to swing low -{room_dn*100:.1f}%")
                    elif 0 <= room_dn < 0.005:
                        score -= 10
                        reasons.append("right above support")
                    if 0 <= room_up <= 0.03:
                        score += 6
                        reasons.append(
                            f"resistance {room_up*100:.1f}% above")
        except Exception:
            pass
    return {"name": "chartist", "score": _clip(score),
            "reasons": reasons}


# ===========================================================================
# ANALYST 3 — 📊 Quant (backtested priors + stats)
# ===========================================================================
def analyst_quant(cand: dict) -> dict:
    reasons = []
    tier = cand.get("tier") or "STANDARD"
    # Priors anchored on our walk-forward backtests (3+ lane confluence
    # won 53-66%; tier tracks score+strong-lane count).
    score = {"MAX": 64.0, "HIGH": 58.0,
             "STRONG": 54.0, "STANDARD": 50.0}.get(tier, 50.0)
    reasons.append(f"tier {tier} prior")
    n_lanes = len(cand.get("active_lanes") or [])
    if n_lanes >= 3:
        score += 12
        reasons.append(f"{n_lanes} lanes — backtested confluence edge "
                       "(53-66% win band)")
    plan = cand.get("trade_plan") or {}
    rr = float(plan.get("rr") or cand.get("rr") or 0)
    if rr >= 2.0:
        score += 10
        reasons.append(f"R:R {rr:.2f} excellent")
    elif rr >= 1.5:
        score += 5
        reasons.append(f"R:R {rr:.2f} good")
    elif 0 < rr < 1.2:
        score -= 10
        reasons.append(f"R:R {rr:.2f} poor")
    vb = float((cand.get("lanes_fired") or {}).get(
        "velocity_burst") or 0)
    if vb >= 90:
        score += 6
        reasons.append(f"velocity burst {vb:.0f} — proven 90+ band "
                       "(+0.127R expectancy)")
    return {"name": "quant", "score": _clip(score), "reasons": reasons}


# ===========================================================================
# ANALYST 4 — 🌍 Macro (regime + BTC fast trend)
# ===========================================================================
def analyst_macro(cand: dict, regime_info: dict) -> dict:
    reasons = []
    score = 50.0
    side = (cand.get("side") or "").upper()
    regime = (regime_info or {}).get("regime", "")
    conf = float((regime_info or {}).get("confidence") or 0)
    proven_n = cand.get("proven_count", 0)
    aligned = ((regime == "BULL" and side == "LONG")
               or (regime == "BEAR" and side == "SHORT"))
    if aligned:
        score += min(20, conf / 4)
        reasons.append(f"regime {regime} backs {side} ({conf:.0f}%)")
    elif regime in ("BULL", "BEAR"):
        pen = 4 if proven_n >= 2 else 12
        score -= pen
        reasons.append(f"counter-{regime} (-{pen})")
    else:
        reasons.append(f"regime {regime or 'UNKNOWN'} — neutral")
    fast = ((regime_info or {}).get("components") or {}).get(
        "fast") or {}
    fs = float(fast.get("score") or 50)
    if side == "LONG":
        if fs >= 58:
            score += 8
            reasons.append(f"BTC 1h fast trend bullish ({fs:.0f})")
        elif fs <= 42:
            score -= 8
            reasons.append(f"BTC 1h fast trend bearish ({fs:.0f})")
    else:
        if fs <= 42:
            score += 8
            reasons.append(f"BTC 1h fast trend bearish ({fs:.0f})")
        elif fs >= 58:
            score -= 8
            reasons.append(f"BTC 1h fast trend bullish ({fs:.0f})")
    if (regime_info or {}).get("is_shifting"):
        score -= 4
        reasons.append("regime SHIFTING — caution")
    return {"name": "macro", "score": _clip(score), "reasons": reasons}


# ===========================================================================
# ANALYST 5 — 🕒 Timeframes (15m/1h/4h alignment)
# ===========================================================================
def analyst_timeframes(cand: dict) -> dict:
    aligned = cand.get("_mtf_aligned")
    against = int(cand.get("_mtf_against") or 0)
    summary = cand.get("_mtf_summary") or ""
    if aligned is None:
        return {"name": "timeframes", "score": 50.0,
                "reasons": ["no multi-TF data"]}
    aligned = int(aligned)
    if aligned >= 3:
        score, note = 85.0, "3/3 timeframes aligned"
    elif aligned == 2:
        score, note = 70.0, "2/3 timeframes aligned"
    elif aligned == 1:
        score, note = 55.0, "1/3 timeframe aligned"
    elif against >= 2:
        score, note = 22.0, f"{against} timeframes AGAINST"
    else:
        score, note = 40.0, "no timeframe aligned"
    reasons = [note] + ([summary] if summary else [])
    return {"name": "timeframes", "score": score, "reasons": reasons}


# ===========================================================================
# ANALYST 6 — 📰 News (VADER sentiment + coin mentions)
# ===========================================================================
def analyst_news(cand: dict, headlines: list[str]) -> dict:
    reasons = []
    score = 50.0
    side = (cand.get("side") or "").upper()
    sign = 1 if side == "LONG" else -1
    if _VADER is None or not headlines:
        return {"name": "news", "score": 50.0,
                "reasons": ["no news data / sentiment engine"]}
    # Market-wide mood across recent crypto headlines
    compounds = []
    for h in headlines[:30]:
        try:
            compounds.append(_VADER.polarity_scores(str(h))["compound"])
        except Exception:
            continue
    if compounds:
        mood = sum(compounds) / len(compounds)   # -1..+1
        score += sign * mood * 24                # up to ±~12 typical
        reasons.append(
            f"market news mood {mood:+.2f} across "
            f"{len(compounds)} headlines")
    # Coin-specific mentions (only for bases long enough to be unambiguous)
    base = str(cand.get("base") or "")
    if len(base) >= 3:
        hits = [h for h in headlines
                if base.lower() in str(h).lower()]
        if hits:
            coin_comp = [
                _VADER.polarity_scores(str(h))["compound"]
                for h in hits[:5]]
            coin_mood = sum(coin_comp) / len(coin_comp)
            score += sign * coin_mood * 36       # up to ±~18
            reasons.append(
                f"{len(hits)} headline(s) mention {base}, "
                f"sentiment {coin_mood:+.2f}")
            if sign * coin_mood < -0.3:
                reasons.append("⚠ coin news CONTRADICTS trade direction")
    return {"name": "news", "score": _clip(score), "reasons": reasons}


# ===========================================================================
# ANALYST 7 — 💹 Derivatives (funding/OI velocity)
# ===========================================================================
def analyst_derivs(cand: dict) -> dict:
    dv = float((cand.get("lanes_fired") or {}).get(
        "deriv_velocity") or 0)
    if dv >= 55:
        score = 50 + min(22, (dv - 55) / 2)
        reasons = [f"funding/OI velocity supports ({dv:.0f})"]
    else:
        score = 50.0
        reasons = ["derivatives neutral / no signal"]
    return {"name": "derivs", "score": _clip(score), "reasons": reasons}


# ===========================================================================
# AGENT 8 — 🧩 Strategist (weighted consensus)
# ===========================================================================
def strategist_consensus(reports: dict) -> dict:
    """Blend the 7 analyst scores into one conviction + decide consensus.

    reports: {"scout": {...}, "chartist": {...}, ...}
    """
    conviction = 0.0
    for name, w in _ANALYST_WEIGHTS.items():
        conviction += w * float(reports.get(name, {}).get("score", 50))
    backing = [n for n, r in reports.items()
               if float(r.get("score", 0)) >= _BACKING_SCORE]
    vetoes = [n for n, r in reports.items()
              if float(r.get("score", 100)) <= _VETO_SCORE]
    passed = (len(backing) >= _MIN_BACKING) and not vetoes
    if conviction >= _TIER_SURE:
        quality = "SURE SHOT"
    elif conviction >= _TIER_OK:
        quality = "OK"
    else:
        quality = "WEAK"
        passed = False
    return {
        "conviction": round(conviction, 1),
        "backing": backing,
        "backing_n": len(backing),
        "vetoes": vetoes,
        "passed": passed,
        "quality": quality,
    }


# ===========================================================================
# Deep LLM verdict (Fable 5 by default) — finalists only
# ===========================================================================
def _deep_verdict(cand: dict, reports: dict, consensus: dict,
                 regime_info: dict) -> dict | None:
    api_key = getattr(config, "ANTHROPIC_API_KEY", "") or ""
    if not api_key:
        return None
    model = getattr(config, "ANTHROPIC_MODEL_DEEP", "claude-fable-5")
    sym = cand.get("base", cand.get("symbol", "?"))
    side = (cand.get("side") or "").upper()
    plan = cand.get("trade_plan") or {}
    analyst_lines = []
    for name in _ANALYST_WEIGHTS:
        r = reports.get(name, {})
        analyst_lines.append(
            f"  {name:<11} {float(r.get('score', 0)):>5.0f}  "
            + "; ".join(r.get("reasons", [])[:3]))
    prompt = f"""You are the head of a crypto trading desk. Seven analyst \
agents reviewed this proposed trade and a strategist computed consensus. \
Your job: adjudicate. Be skeptical — approve TRADE only when the \
evidence stack is genuinely coherent; if any analyst raises a \
contradiction the others can't outweigh, say WATCH or SKIP.

TRADE: {sym} {side}
  entry {plan.get('entry')}  stop {plan.get('stop')}  \
tp1 {plan.get('tp1')}  R:R {float(plan.get('rr') or 0):.2f}

ANALYST DESK (score 0-100, reasons):
{chr(10).join(analyst_lines)}

STRATEGIST: conviction {consensus['conviction']:.0f}, \
{consensus['backing_n']}/7 backing ({', '.join(consensus['backing'])})\
{', VETO: ' + ', '.join(consensus['vetoes']) if consensus['vetoes'] else ''}

REGIME: {(regime_info or {}).get('regime', '?')} — \
{(regime_info or {}).get('summary', '')[:200]}

Reply ONLY a compact JSON object:
{{"verdict": "TRADE" | "WATCH" | "SKIP", "confidence": 0-100, \
"reason": "one concise sentence naming the deciding factor"}}"""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 250,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return {"verdict": "ERROR", "confidence": 0,
                    "reason": f"API {resp.status_code}"}
        data = resp.json()
        text = "".join(
            b.get("text", "") for b in data.get("content", [])
            if b.get("type") == "text").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)
        verdict = str(parsed.get("verdict", "WATCH")).upper()
        if verdict not in ("TRADE", "WATCH", "SKIP"):
            verdict = "WATCH"
        return {"verdict": verdict,
                "confidence": int(parsed.get("confidence", 0) or 0),
                "reason": str(parsed.get("reason", ""))[:240],
                "model": model}
    except Exception as exc:
        return {"verdict": "ERROR", "confidence": 0,
                "reason": str(exc)[:120]}


# ===========================================================================
# AGENT 9 — 🛡️ Risk manager
# ===========================================================================
def risk_manager(finalists: list[dict], open_positions: list[dict],
                max_picks: int = 6) -> list[dict]:
    open_syms = {p.get("symbol") for p in (open_positions or [])}
    out = []
    sides = [(p.get("side") or "").upper()
             for p in (open_positions or [])]
    same_side_note = (len(sides) >= 4 and len(set(sides)) == 1)
    for c in finalists:
        c = dict(c)
        c["already_open"] = c.get("symbol") in open_syms
        c["strength_factor"] = max(
            0.5, min(1.0, float(c.get("conviction") or 0) / 100.0))
        if same_side_note:
            c.setdefault("risk_notes", []).append(
                f"⚠ book already {len(sides)} positions all "
                f"{sides[0]} — concentration risk")
        out.append(c)
        if len(out) >= max_picks:
            break
    return out


# ===========================================================================
# ORCHESTRATOR
# ===========================================================================
def run_pipeline2(scan_picks: list[dict],
                 regime_info: dict,
                 convergence_syms: set,
                 sure_shot_syms: set,
                 elite_lookup: dict,
                 news_headlines: list[str] | None = None,
                 open_positions: list[dict] | None = None,
                 llm_top_n: int = 3,
                 use_llm: bool = True,
                 max_picks: int = 6) -> dict:
    """Run the full 9-agent desk. Returns picks with per-analyst reports."""
    news_headlines = news_headlines or []

    # ---- Gather + proven tagging (scout's raw material) ----
    candidates = []
    for p in scan_picks or []:
        sym = p.get("symbol")
        if not sym:
            continue
        side = (p.get("side") or "").upper()
        proven = []
        if sym in (convergence_syms or set()):
            proven.append("CONVERGENCE")
        if sym in (sure_shot_syms or set()):
            proven.append("SURE SHOT")
        e = (elite_lookup or {}).get(sym)
        if e and (e.get("side") or "").upper() == side:
            proven.append("ELITE")
        c = dict(p)
        c["proven_systems"] = proven
        c["proven_count"] = len(proven)
        candidates.append(c)
    candidates.sort(
        key=lambda c: (c.get("proven_count", 0),
                       float(c.get("score") or 0)),
        reverse=True)

    # ---- Enrich top candidates with multi-TF (cached, 3 TFs each) ----
    deep_pool = candidates[:12]
    if multi_tf is not None:
        for c in deep_pool:
            if c.get("_mtf_aligned") is not None:
                continue
            try:
                r = multi_tf.get_multi_tf_alignment(
                    c.get("symbol"), (c.get("side") or "").upper())
                c["_mtf_aligned"] = r.get("aligned", 0)
                c["_mtf_against"] = r.get("against", 0)
                c["_mtf_summary"] = r.get("summary", "")
            except Exception:
                c["_mtf_aligned"] = 0
                c["_mtf_against"] = 0

    # ---- Run the 7-analyst desk on the deep pool ----
    analyzed = []
    for c in deep_pool:
        reports = {
            "scout":      analyst_scout(c),
            "chartist":   analyst_chartist(c),
            "quant":      analyst_quant(c),
            "macro":      analyst_macro(c, regime_info),
            "timeframes": analyst_timeframes(c),
            "news":       analyst_news(c, news_headlines),
            "derivs":     analyst_derivs(c),
        }
        consensus = strategist_consensus(reports)
        c["analyst_reports"] = reports
        c["conviction"] = consensus["conviction"]
        c["backing"] = consensus["backing"]
        c["backing_n"] = consensus["backing_n"]
        c["vetoes"] = consensus["vetoes"]
        c["quality"] = consensus["quality"]
        c["passed"] = consensus["passed"]
        analyzed.append(c)

    survivors = [c for c in analyzed if c["passed"]]
    survivors.sort(key=lambda c: c["conviction"], reverse=True)

    # ---- Deep LLM verdict (Fable 5) on the top finalists ----
    api_key = getattr(config, "ANTHROPIC_API_KEY", "") or ""
    llm_active = use_llm and bool(api_key)
    llm_calls = 0
    for i, c in enumerate(survivors):
        c["llm"] = None
        if llm_active and i < llm_top_n:
            v = _deep_verdict(c, c["analyst_reports"],
                             {"conviction": c["conviction"],
                              "backing": c["backing"],
                              "backing_n": c["backing_n"],
                              "vetoes": c["vetoes"]},
                             regime_info)
            c["llm"] = v
            llm_calls += 1 if v is not None else 0
            if v and v.get("verdict") in ("WATCH", "SKIP"):
                c["passed"] = False
    final_pool = [c for c in survivors if c.get("passed")]

    # ---- Risk manager ----
    sure_shots = risk_manager(final_pool, open_positions or [],
                             max_picks=max_picks)

    return {
        "candidates": candidates,
        "analyzed": analyzed,
        "sure_shots": sure_shots,
        "stats": {
            "gathered": len(candidates),
            "analyzed": len(analyzed),
            "consensus_passed": len(survivors),
            "sure_shots": len(sure_shots),
            "llm_active": llm_active,
            "llm_calls": llm_calls,
            "deep_model": getattr(config, "ANTHROPIC_MODEL_DEEP",
                                  "claude-fable-5"),
        },
    }

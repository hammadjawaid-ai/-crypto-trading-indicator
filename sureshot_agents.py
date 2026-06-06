"""🎯 Sure Shot Trader — 3-agent pipeline.

A deterministic-first, LLM-validated pipeline that turns the raw signal
universe into a tiny set of highest-conviction "sure shot" trades.

    Agent 1 — GATHER     collect every candidate the system found and
                          tag which PROVEN systems confirm it
                          (CONVERGENCE / SURE SHOT / ELITE).
    Agent 2 — VALIDATE   score each candidate deterministically
                          (proven-system stack + multi-TF alignment +
                          regime + R:R), keep the top few, then get a
                          final LLM TRADE/WATCH/SKIP verdict on those
                          survivors (incorporating news + BTC context).
    Agent 3 — PRESENT    rank the TRADE-verdict picks into the final
                          sure-shot list shown on the cards.

Design notes
------------
- This module does NOT scan the market itself. app.py already runs the
  full scan (scan_unified + convergence + sure-shot + ELITE) once per
  render; we reuse that work and pass it in. No double-scanning.
- The LLM call is OPTIONAL. With no ANTHROPIC_API_KEY the validator runs
  deterministic-only and every survivor is treated as TRADE-eligible
  (the deterministic bar is already strict). With a key, the LLM is a
  second opinion on only the top 2-3 — cheap (~$5-15/mo).
- LLM calls go over plain HTTP (requests) to avoid an SDK dependency.
"""
from __future__ import annotations

import json
import requests

import config

try:
    import multi_tf
except Exception:
    multi_tf = None


# ===========================================================================
# AGENT 1 — GATHER
# ===========================================================================
def agent1_gather(scan_picks: list[dict],
                 convergence_syms: set,
                 sure_shot_syms: set,
                 elite_lookup: dict) -> list[dict]:
    """Collect candidates and tag proven-system confirmations.

    scan_picks: list of pick dicts (each has symbol/base/side/score/
        tier/active_lanes/trade_plan/confidence). This is the unified
        scan result app.py already computed.
    Returns a list of candidate dicts enriched with:
        proven_systems: list[str]  e.g. ['CONVERGENCE', 'ELITE']
        proven_count: int
    """
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
        cand = dict(p)
        cand["proven_systems"] = proven
        cand["proven_count"] = len(proven)
        candidates.append(cand)
    # Sort by proven_count then score so the strongest bubble up
    candidates.sort(
        key=lambda c: (c.get("proven_count", 0),
                       float(c.get("score") or 0)),
        reverse=True)
    return candidates


# ===========================================================================
# AGENT 2 — VALIDATE
# ===========================================================================
def _deterministic_conviction(cand: dict,
                             regime_info: dict) -> tuple[float, list[str]]:
    """Compute a 0-100 conviction score + reasons from proven systems,
    multi-TF alignment, regime, and R:R. No LLM, no network."""
    reasons = []
    sym = cand.get("symbol")
    side = (cand.get("side") or "").upper()
    base_score = float(cand.get("score") or 0)
    conviction = base_score * 0.5   # 0-50 from raw composite

    # Proven systems — the biggest lever (these have backtested edge)
    pc = cand.get("proven_count", 0)
    proven = cand.get("proven_systems", [])
    if "CONVERGENCE" in proven:
        conviction += 16
        reasons.append("CONVERGENCE (+6.8pp backtested edge)")
    if "SURE SHOT" in proven:
        conviction += 12
        reasons.append("SURE SHOT meta-filter")
    if "ELITE" in proven:
        conviction += 8
        reasons.append("ELITE composite confirms side")

    # Multi-TF alignment
    mtf_aligned = int(cand.get("_mtf_aligned") or 0)
    mtf_against = int(cand.get("_mtf_against") or 0)
    if mtf_aligned >= 3:
        conviction += 12
        reasons.append("3/3 timeframes aligned (15m/1h/4h)")
    elif mtf_aligned == 2:
        conviction += 7
        reasons.append("2/3 timeframes aligned")
    elif mtf_aligned == 1:
        conviction += 2
        reasons.append("1/3 timeframe aligned")
    if mtf_against >= 2:
        conviction -= 10
        reasons.append(f"⚠ {mtf_against} timeframes against")

    # Regime alignment
    regime = (regime_info or {}).get("regime", "")
    reg_conf = float((regime_info or {}).get("confidence") or 0)
    if regime == "BULL" and side == "LONG":
        conviction += min(8, reg_conf / 12)
        reasons.append(f"regime BULL backs LONG ({reg_conf:.0f}%)")
    elif regime == "BEAR" and side == "SHORT":
        conviction += min(8, reg_conf / 12)
        reasons.append(f"regime BEAR backs SHORT ({reg_conf:.0f}%)")
    elif regime in ("BULL", "BEAR"):
        # counter-regime — small penalty unless very high proven count
        if pc < 2:
            conviction -= 5
            reasons.append(f"counter-{regime} (no strong confirm)")

    # R:R from the plan
    plan = cand.get("trade_plan") or {}
    rr = float(plan.get("rr") or cand.get("rr") or 0)
    if rr >= 2.0:
        conviction += 5
        reasons.append(f"R:R {rr:.2f} (excellent)")
    elif rr >= 1.5:
        conviction += 2
        reasons.append(f"R:R {rr:.2f} (good)")
    elif 0 < rr < 1.2:
        conviction -= 6
        reasons.append(f"R:R {rr:.2f} (poor)")

    conviction = max(0.0, min(100.0, conviction))
    return round(conviction, 1), reasons


def _llm_verdict(cand: dict,
                regime_info: dict,
                news_headlines: list[str],
                conviction: float,
                det_reasons: list[str]) -> dict | None:
    """Get a TRADE/WATCH/SKIP verdict from the Anthropic API.

    Returns None when no API key is set (deterministic-only mode) or on
    any error (fail-open: deterministic decision stands).
    """
    api_key = getattr(config, "ANTHROPIC_API_KEY", "") or ""
    if not api_key:
        return None

    sym = cand.get("base", cand.get("symbol", "?"))
    side = (cand.get("side") or "").upper()
    plan = cand.get("trade_plan") or {}
    entry = plan.get("entry") or cand.get("entry_low") or 0
    stop = plan.get("stop") or cand.get("stop") or 0
    tp1 = plan.get("tp1") or cand.get("target") or 0
    rr = float(plan.get("rr") or cand.get("rr") or 0)
    lanes = ", ".join(cand.get("active_lanes") or [])
    proven = ", ".join(cand.get("proven_systems") or []) or "none"
    regime = (regime_info or {}).get("regime", "?")
    reg_summary = (regime_info or {}).get("summary", "")
    headlines = "\n".join(f"- {h}" for h in (news_headlines or [])[:8]) \
        or "- (none available)"

    prompt = f"""You are a disciplined crypto futures risk manager. A \
multi-system scanner proposes this trade. Decide if it is a genuine \
high-conviction "sure shot" worth real capital, or if something looks \
off. Be skeptical — default to WATCH unless the setup is clean.

PROPOSED TRADE
  Symbol: {sym}   Direction: {side}
  Entry: {entry}   Stop: {stop}   Target: {tp1}   R:R: {rr:.2f}
  Scanner conviction (0-100): {conviction:.0f}
  Proven systems confirming: {proven}
  Signal lanes firing: {lanes}
  Deterministic reasons: {"; ".join(det_reasons)}

MARKET CONTEXT
  Regime: {regime} — {reg_summary}

RECENT NEWS HEADLINES (crypto + macro)
{headlines}

Consider: does the direction fight the regime or BTC trend? Does any \
headline contradict the trade (e.g. bad news on a LONG)? Is the R:R \
acceptable? Is conviction backed by PROVEN systems or just lane noise?

Reply with ONLY a compact JSON object, no prose:
{{"verdict": "TRADE" | "WATCH" | "SKIP", "confidence": 0-100, \
"reason": "one concise sentence"}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": getattr(config, "ANTHROPIC_MODEL",
                                 "claude-3-5-haiku-latest"),
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return {"verdict": "ERROR", "confidence": 0,
                    "reason": f"API {resp.status_code}"}
        data = resp.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text").strip()
        # Strip markdown fences if the model added them
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)
        verdict = str(parsed.get("verdict", "WATCH")).upper()
        if verdict not in ("TRADE", "WATCH", "SKIP"):
            verdict = "WATCH"
        return {
            "verdict": verdict,
            "confidence": int(parsed.get("confidence", 0) or 0),
            "reason": str(parsed.get("reason", ""))[:200],
        }
    except Exception as exc:
        return {"verdict": "ERROR", "confidence": 0,
                "reason": str(exc)[:120]}


def agent2_validate(candidates: list[dict],
                   regime_info: dict,
                   news_headlines: list[str],
                   det_floor: float = 68.0,
                   llm_top_n: int = 3,
                   use_llm: bool = True) -> list[dict]:
    """Score candidates deterministically, then LLM-validate the top few.

    Each returned dict gains:
        conviction: float 0-100
        conviction_reasons: list[str]
        llm: dict | None  ({verdict, confidence, reason})
        passed: bool       final validate decision
    """
    scored = []
    for cand in candidates:
        conv, reasons = _deterministic_conviction(cand, regime_info)
        c = dict(cand)
        c["conviction"] = conv
        c["conviction_reasons"] = reasons
        c["llm"] = None
        scored.append(c)
    # Only candidates clearing the deterministic floor proceed
    survivors = [c for c in scored if c["conviction"] >= det_floor]
    survivors.sort(key=lambda c: c["conviction"], reverse=True)

    # LLM verdict on the top N survivors only (cost control)
    api_key = getattr(config, "ANTHROPIC_API_KEY", "") or ""
    llm_active = use_llm and bool(api_key)
    for i, c in enumerate(survivors):
        if llm_active and i < llm_top_n:
            v = _llm_verdict(c, regime_info, news_headlines,
                            c["conviction"], c["conviction_reasons"])
            c["llm"] = v
            if v is None:
                c["passed"] = True             # no LLM → det decision
            elif v["verdict"] == "TRADE":
                c["passed"] = True
            elif v["verdict"] == "ERROR":
                c["passed"] = True             # fail-open on API error
            else:  # WATCH or SKIP
                c["passed"] = False
        else:
            # Deterministic-only path (no key, or beyond top-N)
            c["passed"] = True
    return survivors


# ===========================================================================
# AGENT 3 — PRESENT
# ===========================================================================
def agent3_present(validated: list[dict],
                  max_picks: int = 5) -> list[dict]:
    """Final ranked sure-shot list. Only TRADE-eligible (passed) picks.

    Ranking key: LLM-confirmed first, then conviction, then proven_count.
    """
    final = [c for c in validated if c.get("passed")]

    def _rank_key(c):
        llm = c.get("llm") or {}
        llm_trade = 1 if llm.get("verdict") == "TRADE" else 0
        llm_conf = llm.get("confidence", 0) if llm else 0
        return (llm_trade, c.get("conviction", 0),
                c.get("proven_count", 0), llm_conf)

    final.sort(key=_rank_key, reverse=True)
    return final[:max_picks]


# ===========================================================================
# ORCHESTRATOR
# ===========================================================================
def run_pipeline(scan_picks: list[dict],
                regime_info: dict,
                convergence_syms: set,
                sure_shot_syms: set,
                elite_lookup: dict,
                news_headlines: list[str] | None = None,
                det_floor: float = 68.0,
                llm_top_n: int = 3,
                use_llm: bool = True,
                max_picks: int = 5) -> dict:
    """Run all three agents and return a structured result.

    Returns:
        {
          "candidates": [...],     Agent 1 output
          "validated": [...],      Agent 2 output (survivors, scored)
          "sure_shots": [...],     Agent 3 output (final TRADE picks)
          "stats": {
             "gathered": int, "survived": int, "sure_shots": int,
             "llm_active": bool, "llm_calls": int,
          },
        }
    """
    news_headlines = news_headlines or []

    # Agent 1
    candidates = agent1_gather(
        scan_picks, convergence_syms, sure_shot_syms, elite_lookup)

    # Agent 2
    validated = agent2_validate(
        candidates, regime_info, news_headlines,
        det_floor=det_floor, llm_top_n=llm_top_n, use_llm=use_llm)

    # Agent 3
    sure_shots = agent3_present(validated, max_picks=max_picks)

    api_key = getattr(config, "ANTHROPIC_API_KEY", "") or ""
    llm_active = use_llm and bool(api_key)
    llm_calls = sum(1 for c in validated if c.get("llm") is not None)

    return {
        "candidates": candidates,
        "validated": validated,
        "sure_shots": sure_shots,
        "stats": {
            "gathered": len(candidates),
            "survived": len(validated),
            "sure_shots": len(sure_shots),
            "llm_active": llm_active,
            "llm_calls": llm_calls,
        },
    }

"""🔬 NIGHTLY AUDITOR — the system watches itself while you sleep.

Validated 2026-09-04 (.llm_auditor_validate.py, commit 9125e84): the
check-suite caught 5/5 fixtures of this week's four REAL defects (the
eagle `_b3` NameError, the `_pw_mult` record loss, the BEST ZONE
greens-gate mute, elite_conv's missing desk tier) with zero false
alarms on the healthy fixture. The two false-positive classes the
validation surfaced on the stale July DB are fixed here: C1 only
checks streams in the explicit STREAM_TO_TIER map (naming aliases),
and C6 only watches dependents that exist in this code era.

Design rule: every finding and every number is a SQL query —
deterministic, cheap, testable. The model (ANTHROPIC_MODEL_DEEP,
Fable) only PHRASES the headline, and any API failure falls back to
template text. A wrong model call can mis-phrase a morning message;
it can never invent or suppress a finding, and it can never touch a
trade.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

import config
import worker_store as store

D = 86400.0

# stream name (signals table) -> desk tier name (shadow_trades) for the
# streams that are WIRED to open a desk trade per signal. C1 checks
# only these — everything else records without a same-named tier and
# would be a naming false positive (the July-DB lesson).
STREAM_TO_TIER = {
    "apex": "apex", "one_trade": "one_trade",
    "elite_conv": "elite_conv", "elite_confirm": "elite_confirm",
    "prime": "prime", "moonshot": "moonshot",
    "conviction_v2": "conviction_v2", "surge": "surge",
    "ignition": "ignition", "ignition_strong": "ignition_strong",
    "true_signal": "true_signal", "kr_approved": "kr_approved",
    "kr_strong": "kr_strong", "sentry": "sentry",
    "top_conviction": "top_conviction", "preburst": "preburst",
    "fast30": "fast30", "best": "best_board",
    "takenow": "takenow_hot", "early_strong": "early_movers",
    "trend": "trend_rider", "eagle_heat": "eagle_heat",
    "duo85": "duo85", "kingpair": "kingpair",
    "tnelite": "tnelite", "apextn": "apextn",
    "sniper": "sniper", "revival": "revival",
    "personal_watch": "personal_watch",
    "personal_watch_early": "personal_watch_early",
}
# dependent stream -> (parent stream, max healthy silent days). Only
# streams that exist in THIS code era (the second July-DB lesson).
DEPENDENTS = {"eagle_heat": ("elite_conv", 3.0),
              "duo85": ("apex", 7.0),
              "kingpair": ("one_trade", 14.0),
              "tnelite": ("takenow", 14.0),
              "apextn": ("apex", 14.0)}
# buzz alert-key prefix -> stream that must record alongside it
BUZZ_RECORD = {"pwatch": "personal_watch",
               "pwatch_early": "personal_watch_early"}
CONF_TIERS = ("apex", "best_board", "one_trade", "elite_conv")


def _checks(c: sqlite3.Connection, now: float) -> list[tuple[str, str]]:
    """The validated C1-C6 suite. Returns (code, message) findings."""
    f: list[tuple[str, str]] = []
    # C1 signals flowing but desk tier empty (wiring/recording broken)
    for st, tier in STREAM_TO_TIER.items():
        n_sig = c.execute(
            "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
            (st, now - 5 * D)).fetchone()[0]
        if n_sig < 5:
            continue
        n_desk = c.execute(
            "SELECT COUNT(*) FROM shadow_trades WHERE tier=? "
            "AND opened_at>=?", (tier, now - 5 * D)).fetchone()[0]
        if n_desk == 0:
            f.append(("C1", f"`{st}`: {n_sig} signals in 5d but ZERO "
                            f"desk trades — wiring or recording broken"))
    # C2 worker stall
    base = c.execute(
        "SELECT COUNT(*) FROM signals WHERE ts BETWEEN ? AND ?",
        (now - 8 * D, now - D)).fetchone()[0] / 7.0
    last24 = c.execute("SELECT COUNT(*) FROM signals WHERE ts >= ?",
                       (now - D,)).fetchone()[0]
    if base >= 3 and last24 == 0:
        f.append(("C2", f"worker looks STALLED: {base:.0f} signals/day "
                        f"baseline, 0 in the last 24h"))
    # C3 conf stamps going missing
    cols = {r[1] for r in c.execute("PRAGMA table_info(shadow_trades)")}
    for t in (CONF_TIERS if "conf" in cols else ()):
        n_null = c.execute(
            "SELECT COUNT(*) FROM shadow_trades WHERE tier=? AND "
            "opened_at>=? AND conf IS NULL", (t, now - 3 * D)
        ).fetchone()[0]
        if n_null >= 3:
            f.append(("C3", f"`{t}`: {n_null} desk trades in 3d missing "
                            f"the conf stamp"))
    # C4 greens-gate flips (both directions — a mute OR a comeback)
    for (t,) in c.execute("SELECT DISTINCT tier FROM shadow_trades"):
        def form(upto):
            r = c.execute(
                "SELECT COALESCE(SUM(pnl_r),0), COUNT(*) FROM "
                "shadow_trades WHERE tier=? AND status='CLOSED' "
                "AND closed_at BETWEEN ? AND ?",
                (t, upto - 14 * D, upto)).fetchone()
            return float(r[0]), int(r[1])
        f_now, n_now = form(now)
        f_yd, n_yd = form(now - D)
        if n_now >= 10 and n_yd >= 10:
            if f_yd > 0 >= f_now:
                f.append(("C4", f"`{t}`: 14d form flipped NEGATIVE "
                                f"({f_yd:+.1f}R → {f_now:+.1f}R) — the "
                                f"greens gate mutes it today"))
            elif f_now > 0 >= f_yd:
                f.append(("C4", f"`{t}`: 14d form flipped POSITIVE "
                                f"({f_yd:+.1f}R → {f_now:+.1f}R) — it "
                                f"can come back off the bench"))
    # C5 buzzes sent but records silently failing
    for pref, st in BUZZ_RECORD.items():
        n_bz = c.execute(
            "SELECT COUNT(*) FROM alerts_sent WHERE alert_id LIKE ? "
            "AND last_ts >= ?", (pref + ":%", now - 3 * D)).fetchone()[0]
        n_rec = c.execute(
            "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
            (st, now - 3 * D)).fetchone()[0]
        if n_bz >= 2 and n_rec == 0:
            f.append(("C5", f"`{st}`: {n_bz} buzzes sent in 3d but ZERO "
                            f"records — the ledger is silently losing "
                            f"this stream"))
    # C6 dependent stream never fired though its parent keeps firing
    for dep, (parent, max_d) in DEPENDENTS.items():
        n_par = c.execute(
            "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
            (parent, now - max_d * D)).fetchone()[0]
        ever = c.execute("SELECT COUNT(*) FROM signals WHERE stream=?",
                         (dep,)).fetchone()[0]
        if n_par >= 10 and ever == 0:
            f.append(("C6", f"`{dep}`: parent `{parent}` fired {n_par}x "
                            f"in {max_d:.0f}d yet `{dep}` has NEVER "
                            f"recorded — its code path may be crashing"))
    return f


def _brief(c: sqlite3.Connection, now: float) -> list[str]:
    """Yesterday-in-numbers + decision-ready. Pure queries."""
    lines: list[str] = []
    day = list(c.execute(
        "SELECT tier, symbol, side, pnl_r FROM shadow_trades "
        "WHERE status='CLOSED' AND closed_at>=?", (now - D,)))
    n_sig = c.execute("SELECT COUNT(*) FROM signals WHERE ts>=?",
                      (now - D,)).fetchone()[0]
    n_open = c.execute(
        "SELECT COUNT(*) FROM shadow_trades WHERE opened_at>=?",
        (now - D,)).fetchone()[0]
    net = sum(float(x[3] or 0) for x in day)
    lines.append(f"24h: {n_sig} signals · {n_open} desk opens · "
                 f"{len(day)} closes · net {net:+.2f}R")
    if day:
        b = max(day, key=lambda x: x[3] or 0)
        w = min(day, key=lambda x: x[3] or 0)
        lines.append(f"best `{b[1]}` {b[2]} ({b[0]}) {b[3]:+.2f}R · "
                     f"worst `{w[1]}` {w[2]} ({w[0]}) {w[3]:+.2f}R")
    # 📊 analyst section (user go 2026-09-04): per-tier day movers,
    # 14d form leaders/laggards, narrative-recorder count — every
    # number a query, the model only phrases the headline.
    tiers: dict = {}
    for t, _sym, _side, r in day:
        g = tiers.setdefault(t, [0, 0.0])
        g[0] += 1
        g[1] += float(r or 0)
    movers = sorted(tiers.items(), key=lambda kv: -abs(kv[1][1]))[:3]
    if movers:
        lines.append("day movers: " + " · ".join(
            f"`{t}` {n}cl {net:+.1f}R" for t, (n, net) in movers))
    forms = []
    for (t,) in c.execute("SELECT DISTINCT tier FROM shadow_trades"):
        r = c.execute(
            "SELECT COALESCE(SUM(pnl_r),0), COUNT(*) FROM shadow_trades "
            "WHERE tier=? AND status='CLOSED' AND closed_at>=?",
            (t, now - 14 * D)).fetchone()
        if int(r[1]) >= 10:
            forms.append((t, float(r[0])))
    if forms:
        forms.sort(key=lambda x: -x[1])
        hi, lo = forms[0], forms[-1]
        lines.append(f"14d form: best `{hi[0]}` {hi[1]:+.1f}R · "
                     f"worst `{lo[0]}` {lo[1]:+.1f}R")
    try:
        n_ev = store.event_flag_count(1.0)
        if n_ev:
            lines.append(f"📰 {n_ev} event flags recorded (proving, "
                         f"gates nothing)")
    except Exception:
        pass
    ready = list(c.execute(
        "SELECT tier, COUNT(*), SUM(CASE WHEN pnl_r>0 THEN 1 ELSE 0 "
        "END), COALESCE(SUM(pnl_r),0) FROM shadow_trades WHERE "
        "status='CLOSED' GROUP BY tier "
        "HAVING COUNT(*) BETWEEN 20 AND 24"))
    for t, n, wn, nt in ready:
        lines.append(f"⚖️ decision-ready: `{t}` hit {n} closed — "
                     f"{wn}/{n} wins · {nt:+.1f}R")
    return lines


def _phrase(findings: list[tuple[str, str]], brief: list[str]) -> str | None:
    """Optional Fable-written headline. Fail-soft: None on ANY issue."""
    if not getattr(config, "ANTHROPIC_API_KEY", None):
        return None
    try:
        import anthropic
        cl = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                 timeout=25.0)
        txt = ("Findings:\n" + "\n".join(m for _, m in findings)
               + "\nStats:\n" + "\n".join(brief))
        r = cl.messages.create(
            model=getattr(config, "ANTHROPIC_MODEL_DEEP",
                          "claude-fable-5"),
            max_tokens=260,
            messages=[{"role": "user", "content":
                       "One sentence, direct, for a trader's morning "
                       "Telegram: the single most important thing in "
                       "this system health report. No preamble.\n"
                       + txt}])
        out = "".join(b.text for b in r.content
                      if getattr(b, "type", "") == "text").strip()
        return out[:200] if out else None
    except Exception:
        return None


def run_daily(send: bool = True, phrase: bool = True,
              now: float | None = None) -> str:
    """Run checks + brief, compose ONE message, optionally send."""
    now = time.time() if now is None else now
    c = sqlite3.connect(store.DB_PATH, timeout=10)
    try:
        findings = _checks(c, now)
        brief = _brief(c, now)
    finally:
        c.close()
    stamp = datetime.now(timezone.utc).strftime("%b %d")
    if findings:
        head = f"🔬 *AUDITOR — {len(findings)} finding" + \
               ("s" if len(findings) > 1 else "") + f"* · {stamp}"
        body = "\n".join(f"⚠️ {m}" for _, m in findings)
    else:
        head = f"🔬 *AUDITOR — all clear* · {stamp}"
        body = "every stream recording, no silent failures detected"
    ai = _phrase(findings, brief) if phrase else None
    msg = head + "\n" + body + "\n" + "\n".join(brief)
    if ai:
        msg += f"\n🧠 _{ai}_"
    if send:
        try:
            import telegram_notify as tg
            tg.send(msg)
        except Exception as exc:
            print("[auditor] send error:", exc, flush=True)
    return msg

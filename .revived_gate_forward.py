"""⭐⚡/💎⚡ GO REVIVED gate — FORWARD CHECK (user 2026-10-15: "have a history of
it according to its win rates so we can compare the BTC rule").
Usage:  .venv/Scripts/python .revived_gate_forward.py <path to worker.db>
Splits every go_revived desk trade opened since the gates went live by what
its GO bell did (rang / gated) and by WHICH rule gated it (BTC day, MAX card,
score 90+), so the BTC rule can be judged against the bells that rang.
Also prints the pre-gate stamped cells the rules came from, for reference."""
import calendar
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

DB = sys.argv[1] if len(sys.argv) > 1 else r"F:\Trading Indicator\.state_backup_1014\worker.db"
GATES_LIVE = calendar.timegm((2026, 10, 14, 11, 48, 0))      # 394d805, 16:48 PKT
THREE_RULES = calendar.timegm((2026, 10, 14, 13, 25, 0))     # 1df9ac5 landed ~18:25 PKT
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
PK = 5 * 3600

# the GO stamps: star_go / elite_go carry "bell" (sent-standalone / gated: read: … / thread)
stamps = {}
for ts, sym, side, extra in con.execute("SELECT ts, symbol, side, extra FROM signals WHERE stream IN ('star_go','elite_go') AND ts >= ?", (GATES_LIVE - 3600,)):
    try:
        ex = json.loads(extra or "{}")
    except Exception:
        ex = {}
    stamps.setdefault((sym, (side or "").upper()), []).append((float(ts), ex.get("bell") or "", ex))

rows = con.execute("SELECT symbol, side, opened_at, closed_at, entry, stop0, tp1, pnl_r, tp1_hit, status FROM shadow_trades "
                   "WHERE tier='go_revived' AND opened_at >= ? AND entry>0 AND abs(entry-stop0)/entry>=0.005", (GATES_LIVE,)).fetchall()
df = pd.DataFrame(rows, columns=["symbol", "side", "opened", "closed", "entry", "stop0", "tp1", "r", "tp1_hit", "status"])
df["side"] = df.side.str.upper()


def stamp_for(r):
    best = None
    for ts, bell, ex in stamps.get((r.symbol, r.side), ()):
        d = abs(ts - float(r.opened))
        if d <= 900 and (best is None or d < best[0]):
            best = (d, bell, ex)
    return best[1] if best else ""


df["bell"] = pd.Series([stamp_for(r) for r in df.itertuples()], index=df.index, dtype="string").fillna("")
df["rang"] = df.bell.str.startswith("sent")
df["gated"] = df.bell.str.startswith("gated")
df["fail_btc"] = df.bell.str.contains("⚠️ BTC")
df["fail_max"] = df.bell.str.contains("⚠️ MAX card")
df["fail_score"] = df.bell.str.contains("⚠️ score")
df["fail_conf"] = df.bell.str.contains("⚠️ conf")          # pre-18:25 PKT 14 Oct only
df["fail_clock"] = df.bell.str.contains("⚠️ fired")        # pre-18:12 PKT 14 Oct only
df["when"] = df.opened.map(lambda t: time.strftime("%d %b %H:%M PKT", time.gmtime(t + PK)))
closed = df[(df.status == "CLOSED") & df.r.notna()]


def cell(g):
    if not len(g):
        return "—"
    w = g[g.r > 0]
    return f"{(g.r>0).mean()*100:3.0f}% / {g.r.mean():+.2f}R ({len(g)}) · net {g.r.sum():+.1f}R · TP1 {g.tp1_hit.mean()*100:.0f}%"


print(f"GO REVIVED desk trades since the gates went live (14 Oct 16:48 PKT): {len(df)} opened, {len(closed)} closed, {int((df.status!='CLOSED').sum())} still open")
df["unappr"] = df.bell.str.contains("unapproved")
closed = df[(df.status == "CLOSED") & df.r.notna()]
print(f"  bell rang      : {cell(closed[closed.rang])}")
print(f"     rang, star / approved    : {cell(closed[closed.rang & ~closed.unappr])}")
print(f"     rang, UNAPPROVED (tagged): {cell(closed[closed.rang & closed.unappr])}   (ring since 15 Oct)")
print(f"  bell gated     : {cell(closed[closed.gated])}")
print(f"     gated by BTC day   : {cell(closed[closed.gated & closed.fail_btc & ~closed.fail_max & ~closed.fail_score])}   (BTC the ONLY failing rule)")
print(f"     gated by MAX card  : {cell(closed[closed.gated & closed.fail_max])}")
print(f"     gated by score 90+ : {cell(closed[closed.gated & closed.fail_score])}")
print(f"  no stamp found : {cell(closed[~closed.rang & ~closed.gated])}")
print(f"  (since the three-rule read, 14 Oct 18:25 PKT): rang {cell(closed[closed.rang & (closed.opened >= THREE_RULES)])} · gated {cell(closed[closed.gated & (closed.opened >= THREE_RULES)])}")
print("\n  every trade:")
for r in df.sort_values("opened").itertuples():
    tag = "rang" if r.rang else ("gated: " + ", ".join(k for k, v in (("BTC", r.fail_btc), ("MAX", r.fail_max), ("score", r.fail_score), ("conf", r.fail_conf), ("clock", r.fail_clock)) if v) if r.gated else "no stamp")
    print(f"     {r.when} {r.symbol:12s} {r.side:5s} {tag:26s} {('%+.2fR' % r.r) if r.r is not None and r.status == 'CLOSED' else 'open':>8s}")

print("\n  REFERENCE — the stamped desk cells the rules came from (13 Sep → 14 Oct, from the fire price):")
print("     BTC day < -1.5% rejects      41% / +0.06R (37)   <- the soft rule; judge it against 'bell rang' above")
print("     MAX card rejects             26% / -0.15R (23)")
print("     score 90+ rejects            17% / -0.49R (12)")
print("     three-rule pass vs fail      65% / +0.42R (116) vs 38% / -0.02R (50)")
print("     7-week replay, BTC rule alone, AT THE GO: pass 64% / -0.01R (502) vs fail 58% / +0.01R (64) — no edge at the GO price")
print("  Decision rule (pre-registered 2026-10-15): drop the BTC rule if, after 20+ closed BTC-only-gated trades, their avg R is within 0.10R of the rang set or better.")

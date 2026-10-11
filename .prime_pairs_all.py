"""🥇 PRIME x EVERY STREAM — which stream, when it fires while 🥇 PRIME has the
same coin+side on its board, has the strongest record? (user 2026-10-11)
Overlap = a PRIME signal 2h before → 30 min after the partner's desk open (the
window used for the star / conviction study). Outcome = the PARTNER trade's
desk result (ladder exits, fees). Clean = |entry-stop0|/entry >= 0.5%.
Ranked by win rate (n >= 20) with the R beside it, plus the lift vs the same
stream without PRIME. Ledger copy 2026-09-01 → 2026-09-28."""
import io
import sqlite3
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = sys.argv[1]
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
BEFORE, AFTER = 2 * 3600, 30 * 60
prime = defaultdict(list)
for s, d, ts in con.execute("SELECT symbol, side, ts FROM signals WHERE stream='prime'"):
    prime[(s, (d or "").upper())].append(float(ts))
rows = con.execute(
    "SELECT tier, symbol, side, opened_at, pnl_r FROM shadow_trades WHERE status='CLOSED' AND pnl_r IS NOT NULL "
    "AND opened_at>=strftime('%s','2026-09-01') AND entry>0 AND abs(entry-stop0)/entry>=0.005").fetchall()
df = pd.DataFrame(rows, columns=["tier", "symbol", "side", "opened", "r"])
df["side"] = df.side.str.upper()
df["with_prime"] = [any(o - BEFORE <= t <= o + AFTER for t in prime.get((s, d), ())) for s, d, o in zip(df.symbol, df.side, df.opened)]
out = []
for tier, g in df.groupby("tier"):
    a, b = g[g.with_prime], g[~g.with_prime]
    if len(a) < 20:
        continue
    out.append(dict(tier=tier, n=len(a), win=(a.r > 0).mean() * 100, avg=a.r.mean(), net=a.r.sum(),
                    n_off=len(b), win_off=((b.r > 0).mean() * 100 if len(b) else np.nan), avg_off=(b.r.mean() if len(b) else np.nan),
                    longs=(a.side == "LONG").mean() * 100))
R = pd.DataFrame(out).sort_values("win", ascending=False)
pd.set_option("display.width", 200)
print(f"desk trades 09-01 → 09-28 (clean, closed): {len(df)} · streams with >= 20 PRIME overlaps: {len(R)}\n")
print(f"{'stream':18s} {'with PRIME: n':>13s} {'win':>5s} {'avg R':>7s} {'net':>7s} | {'without: win':>12s} {'avg R':>7s} {'n':>5s} | {'lift R':>7s} {'% longs':>8s}")
for _, x in R.iterrows():
    print(f"{x.tier:18s} {x.n:13d} {x.win:4.0f}% {x.avg:+7.2f} {x.net:+7.1f} | {x.win_off:11.0f}% {x.avg_off:+7.2f} {x.n_off:5d} | {x.avg - x.avg_off:+7.2f} {x.longs:7.0f}%")
print("\nsame table ranked by avg R with PRIME:")
for _, x in R.sort_values("avg", ascending=False).head(10).iterrows():
    print(f"  {x.tier:18s} {x.win:4.0f}% · {x.avg:+.2f}R · net {x.net:+.1f}R (n={x.n}) · without {x.win_off:.0f}% / {x.avg_off:+.2f}R")
# PRIME's own trades when a given partner also fired (the reverse view)
print("\nreverse: 🥇 PRIME desk trades by which other stream fired on the coin within the window:")
pt = df[df.tier == "prime"]
sigs = defaultdict(list)
streams = [r[0] for r in con.execute("SELECT DISTINCT stream FROM signals WHERE ts>=strftime('%s','2026-09-01')")]
for st in streams:
    for s, d, ts in con.execute("SELECT symbol, side, ts FROM signals WHERE stream=? AND ts>=strftime('%s','2026-08-31')", (st,)):
        sigs[(st, s, (d or "").upper())].append(float(ts))
rev = []
for st in streams:
    hit = [r for s, d, o, r in zip(pt.symbol, pt.side, pt.opened, pt.r) if any(o - BEFORE <= t <= o + AFTER for t in sigs.get((st, s, d), ()))]
    if len(hit) >= 20:
        rev.append((st, len(hit), np.mean(np.array(hit) > 0) * 100, np.mean(hit)))
for st, n, w, a in sorted(rev, key=lambda x: -x[2])[:12]:
    print(f"  PRIME + {st:16s}: {w:4.0f}% · {a:+.2f}R (n={n})")
print(f"  PRIME alone (all): {(pt.r > 0).mean() * 100:.0f}% · {pt.r.mean():+.2f}R (n={len(pt)})")

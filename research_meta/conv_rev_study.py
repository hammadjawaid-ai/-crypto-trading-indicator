"""💯↩️ CONVICTION v2 REVERSED — replay (2026-11-06).

User: "reverse the signals with it — if it says tp it should be considered as sl and sl should be
considered as tp". Every CLEAN closed conviction_v2 desk trade (4 Nov ledger backup, risk >= 0.1%)
is replayed on the 15m candle path twice: as the desk took it (validates the harness against the
ledger's own record) and MIRRORED — the opposite side, entry at the same price, the plan's TP1 as
the stop and the plan's stop as the target. Both run through the desk's own ladder (BE at +1R,
TP1 lock, 1.2R trail after TP1, 48h time stop, taker fees both ways) and, for transparency, as a
plain stop/target trade. Same-bar stop + target = stop. Research only; nothing here touches live code.

Run: research_meta\\.venv\\Scripts\\python.exe -I research_meta\\conv_rev_study.py
"""
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RM)
import channel_study as CS  # noqa: E402  (candles() + the kl_channel cache)

PKT = timezone(timedelta(hours=5))
DB = os.path.join(os.path.dirname(RM), ".state_backup_1104", "worker.db")
OUT = os.path.join(RM, "conv_rev_rows.csv")
LOG = os.path.join(RM, "conv_rev_log.txt")
FEE = 2 * 0.00055          # the desk's own round-trip taker fee
TRAIL_R = 1.2
MAX_BARS = 192             # 48h of 15m


def ladder(d, j, e, side, stop, tp1, tp2, plain=False):
    """The desk ladder on bars. side +1 long / -1 short. Returns (net_R, reason, bars)."""
    risk = abs(e - stop)
    if risk <= 0:
        return None
    h = d.h.to_numpy(); l = d.l.to_numpy(); c = d.c.to_numpy()
    n = min(j + MAX_BARS, len(d))
    if j >= n:
        return None
    long = side == 1
    be = tp1_hit = False
    peak = e
    fee_r = FEE * e / risk
    for k in range(j, n):
        adverse = l[k] if long else h[k]
        favour = h[k] if long else l[k]
        stopped = (adverse <= stop) if long else (adverse >= stop)
        if stopped:
            g = (stop - e) if long else (e - stop)
            return (g / risk - fee_r, ("TP1_LOCK" if tp1_hit else "STOP"), k - j + 1)
        hit2 = bool(tp2) and ((favour >= tp2) if long else (favour <= tp2))
        if hit2 and not plain:
            g = (tp2 - e) if long else (e - tp2)
            return (g / risk - fee_r, "TP2", k - j + 1)
        hit1 = (favour >= tp1) if long else (favour <= tp1)
        if plain and hit1:
            g = (tp1 - e) if long else (e - tp1)
            return (g / risk - fee_r, "TP", k - j + 1)
        peak = max(peak, favour) if long else min(peak, favour)
        gain = (peak - e) if long else (e - peak)
        if not plain:
            if not be and gain >= risk:
                stop, be = e, True
            if hit1 and not tp1_hit:
                stop, tp1_hit = tp1, True
            if tp1_hit:
                trail = (peak - TRAIL_R * risk) if long else (peak + TRAIL_R * risk)
                stop = max(stop, trail) if long else min(stop, trail)
    g = (c[n - 1] - e) if long else (e - c[n - 1])
    return (g / risk - fee_r, "TIME", n - j)


def stat(rs, label):
    v = [float(x) for x in rs if x is not None and not (isinstance(x, float) and np.isnan(x))]
    if not v:
        return f"{label:44s} n=0"
    w = sum(1 for x in v if x > 0)
    return (f"{label:44s} n={len(v):4d}  win {100 * w / len(v):4.0f}%  mean {np.mean(v):+.3f}R  "
            f"sum {np.sum(v):+8.1f}R")


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT id,symbol,side,entry,stop0,tp1,tp2,opened_at,exit_reason,pnl_r FROM shadow_trades "
        "WHERE tier='conviction_v2' AND status='CLOSED' AND entry>0 AND abs(entry-stop0)/entry >= 0.001 "
        "ORDER BY opened_at").fetchall()
    c.close()
    first = {}
    for r in rows:
        first.setdefault(r[1], r[7])
    out = []
    t0 = time.time()
    miss = 0
    for i, (tid, sym, side, e, s0, t1, t2, ot, xr, pr) in enumerate(rows):
        base = sym[:-4] if sym.endswith("USDT") else sym
        d = CS.candles(base, int((first[sym] - 86400) * 1000))
        if d is None or len(d) < 50:
            miss += 1
            continue
        ots = d.ot.to_numpy()
        j = int(np.searchsorted(ots, ot * 1000, side="left"))     # first bar opening at/after the seat
        sd = 1 if side == "LONG" else -1
        rec = dict(id=tid, symbol=sym, side=side, entry=e, stop=s0, tp1=t1, tp2=t2 or 0.0, opened_at=ot,
                   month=datetime.fromtimestamp(ot, PKT).strftime("%b"), ledger_r=pr, ledger_exit=xr)
        o = ladder(d, j, e, sd, s0, t1, t2 or 0.0)
        m = ladder(d, j, e, -sd, t1, s0, 0.0)               # the mirror: TP1 is the stop, stop is the target
        op = ladder(d, j, e, sd, s0, t1, 0.0, plain=True)
        mp = ladder(d, j, e, -sd, t1, s0, 0.0, plain=True)
        for k, v in (("orig", o), ("mirror", m), ("orig_plain", op), ("mirror_plain", mp)):
            rec[k + "_r"] = v[0] if v else None
            rec[k + "_exit"] = v[1] if v else None
        out.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rows)} replayed · {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    lines = [f"💯↩️ CONVICTION v2 REVERSED — replay of {len(df)} clean closed desk trades "
             f"({len(rows)} in the ledger, {miss} without candles) · 25 Aug → 4 Nov 2026",
             "ruler: 15m candle path from the first bar after the seat, entry = the ledger's seat price, desk ladder "
             "(BE +1R · TP1 lock · 1.2R trail · 48h), fees 0.11% round trip in R, same-bar stop+target = stop", ""]
    lines.append(stat(df.ledger_r, "LEDGER (what the desk booked)"))
    lines.append(stat(df.orig_r, "ORIGINAL replayed, desk ladder"))
    lines.append(stat(df.orig_plain_r, "ORIGINAL replayed, plain stop/TP1"))
    lines.append(stat(df.mirror_r, "MIRROR, desk ladder  ← the ask"))
    lines.append(stat(df.mirror_plain_r, "MIRROR, plain stop(old TP1)/target(old stop)"))
    lines.append("")
    h = len(df) // 2
    lines.append(stat(df.mirror_r.iloc[:h], "  mirror first half"))
    lines.append(stat(df.mirror_r.iloc[h:], "  mirror second half"))
    for mth in ("Aug", "Sep", "Oct", "Nov"):
        sub = df[df.month == mth]
        lines.append(stat(sub.mirror_r, f"  mirror {mth}") + "   |  " + stat(sub.orig_r, f"orig {mth}"))
    for sd in ("LONG", "SHORT"):
        sub = df[df.side == sd]
        lines.append(stat(sub.mirror_r, f"  mirror of original {sd}s (= {'SHORT' if sd == 'LONG' else 'LONG'} seats)"))
    lines.append("")
    lines.append("mirror exits: " + str(df.mirror_exit.value_counts().to_dict()))
    lines.append("original exits (replay): " + str(df.orig_exit.value_counts().to_dict())
                 + "   ledger: " + str(df.ledger_exit.value_counts().to_dict()))
    rr = (df.stop - df.entry).abs() / (df.tp1 - df.entry).abs()
    lines.append(f"mirror geometry: target/risk median {rr.median():.2f} (the old stop is closer than the old TP1 — "
                 f"the mirror risks the big distance to win the small one)")
    txt = "\n".join(lines)
    print("\n" + txt)
    open(LOG, "w", encoding="utf-8").write(txt + "\n")
    print(f"\nrows → {OUT}\nlog → {LOG}")


if __name__ == "__main__":
    main()

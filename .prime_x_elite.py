"""🥇 PRIME x ⭐ ELITE STAR / 💎 ELITE CONVICTION — desk ledger copy (09-28).
Overlap = a PRIME board signal for the same coin+side from 2h before to 30 min
after the elite desk trade opened (the same window as the Top Conviction
double-stamp study). Outcome = the ELITE trade's desk pnl_r (ladder exits, taker
fees). Conf = the elite card's conf stamped on the trade. Thirds = chronological."""
import io
import sqlite3
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = sys.argv[1]
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
BEFORE, AFTER = 2 * 3600, 30 * 60

prime = defaultdict(list)
for s, d, ts in con.execute("SELECT symbol, side, ts FROM signals WHERE stream='prime'"):
    prime[(s, (d or "").upper())].append(float(ts))
star_sig = defaultdict(list)
for s, d, ts in con.execute("SELECT symbol, side, ts FROM signals WHERE stream='elite_star'"):
    star_sig[(s, (d or "").upper())].append(float(ts))
conv_sig = defaultdict(list)
for s, d, ts in con.execute("SELECT symbol, side, ts FROM signals WHERE stream='elite_conv'"):
    conv_sig[(s, (d or "").upper())].append(float(ts))


def had(sigmap, key, o):
    return any(o - BEFORE <= t <= o + AFTER for t in sigmap.get(key, ()))


def trades(tier, since):
    rows = con.execute(
        "SELECT symbol, side, opened_at, pnl_r, conf FROM shadow_trades WHERE tier=? AND status='CLOSED' "
        "AND pnl_r IS NOT NULL AND opened_at>=strftime('%s',?) AND entry>0 AND abs(entry-stop0)/entry>=0.005 "
        "ORDER BY opened_at", (tier, since)).fetchall()
    return [(s, (d or "").upper(), float(o), float(r), (float(c) if c is not None else None)) for s, d, o, r, c in rows]


def cell(xs):
    n = len(xs)
    if not n:
        return "—"
    w = sum(1 for x in xs if x > 0)
    return f"{w / n * 100:4.0f}% · {sum(xs) / n:+.2f}R · net {sum(xs):+6.1f}R (n={n})"


def thirds(rows):
    xs = [r for _, r in rows]
    if len(xs) < 9:
        return "thirds n/a"
    k = len(xs) // 3
    parts = [xs[:k], xs[k:2 * k], xs[2 * k:]]
    return "thirds " + " / ".join(f"{sum(p) / len(p):+.2f}" for p in parts)


def band(c):
    if c is None:
        return "conf ?"
    if c < 55:
        return "conf 40-54"
    if c < 65:
        return "conf 55-64"
    if c < 75:
        return "conf 65-74"
    if c < 85:
        return "conf 75-84"
    return "conf 85+"


BANDS = ("conf 40-54", "conf 55-64", "conf 65-74", "conf 75-84", "conf 85+", "conf ?")
for label, tier, since in (("⭐ ELITE STAR", "elite_star", "2026-09-09"), ("💎 ELITE CONVICTION", "elite_conv", "2026-09-01")):
    tr = trades(tier, since)
    on = [(o, r, c) for s, d, o, r, c in tr if had(prime, (s, d), o)]
    off = [(o, r, c) for s, d, o, r, c in tr if not had(prime, (s, d), o)]
    print(f"\n{label} desk trades {since} → 09-28 (clean, closed): {len(tr)}")
    print(f"  with 🥇 PRIME on the same coin+side : {cell([r for _, r, _ in on])} · {thirds([(o, r) for o, r, _ in on])}")
    print(f"  without PRIME                       : {cell([r for _, r, _ in off])} · {thirds([(o, r) for o, r, _ in off])}")
    print("  by the elite card's conf, WITH prime  |  WITHOUT prime")
    for b in BANDS:
        a = [r for _, r, c in on if band(c) == b]
        z = [r for _, r, c in off if band(c) == b]
        if a or z:
            print(f"    {b:11s}: {cell(a):48s} | {cell(z)}")
    for sd in ("LONG", "SHORT"):
        a = [r for s, d, o, r, c in tr if d == sd and had(prime, (s, d), o)]
        z = [r for s, d, o, r, c in tr if d == sd and not had(prime, (s, d), o)]
        print(f"    {sd:11s}: {cell(a):48s} | {cell(z)}")

pt = trades("prime", "2026-09-01")
print(f"\n🥇 PRIME desk trades 09-01 → 09-28 (clean, closed): {len(pt)}")
for lab, sm in (("with ⭐ STAR fire", star_sig), ("with 💎 CONVICTION fire", conv_sig)):
    a = [r for s, d, o, r, c in pt if had(sm, (s, d), o)]
    z = [r for s, d, o, r, c in pt if not had(sm, (s, d), o)]
    print(f"  {lab:24s}: {cell(a):48s} | without: {cell(z)}")
print("\n(window: prime signal 2h before → 30 min after the elite open; prime's own conf is not stored, so bands use the elite card's conf)")

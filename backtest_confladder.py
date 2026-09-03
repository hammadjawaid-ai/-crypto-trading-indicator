"""🎯 The ATR ladder — how high should the one working vote be set?

The teardown found only ONE of the three edge-conf votes carries signal
(HOT ATR), one is inert (HOT ROC), one is harmful (BURST>=78). This
walks the ATR-percentile cut upward and reports win rate + expectancy in
BOTH halves, alongside the gate we ship today, so the choice is made on
evidence rather than on the 0.6 that was never tested.

Also tests the two survivors that pair with it: entering soon after the
dip (since_dip low) and stretch above ema20 (dist_ema high).
"""
import io
import json
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

rows = [json.loads(x) for x in open(".pwfeat_rows.jsonl", encoding="utf-8")
        if x.strip()]


def stat(sel):
    n = len(sel)
    if not n:
        return 0, 0.0, 0.0
    w = sum(1 for r in sel if r["out"] == "WIN") / n * 100
    return n, w, sum(r["net"] for r in sel) / n


def show(pred, label):
    sel = [r for r in rows if pred(r)]
    n, w, e = stat(sel)
    if n == 0:
        print(f"  {label:<34} n=0")
        return
    parts = []
    ok = True
    for hf in ("older", "recent"):
        sub = [r for r in sel if r["half"] == hf]
        hn, hw, he = stat(sub)
        parts.append(f"{hf[:3]} {hw:4.1f}%/{he:+.3f}R (n={hn})")
        if he <= 0:
            ok = False
    mark = "✅" if ok else "  "
    thin = "  ⚠️" if n < 60 else ""
    print(f"  {mark} {label:<32} n={n:4} · win {w:5.1f}% · {e:+.3f}R"
          f"{thin}\n       {parts[0]}  |  {parts[1]}")


print("=" * 70)
print(f"🎯 WHERE TO SET THE GATE — {len(rows)} confirms")
print("   ✅ = profitable in BOTH halves (the ship rule)")
print("=" * 70)

print("\n── what ships today ────────────────────────────────────────")
show(lambda r: True, "no gate — every confirm")
show(lambda r: r["conf"] >= 65, "conf >= 65  (CURRENT BUZZ GATE)")

print("\n── the one working vote, cut walked upward ─────────────────")
for cut in (0.50, 0.60, 0.70, 0.80, 0.90):
    show(lambda r, c=cut: r["atr_pct"] >= c, f"HOT ATR pct >= {cut:.2f}")

print("\n── drop the dead + harmful votes, keep ATR ─────────────────")
show(lambda r: r["atr_pct"] >= 0.6 and r["burst"] < 78,
     "ATR>=.60 AND burst < 78")
show(lambda r: r["atr_pct"] >= 0.8 and r["burst"] < 78,
     "ATR>=.80 AND burst < 78")

print("\n── pair ATR with the other two survivors ───────────────────")
for cut in (0.70, 0.80):
    show(lambda r, c=cut: r["atr_pct"] >= c and r["since_dip"] <= 2,
         f"ATR>={cut:.2f} AND fresh (dip<=2 bars)")
    show(lambda r, c=cut: r["atr_pct"] >= c and r["dist_ema"] >= 1.0,
         f"ATR>={cut:.2f} AND ema stretch >=1%")
    show(lambda r, c=cut: (r["atr_pct"] >= c and r["since_dip"] <= 2
                           and r["burst"] < 78),
         f"ATR>={cut:.2f} + fresh + no max-burst")

print("\n── sanity: is BURST really hurting? ────────────────────────")
show(lambda r: r["burst"] >= 78, "burst >= 78 (the 3rd vote)")
show(lambda r: r["atr_pct"] >= 0.7 and r["burst"] >= 78,
     "ATR>=.70 AND burst>=78 (conf 85 shape)")
show(lambda r: r["atr_pct"] >= 0.7 and r["burst"] < 78,
     "ATR>=.70 AND burst<78")
print("=" * 70)

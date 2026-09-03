"""🎯 Reads .pwfeat_rows.jsonl and answers two questions.

Q1  Do the three current edge-conf votes each carry signal on their own,
    or are they three views of the same fact?
Q2  Does anything that is NOT momentum-heat separate winners better —
    and can a continuous score fitted on the OLDER half survive the
    RECENT half out of sample?

Nothing here writes to the app. Analysis only.
"""
import io
import json
import statistics as st
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

rows = [json.loads(x) for x in open(".pwfeat_rows.jsonl", encoding="utf-8")
        if x.strip()]
older = [r for r in rows if r["half"] == "older"]
recent = [r for r in rows if r["half"] == "recent"]


def stat(sel):
    n = len(sel)
    if not n:
        return 0, 0.0, 0.0
    w = sum(1 for r in sel if r["out"] == "WIN") / n * 100
    e = sum(r["net"] for r in sel) / n
    return n, w, e


def line(sel, label, thin=25):
    n, w, e = stat(sel)
    if n == 0:
        print(f"  {label:<38} n=0")
        return
    flag = "  ⚠️" if n < thin else ""
    print(f"  {label:<38} n={n:4} · win {w:5.1f}% · {e:+.3f}R{flag}")


print("=" * 66)
print(f"🎯 CONFIDENCE TEARDOWN — {len(rows)} confirms "
      f"({len(older)} older / {len(recent)} recent)")
print("=" * 66)
line(rows, "baseline — every confirm")

# ── Q1: the three votes, one at a time ───────────────────────────────
print("\n── Q1. Each current vote ALONE ─────────────────────────────")
VOTES = {
    "HOT ATR  (atr_pct>=.6)": lambda r: r["atr_pct"] >= 0.6,
    "HOT ROC  (roc_pct>=.6)": lambda r: r["roc_pct"] >= 0.6,
    "BURST    (burst>=78)  ": lambda r: r["burst"] >= 78,
}
for name, fn in VOTES.items():
    on = [r for r in rows if fn(r)]
    off = [r for r in rows if not fn(r)]
    _, w1, e1 = stat(on)
    _, w0, e0 = stat(off)
    print(f"  {name}  ON  n={len(on):4} win {w1:5.1f}% {e1:+.3f}R"
          f"   |  OFF n={len(off):4} win {w0:5.1f}% {e0:+.3f}R"
          f"   Δ{e1 - e0:+.3f}R")

print("\n  overlap — how often the votes fire together:")
ks = list(VOTES)
for a in range(len(ks)):
    for b in range(a + 1, len(ks)):
        fa, fb = VOTES[ks[a]], VOTES[ks[b]]
        both = sum(1 for r in rows if fa(r) and fb(r))
        ea = sum(1 for r in rows if fa(r))
        eb = sum(1 for r in rows if fb(r))
        j = both / (ea + eb - both) if (ea + eb - both) else 0
        print(f"    {ks[a].strip():<22} & {ks[b].strip():<22} "
              f"both {both:4} / either {ea + eb - both:4} = {j:.0%}")

# ── Q2: every feature, by tercile, both halves ───────────────────────
FEATS = ["atr_pct", "roc_pct", "burst", "ext_pct", "dist_ema",
         "body_pct", "vol_mult", "since_dip", "rr", "rs_btc", "btc_ret"]

print("\n── Q2. Each feature by tercile (low / mid / high) ───────────")
print("      shown as expectancy R; ✅ = same sign in BOTH halves\n")
keep = []
for f in FEATS:
    vals = sorted(r[f] for r in rows)
    q1, q2 = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    lows = [r for r in rows if r[f] <= q1]
    highs = [r for r in rows if r[f] > q2]
    _, wl, el = stat(lows)
    _, wh, eh = stat(highs)
    spread = eh - el
    # out-of-sample check: does the high-minus-low sign hold in both?
    sp = {}
    for hf, sub in (("older", older), ("recent", recent)):
        sl = [r for r in sub if r[f] <= q1]
        sh = [r for r in sub if r[f] > q2]
        sp[hf] = stat(sh)[2] - stat(sl)[2]
    holds = (sp["older"] > 0) == (sp["recent"] > 0) and abs(spread) > 0.05
    mark = "✅" if holds else "  "
    if holds:
        keep.append((f, 1 if spread > 0 else -1, abs(spread)))
    print(f"  {mark} {f:<10} low {el:+.3f}R ({wl:4.1f}%) → "
          f"high {eh:+.3f}R ({wh:4.1f}%)   spread {spread:+.3f}R"
          f"   [older {sp['older']:+.3f} / recent {sp['recent']:+.3f}]")

# ── Q3: build a continuous score on OLDER, test on RECENT ────────────
print("\n── Q3. Continuous score — fitted on OLDER, tested on RECENT ─")
if not keep:
    print("  no feature held its sign across both halves — nothing to fit.")
    sys.exit(0)

keep.sort(key=lambda t: -t[2])
print("  features that held sign in both halves, by spread:")
for f, sgn, sp in keep:
    print(f"    {f:<10} direction {'higher=better' if sgn > 0 else 'lower=better'}"
          f"   |spread| {sp:.3f}R")

# z-score each kept feature on the OLDER half only, then apply to recent
norm = {}
for f, sgn, _ in keep:
    xs = [r[f] for r in older]
    mu, sd = st.mean(xs), (st.pstdev(xs) or 1.0)
    norm[f] = (mu, sd, sgn)


def score(r):
    return sum(sgn * (r[f] - mu) / sd for f, (mu, sd, sgn) in norm.items())


for r in rows:
    r["score"] = score(r)

cut = sorted(x["score"] for x in older)
top_q = cut[int(len(cut) * 0.75)]
bot_q = cut[int(len(cut) * 0.25)]
print(f"\n  (top-quartile cut = {top_q:+.2f}, taken from the OLDER half)")
for hf, sub in (("OLDER  (in-sample)", older), ("RECENT (OUT-of-sample)",
                                                recent)):
    hi = [r for r in sub if r["score"] >= top_q]
    lo = [r for r in sub if r["score"] <= bot_q]
    _, wh, eh = stat(hi)
    _, wl, el = stat(lo)
    print(f"  {hf:<24} top-q n={len(hi):4} win {wh:5.1f}% {eh:+.3f}R"
          f"   |  bot-q n={len(lo):4} win {wl:5.1f}% {el:+.3f}R")

print("\n  head-to-head vs the score you ship today (conf>=65):")
for hf, sub in (("older", older), ("recent", recent)):
    line([r for r in sub if r["conf"] >= 65], f"  conf>=65 {hf}")
    line([r for r in sub if r["score"] >= top_q], f"  new score top-q {hf}")
print("=" * 66)

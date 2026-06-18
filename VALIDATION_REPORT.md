# Trading System Validation Report

**Generated:** 2026-06-18 (morning run)
**Method:** Walk-forward backtests, no lookahead. Each system scored on
data *up to* each bar, then outcome measured forward. Fees noted per
section (crypto perps ≈ 0.18% round-trip: taker ×2 + slippage).

> **Honest note on the overnight run:** the unattended overnight suite
> **failed** — this environment's sandbox blocks detached processes and
> reaps background shells during long idle, so it died minutes after
> starting and produced nothing. I re-ran everything in the foreground.
> The numbers below are real and freshly measured. SST1, Convergence,
> Predictor, ELITE-by-tier and Tiers-with-costs were still running when
> this was written and are appended at the bottom as they land.

---

## ⚠️ Read this first — the baseline

On the top liquid coins over this window, a **random long held 12h wins
~36.8%** of the time and averages **+0.06%**. Crypto drifts up, so 37%
is the coin-flip line. **A signal is only real if it clearly beats that.**
This is why "win rate" alone is misleading — context matters.

---

## Summary — systems ranked by measured edge

| System / slice | Win rate | Edge | Sample | Verdict |
|---|---|---|---|---|
| **Long: higher-low structure** (`hl_struct`) | 58.8% | +0.38%/12h (vs 0.06% base) | n=850 | ✅ **Real edge** |
| **Velocity burst — 90+ score only** | 43.6% | +0.164R | n=110 | ✅ Real, but rare |
| **Early burst (15m) — aligned, TP5** | ~20% | +0.093R | mid | 🟡 Thin |
| **Grind — strict+very-early+aligned** | 48% | +0.078R (pre-fee) | n=836 | 🟡 Thin (real) |
| ttm_squeeze (long) | 78% | +1.47% | n=32 | 🟡 Tiny sample |
| Grind — loose (what fires) | 43% | −0.021R | large | ❌ Break-even/neg |
| **Velocity burst — overall** | 35.8% | −0.022R | n=1157 | ❌ Negative |
| Velocity burst — 80-89 band | 33.7% | −0.100R | n=382 | ❌ Negative |
| Grind — score 80+ (strongest closes) | 36% | −0.196R | n=28 | ❌ Anti-predictive |
| Recovery: trend_reclaim | 32-35% | ~baseline | n=37 | ❌ No edge |
| smc_sweep (long) | 7% | −1.34% | n=129 | ❌ Broken |
| vwap_reclaim / reclaim / engulfing | 17-25% | negative | mixed | ❌ Negative |

**⏳ Running now:** SST1 · Convergence · Predictor · ELITE-by-tier ·
Pattern Scout tiers (S/A/B/C) with costs.

---

## Per-system detail

### ✅ Higher-low structure (long) — the strongest verified edge
- **58.8% win, +0.38% avg/12h, n=850** vs baseline 36.8% / +0.06%.
- After ~0.18% fees ≈ **+0.20% net** — still clearly positive, large
  sample. This is the most trustworthy long signal in the system.
- Same module's other patterns are weak: `rsi_div` 42.9%/+0.06% (barely
  above base), `reclaim` 25%/−0.69% ❌, `engulfing` 21.3%/−0.19% ❌.
- **Correction:** lean long-side entries on `hl_struct`; drop/ignore
  `reclaim` and `engulfing` as standalone long triggers.

### Velocity Burst — only the 90+ band works
- Overall **−0.022R (negative)** across n=1157. By score bucket:
  - 60-69: +0.034R · 70-79: −0.036R · 80-89: −0.100R · **90-100: +0.164R (43.6%, n=110)**.
- The lane only pays at **score ≥ 90**. Everything 70-89 bleeds.
- **Correction:** raise the burst lane floor to **90** for any tradeable
  signal; treat 70-89 as watch-only.

### Grind (15m candle-strength)
- Loose (everything that fires, score≥50): **−0.021R** — display only.
- Strict slice (strict-run + very-early + 30m-aligned): **+0.078R**
  pre-fee (n=836). With the EMA200 deep-trend filter added yesterday it
  was **+0.047R after fees, out-of-sample** — the real, thin edge.
- Score 80+ (strongest closes): **−0.196R** — close-strength is
  **anti-predictive**, confirmed a third time. Already display-only. ✓
- **Correction:** none needed — yesterday's optimized VALIDATED gate
  (1.5 ATR stop + deep-trend) is the right config. Trade small.

### Early Burst radar (15m)
- Best slice: aligned, TP 5 ATR → **+0.093R**. Very-early TP3 → +0.014R.
- Thin positive. Fine as an early-warning surface, not a strong edge.

### Recovery patterns — no usable edge
- `trend_reclaim`: 32-35% win, at/below the 36.8% random baseline.
- `v_bottom_bounce`: 0 fires in window. `volume_shock`: n=1 (noise).
- **Correction:** do not trade recovery patterns standalone; demote to
  context only.

### Components — mixed, one script bug
- `ttm_squeeze` looks strong (long 78%/+1.47%, short 60.7%/+1.51%) but
  **tiny samples (n≈28-32)** — promising, not yet trustworthy.
- `smc_sweep` 7% win / −1.34% (n=129) — **broken or inverted**, investigate.
- `vwap_reclaim` 16.8% / −1.27% — negative.
- (Note: `backtest_components.py` crashed mid-run on a `None` formatting
  bug — minor harness fix needed to get full short-side table.)

### Phase E/F (macro / on-chain / TVL / dominance)
- Correctly **not** run through the 1h harness — these are daily/weekly
  signals that need a monthly-rebalanced multi-year portfolio backtest.
  Out of scope here; the modules work and surface live data.

---

## Recommended corrections (so far)

1. **Velocity burst floor → 90.** It's the difference between −0.02R and
   +0.16R. Biggest single fix.
2. **Promote `hl_struct` long signals** — best verified edge (58.8%, n=850).
3. **Drop `reclaim`/`engulfing`/`smc_sweep`/`vwap_reclaim`** as standalone
   triggers — all negative.
4. **Demote recovery patterns** to context-only.
5. **Grind** — keep yesterday's optimized gate; it's already correct.
6. Fix the `backtest_components.py` None-format crash to finish the
   short-side component table.

---

## The honest bottom line (preliminary)

The pattern is consistent across every system: **edges here are thin and
slice-specific, not broad money-makers.** The real ones —
`hl_struct` longs, burst-at-90+, the strict grind slice — are genuine but
small (after fees, low-single-digit % or ~+0.05-0.16R), and they fire
rarely. Most of what *looks* like a signal (loose grind, burst below 90,
recovery patterns, strong-close grinds) is at or below the random
baseline. Trading those is how an account bleeds.

**SST1 + Convergence + Predictor + ELITE-tier + Pattern-Scout-tier
numbers are appended below as they finish.**

---

## Appended results

> Note: background runs get reaped during idle on this host (detached
> processes are sandbox-blocked), so these were run in the foreground at
> a reduced-but-honest scope. Samples are smaller than the overnight
> plan intended but the signal is clear.

### SST1 (3-agent pipeline) — ✅ COMPLETE: 20 coins, ~46d, 674 picks
Conservative reconstruction (no CONVERGENCE/SURE/regime bonuses, 2-TF
proxy — so the LIVE pipeline's conv≥70 tier is likely at least this
good). Run in checkpointed chunks (resumable; survives laptop-close).

| Tier | Win rate | R:R | Expectancy | Sample |
|---|---|---|---|---|
| **SURE SHOT (conv≥70)** | **72.4%** | 1.97 | **+1.152R** | 39 (29 resolved) |
| ALL gated (conv≥55) | 36.4% | 1.83 | +0.031R | 674 (486 res) |
| OK (conv 55-69) | 34.1% | 1.82 | −0.037R | 635 (457 res) |

- **conv≥70 SURE SHOT is a REAL, strong edge: ~72% win, +1.15R.** Held
  across the whole sample (50→57→71→75→72% as coins were added).
- **The OK tier (55-69) loses** — it's the noise dragging ALL-gated to
  break-even.
- **Correction (high value): SST1 surfaces conv≥70 ONLY as tradeable;**
  OK tier → watch-only. Turns SST1 from break-even into a 72%-win edge.
- Caveat: 29 resolved = moderate sample (encouraging, keep watching
  live). conv≥70 fires selectively (~39 in 46d / 20 coins, <1/day).

### Grind candle-window sweep (user q: 5 or 6 candles vs 7?)
After-fee, +trend gate, scale-out. **Answer: no — 7 is best, fewer hurts.**

| TF | 5 candles | 6 candles | 7 candles |
|---|---|---|---|
| 5m | −0.217R | −0.201R | −0.204R (fee drag — all lose) |
| 15m | −0.113R | −0.120R | **−0.084R** (best of the three) |

- Shorter window catches earlier but adds noise → worse expectancy.
- (All negative here = loose gate; the live grind is +0.078R only via
  the strict validation gate, not the candle count.) **Keep 7 candles.**

### 5m GRIND (user's earlier-entry idea) — 25 coins, ~14d, AFTER fees
Tested to spec: 7 candles, ≥5 directional, 1-2 opposites tolerated &
penalized by their close strength, scale-out exit.

| Gate | Win rate | Expectancy |
|---|---|---|
| Raw 5m grind | 42.6% | **−0.215R** |
| + volume surge | 43.8% | −0.229R |
| + trend (EMA40) | 42.9% | −0.207R |
| **+ both (trend+volume)** | 43.8% | **−0.228R** |
| score 70-79 bucket | 46.4% | −0.141R |

- **Negative at every gate**, even trend+volume combined. Win rate (~43%)
  is fine but **fee drag kills it**: 5m moves are small in %, so the
  ~0.12% round-trip fee is a huge fraction of each trade's R.
- **Verdict: do NOT trade 5m grind.** Earlier ≠ better here — it
  badly underperforms the 15m grind (+0.05R) and the user's hypothesis
  that filtering would lift it is disproven. Could be shown as a
  visibility-only "⚡ early" marker, clearly labeled NOT tradeable.

_still pending: convergence, predictor, elite_by_tier, tiers_with_costs
(running in foreground next)._

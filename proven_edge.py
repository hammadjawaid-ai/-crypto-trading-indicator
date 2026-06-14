"""Proven-edge reference — the REAL walk-forward stats we measured.

These numbers come from this project's own backtests (backtest_elite.py,
backtest_velocity_burst.py, backtest_convergence.py, the 150-coin
lane-confluence run, etc.). They are recorded here so the UI can show
the user WHY a signal type is trusted — for justified sizing, not as a
new signal.

HONEST SCOPE:
  - Walk-forward, no lookahead, but PAPER-PERFECT execution: no fees,
    no slippage, no partial fills. Live results run a little worse.
  - Crypto futures history is short and regime-dependent; these edges
    were measured over recent months, not 5-10 years. Treat them as
    "what held up recently," not eternal truths.
  - We deliberately do NOT quote CAGR or Sharpe for the whole system —
    it mixes many signals that change over time, so a single
    portfolio CAGR would be misleading. Per-signal win rate +
    expectancy is the honest unit.

Each entry: name, win_rate (%), expectancy (R per trade), sample (n),
best (when it works), breaks (what kills it).
"""

# R convention: a win pays the plan's reward:risk; expectancy is the
# average R per trade including losers.
EDGES = [
    {
        "name": "3+ lane confluence (ELITE)",
        "win_rate": "53-66%",
        "expectancy": "+0.15 to +0.40R",
        "sample": "n=124 (3-lane), n=9 (4+ lane)",
        "best": "When 3+ independent lanes agree on the same side — "
                "the only lane-count band with a real edge.",
        "breaks": "1-2 lane setups (43% / 42% win) — below coin-flip "
                  "after costs. That's why singles are gated out.",
    },
    {
        "name": "CONVERGENCE meta-filter",
        "win_rate": "baseline +6.8pp",
        "expectancy": "positive vs baseline",
        "sample": "12-bar forward, multi-month",
        "best": "Pattern Scout + Setups + regime + 4h trend all line "
                "up on one coin. Rare (0-3/day) — rarity is the edge.",
        "breaks": "Choppy/transition tape where the sub-systems "
                  "disagree; it simply doesn't fire (correctly).",
    },
    {
        "name": "Velocity burst",
        "win_rate": "42% (90+ band)",
        "expectancy": "+0.127R (90+) · -0.172R (78-89)",
        "sample": "n=740 (30 coins x 90d, 1h)",
        "best": "90+ band = standalone edge (extreme volume+range "
                "breakout). The earlier 78-89 band is now allowed in "
                "as a CONFLUENCE contributor only — it surfaces a "
                "trade ONLY when the quality gate / multi-TF gate / "
                "Sure Shot consensus also confirm. Catches the move "
                "~1 candle sooner without trading the losing band "
                "alone.",
        "breaks": "78-89 burst with nothing else confirming — loses "
                  "standalone (-0.172R), so the downstream gates hold "
                  "it back unless 2+ systems agree.",
    },
    {
        "name": "dist_top (distribution-top SHORT)",
        "win_rate": "edge at parabolic tops",
        "expectancy": "positive at peaks",
        "sample": "leading-signal lane (floor 50)",
        "best": "Parabolic tops with RSI overbought + price far above "
                "EMAs — catches NEAR/INJ-style -25% drops early.",
        "breaks": "Strong uptrends — shorting a coin that keeps "
                  "ripping. Regime tilt + multi-TF gate guard this.",
    },
    {
        "name": "early_trend (aggressive)",
        "win_rate": "lower (earlier = less confirmation)",
        "expectancy": "speculative — not yet walk-forward proven",
        "sample": "new lane (2026-06)",
        "best": "Catching a turn AS IT STARTS (EMA reclaim + RSI cross "
                "+ MACD flip + volume). For aggressive early entries.",
        "breaks": "Fakeouts — the move reverses before it confirms. "
                  "Trade it smaller; it's a catcher, not a sure thing.",
    },
    {
        "name": "Tier scaling (STANDARD->MAX)",
        "win_rate": "rises with tier",
        "expectancy": "R:R 1.67 -> 2.50 by tier",
        "sample": "tier = score + strong-lane count",
        "best": "MAX/HIGH tiers get wider targets (3.0/2.5x ATR) "
                "because higher conviction sustains bigger moves.",
        "breaks": "Forcing MAX targets on STANDARD setups — they "
                  "don't travel that far. Targets are tier-matched.",
    },
]

DISCLAIMER = (
    "Walk-forward, no lookahead — but paper-perfect (no fees / "
    "slippage), measured over recent months, not 5-10 years. Live "
    "runs a little worse. We don't quote a single system CAGR/Sharpe "
    "because the signal mix changes — per-signal win rate + "
    "expectancy is the honest unit."
)

"""🎮 DEMO ZONE — GEN 6: the $1,500 WILD run (user 2026-08-23).

A simulated REAL account run by the 24/7 worker. GEN 6 rules, all on
the user's explicit order: $1,500 start, 10 slots, one per coin,
Bybit taker fees both sides, 48h time-stop. The pool is EXACTLY
four streams — 💥⚡ STRONG TRIGGER breaks and 🔄 RE-RUNs (second-leg
breaks + re-qualified elite) own at least 6-7 of the 10 seats; the
💎 elite family holds AT MOST 4 together — 💎✅ confirmed entries 2
seats (the higher-weighted construct) + raw elite cream 2 seats.
Sizing is wild by design: each slot margins balance/10 and levers
5x-10x by signal grade. TP1 half-bank + BE, trail to TP2, and
the strength-aware smart exit only steps in when a move is fading.

The 10-day question voiced: does $1,500 honestly reach $2,500? Every
open/close buzzes Telegram; the page shows the equity curve and every
position. Simulated only — no real orders.
"""
from __future__ import annotations

import json
import os
import time

import config

# 2026-08-10 THE RESET BUG, fixed: this file used to sit on the
# container's EPHEMERAL disk, so every deploy wiped the ledger (user:
# "it should NEVER reset from any source until I hard-reset myself").
# Now on the persistent disk via config.state_path (STATE_DIR=/var/data
# on Render) — the same location that keeps the desk's records alive
# across deploys. The ONLY reset path left is bumping GEN below, which
# happens exclusively on the user's explicit order.
STATE_FILE = os.environ.get("DEMO_STATE") or \
    str(config.state_path(".demo_account.json"))
# generation marker — bump ONLY on the user's explicit hard-reset
# order. GEN 3 = 2026-08-10 ("reset again, Monday to Monday").
# GEN 4 = 2026-08-15 ("reset demo trading lets start fresh again now
# based on the changes") — fresh week on the new ladder: 💎 elite
# conviction (approved-only) wins all, 🔮✅ kronos approved right
# behind, B-stocks out of the universe, and the strength-aware
# smart exit with the TP2 trail below.
# GEN 5 = 2026-08-15 later the same day (user order 6: "restart demo
# and remove trend rider from it it sucks") — 🌊 TREND RIDER out of
# the money, and the pool trimmed to exactly the named five: 💎 elite
# conviction (approved) · 🏆 top conviction · 🌟 early elite · 🔮✅
# kronos approved · ✅🔥 take now hot. Surge and fresh lose their
# money seats too (not on the user's list).
# GEN 6 = 2026-08-23 ("even in bull it lost me money... this time we
# go wild"): $1,500 start, 5 slots, ONLY the desk's proven-hot
# streams spend — 💥⚡ STRONG TRIGGER breaks + 🔄 RE-RUN (second-leg
# breaks / re-qualified elite) on TOP priority, 💎 elite conviction
# MAX/HIGH (approved) secondary. NOTHING else gets a seat. Sizing is
# the wild part: each slot margins balance/5 and levers 5x-10x by
# signal grade, so a normal 1R swing is ~$50-200 instead of $10-20.
# TP/SL and the smart exit are UNCHANGED — ideally SL/TP resolves;
# the smart exit only steps in when the move is fading.
# GEN 7 = 2026-08-26 ("lets rerun this demo trading from today its
# not making money"): fresh $1,500 ledger, new seat map — 5 top-
# stream seats (💥⚡ strong triggers + 🔄 re-runs) · 3 🎯 BEST-OF-
# BEST seats (💎 BEST ZONE cards carrying the telegram confidence
# score >= 80; 98+ outranks everything in that lane) · 2 💎 elite-
# family seats (elite cream + 💎✅ confirmed/re-entry, max scores).
# Slots stay a CEILING, not a quota. NEW ROTATION RULE (user: "if
# the signals get healthier from other coins we should close the
# weak ones"): when a stronger signal is waiting and its seats are
# full, a position whose SIGNAL HAS DIED is rotated out — banked if
# positive, cut if negative; a losing position stands ONLY while
# its signal stays healthy.
# GEN 8 = 2026-09-05 ("demo trading reset to 1500... 8 slots with
# maximum leverage of upto 10x per trade... strong triggers priority,
# then the confidence duo bands we measure success, and the waking on
# our coins. no closing until risk is involved, ride to tp1, close,
# and if the momentum is still there open the trade again").
# GEN 9 = 2026-09-06 ("rotate signal remove it. start again with 1500
# ... maximum 8 slots and anyone can take any place" + the named seven
# streams). Open seating: no family caps, rotation OFF, rank floor
# lowered so any listed stream can seat on its own merits.
GEN = 16
START_BAL = 2000.0
# 🎮 GEN 16 (user 2026-09-14: "Demo Trading Start Again now. We will
# have only this and no limit on slots can be 20 at a time depending
# on the signals with leverage of 10x of our total account 2000
# dollars. We are taking trades only on the following: 1. Early Lanes
# and Early Movers · 2. Best Zone · 3. TRIG×KR"). Fresh $2,000 ledger,
# 20 seats, flat 10x, OPEN SEATING (no per-stream caps — his words).
# MEASURED on .state_backup_0913, last 45d closed desk ledgers — the
# three new streams are the desk's highest-volume POSITIVE tiers:
#   early_movers  n=639  43.0%  +0.154R  14.2/day  stop 3.25%
#   early_lane    n=604  42.5%  +0.151R  13.4/day  stop 3.25%
#   best_board    n=657  40.8%  +0.122R  14.6/day  stop 3.34%
#   trig_strong_kr n=94  68.1%  +0.047R   2.1/day  stop 2.21%
# Note the shape: these are LOW win-rate / POSITIVE expectancy lanes
# (the opposite of GEN 15's roster) — ~42% win is normal and healthy
# here, the money comes from the winners running past 1R. Judge this
# generation on R, never on win%.
# SIZING: margin = 2000/20 = $100 a seat, x10 = $1,000 notional; at
# each lane's median stop that is ~$32 risk (1.6% of equity) per
# trade, so a full 20-seat board carries ~32% heat — just inside the
# 35% cap, and 20 x $100 = the whole bank as collateral by design.
# 🎮 GEN 14 (user 2026-09-13: "restart demo trading to 1500 — now it
# will only take trades on the following: 1. STRONG TRIGGER plain, all
# confidence scorings but prioritising conf>=65 · 2. ELITE STAR ·
# 3. KR-STRONG PREMIUM · 4. TRIG×KR any conf"). FOUR streams, fresh
# ledger. Two of them (plain trigger, TRIG×KR) are MUTED on Telegram
# by the same order — buzz and money are separate here by design.
# MEASURED on the 2026-09-13 backup, last 45d closed (.state_backup_
# 0913), which is what the risk sizes below are built from:
#   KR-STRONG PREMIUM   n= 91  78.0%  +0.887R  2.02/day  kelly 61.4%
#   STRONG TRIG >=65    n=110  69.1%  +0.117R  2.44/day  kelly 21.0%
#   STRONG TRIG  <65    n=199  64.8%  -0.101R  4.42/day  kelly  0.0%
#   TRIG×KR             n= 94  68.1%  +0.047R  2.09/day  kelly  9.6%
#   ELITE STAR (fwd)    n= 17  52.9%  +0.062R  0.38/day  kelly  5.9%
# The user first ordered the trigger at ALL bands, then revised to
# ≥65 ONLY in the same message once the sub-65 number (-0.101R over
# 199 trades) was on the table — CONF_GATE enforces that.
# 🎮 GEN 15 = the same four streams, SIZING ENGINE SWAPPED (user
# 2026-09-13: "leverage to drive size — bigger positions at 10x, the
# way GEN 10-12 worked... yes thats what i want"). Fresh ledger so one
# ledger measures one engine. Size now = (balance / MAX_SLOTS) x the
# stream's leverage; dollar risk is the by-product of that notional
# and the stop width. On a $1,500 bank with 10 seats that is $150
# margin a seat: 10x -> $1,500 notional, 8x -> $1,200, 6x -> $900.
# Using each stream's MEDIAN stop from the table above, the resulting
# risk per trade lands at: trigger 2.5% · premium 2.6% · trig×kr 1.8%
# · star 2.7% at 6x / 3.6% at 8x — the star is the biggest risk on
# the board despite the lowest leverage, because its stops are twice
# as wide (4.55% median) as everything else's.
# 🎮 GEN 13 (user 2026-09-13: "add KR-STRONG PREMIUM and STRONG
# TRIGGER to the family... make me 1500 to 3000 dollars in 5 days...
# pick the trades whichever you want no matter how many slots... goal
# is 3000 in 5 to 10 days"): the TARGET generation. Ten streams, and
# the sizing is ENGINEERED to the goal instead of a flat margin —
# risk-per-trade by stream = 0.20 x each stream's own Kelly fraction
# on its last-45d closed ledger (.gen13_size.py), floor 2% / cap 10%
# of equity, notional = risk / stop distance, 10x collateral so the
# seats fit. Portfolio HEAT cap 35% (sum of open risk) so one BTC
# flush can't take the account; daily loss rail 15% of equity stops
# NEW entries; no gain cap. Haircut Monte Carlo (.gen13_haircut.py:
# edges halved, 6 fills/day, 15% flush days): P(3k<=10d) ~43%,
# median day-10 ~$2.1k, P(50% drawdown) ~19% — the honest odds.
# Rosy model (full edges, every fire filled): ~97% — not believed.
TRIG_CONF_PRIORITY = 65.0     # the CONF_GATE floor, kept named
# ⚠️ GEN 15: RISK_PCT / risk_for are GONE — leverage drives size again
# (user 2026-09-13). Dollar risk is now an OUTPUT of leverage x stop
# width, recorded on every position as risk_usd / risk_pct so the
# HEAT_CAP guard and the boards can still read it. To go back to
# risk-first sizing, restore RISK_PCT and the GEN 13 block in
# try_open — both are in git history at commit 3023f10.
HEAT_CAP = 0.35              # open risk (sum of risk_usd) / equity
# 🎯 GEN 15 NEAR-TP BANK — the ONLY exit that is neither SL nor TP
# (user 2026-09-13: "just a smart exit when its close to tp and you
# sense momentum is dropping"). Applies to EVERY stream now; it was
# elite_star-only from GEN 11. Pure price geometry, no outside feed:
# the trade printed NEAR_TP_PEAK of the way to TP1, then rolled back
# to NEAR_TP_FADE or less while still in profit. Loosen the bank by
# raising FADE; make it rarer by raising PEAK.
NEAR_TP_PEAK = 0.85          # how far it must have travelled
NEAR_TP_FADE = 0.60          # how far it has given back
# 📐 rr re-checked at the LIVE entry for streams whose edge IS an rr
# law — (lo, hi) half-open, None = unbounded on that side. The star
# profile was measured at TP1 within 1.2R; the premium cell at
# 1.0-1.5R (under 1R = 30%/-0.09R, over 1.5R = 11%/-0.58R).
# GEN 16: the two rr-law streams (star, premium) are out of the
# roster, so no seat re-checks rr at open. Restore their bounds here
# if either ever returns.
RR_OPEN_BOUNDS: dict = {}
LEV_GEN13 = 10.0             # fallback only; the GEN 14 per-stream
                             # ladder lives in lev_for() below
DAY_MAX_LOSS_PCT = 0.15      # of day-start equity; stops NEW seats
# 🎮 GEN 12 (user 2026-09-12 "gen 12 do the changes but edit the
# slots accordingly by yourself; elite star every band; add kr agree
# and elite star or elite conviction"): ONE SEAT PER MEASURED FAMILY,
# each in its proven band — built from the full-history scorecard +
# the Kronos×conf map. Sources: elite_star (every band) · elite_kr
# (💎🔮 elite fire + KR-STRONG/TRIG×KR backing, conf 40-54 — the
# +1.141R n=21 cell — RIDE exits, see RIDE_SRC) · my-watch confirm
# (>=45) + waking (40-54) · moonshot (55-64) · kr_strong (55-64,
# its native band) · strig_kr (TRIG×KR, the trigger family's
# form-green half; plain trigger benched from money until its 14d
# expectancy re-greens) · sniper2 (golden cells, both ways).
# Rails: +$500 / -$150 per 24h stop NEW entries. Slots 7 max, trim
# to 5 on red/thin days. Frozen for 30 closed before any verdict.
# GEN 12.2 (user 2026-09-13: "increase the demo slots to 10 and
# losing per day to 250 dollar and earning to 500+")
# GEN 13: gain cap OFF (a winning day keeps trading toward the
# target); loss rail is DAY_MAX_LOSS_PCT of equity, computed in
# try_open — DAY_MAX_LOSS below is only the legacy floor.
DAY_MAX_GAIN = float("inf")
DAY_MAX_LOSS = 250.0
MIN_SLOTS = 20
# 💎🔮 RIDE EXITS (elite_kr only): the +1.14R record was earned by
# RIDING — half-bank at TP1, stop to BE, trail toward TP2. Banking
# 100% at TP1 would cut the exact riders that make the cell.
# GEN 14: no RIDE seats — the rider cell (elite_kr) is out of the
# roster. Exits are SL-or-bank-100%-at-TP1 everywhere except ⭐
# elite_star's near-TP bank, which keeps its own block in manage().
RIDE_SRC: set = set()
# 6 -> 10 (user 2026-08-23 second follow-up: "instead of 6 we have
# 10 slots now and 7 for strong triggers and 3 for elite
# conviction"). A CEILING, not a quota — the MIN_RANK floor still
# gates every slot. Elite's 3-seat cap below guarantees the top
# streams (strong triggers + re-runs) always keep >= 7 seats.
# GEN 16: 20 seats ("no limit on slots, can be 20 at a time depending
# on the signals"). MAX_SLOTS is also the SIZE DIVISOR — margin =
# balance / 20 = $100 on a $2,000 bank, x10 leverage = $1,000
# notional a seat. Lowering this number makes every position bigger.
MAX_SLOTS = 20
# The earlier 6->8 good-day overflow is absorbed by the 10-slot
# base; no seats beyond 10.
MAX_SLOTS_HOT = 8
# GEN 6 WILD SIZING (user 2026-08-23: "more leverage 5x to 10x...
# 50-200 dollars per trade... notions as per 1500 in the bank
# accordingly"): per-slot margin = balance / MAX_SLOTS, leverage
# graded by the validated quality tells — never a flat max.
LEV_BASE = 5.0                 # fallback for anything unmapped
LEV_WATCH = 6.0                # GEN 10.1: ⚡🟢 my-watch lanes (user)
LEV_MID = 8.0                  # GEN 10: duo + trig×kr
LEV_MAX = 10.0                 # GEN 10.1: triggers + sniper + moonshot
                               # (validated 64.7% · +0.288R)
FEE = 0.00055                  # Bybit taker, per side
TIME_STOP_H = 72     # GEN 8: seat hygiene only — the
                     # user's exit is SL or TP1
# GEN 5 (user order 6): 🌊 TREND RIDER is OUT of the demo — its
# per-source hold/slot/smart-exit carve-outs go with it.
TIME_STOP_BY_SRC: dict = {}
# GEN 7 seat map (user 2026-08-26): 5 top-stream · 3 best-of-best ·
# 2 elite family. Per-src and family caps below enforce it; counted
# by plan-winning source.
# GEN 14 per-stream seat caps: the plain trigger fires 18.8x/day
# against the premium cell's 2.0x, and it sits ABOVE it in the user's
# ladder — without a cap it would hold every seat and spend the whole
# 35% heat budget before a premium fire ever arrived. Caps keep each
# stream's lane open. Revert to open seating: {}.
# GEN 16: OPEN SEATING — the user asked for "no limit on slots", so
# no per-stream caps; best rank wins a free seat. CONSEQUENCE HE WAS
# TOLD: early lanes/movers/best fire ~14/day each against TRIG×KR's
# ~2/day, so on a busy board TRIG×KR may rarely seat. Restore caps
# here if that lane goes dark.
MAX_PER_SRC: dict = {}
# 💥 TOP FAMILY: strong triggers + re-runs share 5 seats.
# GEN 13: family cap OFF — open seating, best rank wins.
TOP_FAMILY: set = set()
TOP_FAMILY_CAP = 8
# 💎 ELITE FAMILY: raw elite cream + confirmed/re-entry share 2.
ELITE_FAMILY: set = set()
ELITE_FAMILY_CAP = 0
# 🔄 ROTATION (GEN 7): when a qualified candidate is blocked by a
# full board/family, a position whose signal has DIED this cycle
# (its coin+side no longer active in ANY pool) may be rotated out —
# positives banked first, then negatives cut. Healthy signals are
# NEVER rotated, and at most this many rotations happen per cycle.
ROTATE_MAX = 0   # GEN 9 user order: rotation REMOVED
SMART_EXIT_SKIP: set = {"early_lane", "early_movers", "best_zone",
                        "strong_trigger", "strig_kr"}      # GEN 16
# GEN 12: kronos smart-exit off for all. Exits: SL-or-TP1-bank-100%
# everywhere EXCEPT ⭐ elite_star's near-TP bank (own block) and
# 💎🔮 elite_kr's RIDE (half-bank TP1 + BE + trail, in the TP1
# branch) — each matching how its record was earned.
# 🧠 STRENGTH-AWARE SMART EXIT + TRAIL (user 2026-08-15: "smart exit
# should have a trailing method... loosen a bit if the signal
# strength is good... let them ride to tp and trail to tp2 if they
# are good enough — use the brain"). The brain's strength read = the
# signal's own quality at entry: top-class source (💎 elite_conv /
# 🔮✅ kr_approved), multi-system agreement, or a big score.
# GEN 6: every money stream is a proven-hot construct, so all three
# class as STRONG — the smart exit gives them room (scratch-stop /
# tightened trail) instead of banking early. User 2026-08-23:
# "ideally it should stop at sl and tp set... smart exit only if you
# see the movement is fading and it wont push any further."
STRONG_SRC = {"elite_conv", "kr_approved", "strong_trigger", "rerun",
              "elite_confirm"}
STRONG_SCORE = 85.0            # score >= this counts as strong
STRONG_AGREE = 2               # >= this many agreeing systems counts
TRAIL_LOCK = 0.5               # after TP1: stop locks this share of
                               # the PEAK open gain (ratchet, rides
                               # toward TP2 instead of flat BE)
TRAIL_LOCK_FLIP = 0.75         # kronos flips against a STRONG runner
                               # after TP1: tighten the lock, keep
                               # riding (weak signals still bank)


def _is_strong(p) -> bool:
    """The brain's verdict on this position's signal strength."""
    return (p.get("src") in STRONG_SRC
            or int(p.get("agree") or 1) >= STRONG_AGREE
            or float(p.get("score") or 0) >= STRONG_SCORE)
ZONE_MAX = 0.25                # skip if >25% of entry->TP1 gone
STOP_MAX_PCT = 0.25            # skip stops wider than 25%
# quality floor (my call, user granted latitude 2026-08-09): an empty
# slot is better than a mediocre trade. Rank ~100 needs either a
# top-record system, a strong score, or multi-system agreement.
MIN_RANK = 85.0  # GEN 9: anyone can take any place
# construct-class weights — the user's chosen seven (2026-08-09:
# "early elite, kronos approved, surge, ignition, fresh movers, top
# conviction and moonshot — worth trying"; PRIME/others dropped from
# the demo on his call). Weighted by each tier's live desk record.
# IGNITION dropped 2026-08-10 on user call ("we should skip
# ignition" — at-fire entries, the weakest construct class).
# GEN 5 pool (user order 6, 2026-08-15: "we already told you what we
# want to have — top conviction, early elite, kronos approved and
# take now hot" + elite conviction on top by standing order). 🌊
# TREND RIDER removed ("it sucks" — 3-of-4 losers didn't fit);
# surge and fresh lose their seats too (not on the named list).
# GEN 6 pool (user 2026-08-23: "we only go with Strong triggers and
# Re Run, and Elite conviction max... elite conviction max or high
# can be secondary, top priority is strong triggers and reruns...
# nothing else should be a part of demo trading"): exactly three
# streams, weighted by their LIVE desk records —
# GEN 10 RULES (user 2026-09-07: "remove king pair and early best...
# dont change the current standing just update for what we are doing
# ahead"): GEN stays 9 ON PURPOSE — bumping it would reset the
# balance and history, and the order was rules-forward-only. The
# roster is the user's five picks off the live conf chart, each
# stream seated ONLY in its measured-green confidence band(s) — see
# CONF_GATE below. pair_king and early_best lose their seats (king
# pair 33%/-0.355R live; early elite 85+ 19%/-0.514R).
# GEN 12 priority: star, the KR-elite rider cell, my watch, then
# the volume machines.
# GEN 14 ladder = the user's own numbering (2026-09-13). The measured
# ranking would be premium first by a wide margin, so MAX_PER_SRC caps
# below stop the 18.8-fires/day trigger firehose from eating the heat
# budget before the premium cell can seat.
CLASS_W = {"early_lane": 105,     # 1a. the user's first pick
           "early_movers": 104,   # 1b. its non-lane half
           "best_zone": 103,      # 2. 💎 BEST TRADE ZONE
           "strong_trigger": 102,  # 3. 💥 added 2026-09-14
           "strig_kr": 101}       # 4. 💥🔮 TRIG×KR
# 🎯 CONF-BAND SEAT GATES (user 2026-09-07, read off the live desk
# ledger): a stream's candidate takes a seat ONLY when its conf falls
# in a band that measured green on its own closed trades. Bands are
# half-open [lo, hi). Momentum re-entries (chain > 0) are exempt —
# they qualified at original entry and re-arm on the burst gate.
#   strong_trigger  40-54 (69% n=70) + 65-84 (83% n=48)
#   strig_kr        40-54 + 65-84 (mirrors its parent; thin, proving)
#   moonshot        55-64 (75% / +0.933R n=28)
#   sniper          55-64 (sniper2 golden-cell band, 5/6 live)
#   pw_waking       40-54 (62% / +0.584R n=26)
#   pw_confirm      40-54 (75% / +0.823R n=12, thin — user add
#                   2026-09-07) + 65-84 (62% / +0.446R n=29)
#   duo_band        85+   (the DUO cell by construction)
# GEN 12 gates — each stream in its MEASURED band. elite_star
# ungated ("every band", user 2026-09-12); strig_kr ungated (green
# in every band, thin per-band); sniper2 self-gated by golden cells.
# GEN 14 gates. Star "every band" and TRIG×KR "any conf" stay open;
# the premium cell is gated by its own profile (LONG + TP1 1.0-1.5R
# + calm kronos) upstream in the worker.
# user 2026-09-13 (revised same message): the plain trigger takes
# conf >= 65 ONLY — the all-bands version was measured at +0.006R
# because its sub-65 half runs -0.101R (n=199). Revert to all bands:
# delete the strong_trigger line.
# 🎯 GEN 16.1 CONF BANDS (user 2026-09-14: "for demo trading with
# this confidence score only"). Half-open [lo, hi); chain>0 re-entries
# exempt; a gated stream with conf None takes no seat.
# ⚠️ MEASURED WARNING GIVEN TO HIM AT WIRE TIME — two of these four
# gates cost money on the last 45d of closed desk trades:
#   early_lane   conf>=85  +0.096R  3.0/day  vs ALL +0.151R 13.4/day
#   early_movers conf 85+  +0.088R  3.0/day  vs ALL +0.154R 14.2/day
#   early_movers conf 55-64 is n=3 in 45 days — effectively empty
#   strong_trigger conf>=65 +0.117R vs ALL +0.006R   <- gate EARNS
#   strig_kr       conf>=40 +0.077R vs ALL +0.047R   <- gate EARNS
# The early lanes' edge is spread across every band, so gating at 85
# cuts volume ~4x AND expectancy ~40%. His call, his system; revert
# by deleting the two early_* lines.
# best_zone stays UNGATED — he did not name a band for it, and its
# fires carry conf 85-98 natively so a gate would be inert anyway.
CONF_GATE: dict = {
    "early_lane": ((85.0, 1000.0),),
    "early_movers": ((55.0, 65.0), (85.0, 1000.0)),
    "strong_trigger": ((65.0, 1000.0),),
    "strig_kr": ((40.0, 1000.0),),
}
# GEN 6: no conditional seats — the pool is exactly the named three.
CONDITIONAL_SRC: set = set()
# 2026-08-11 user call: 🚀 MOONSHOT removed from the demo menu (desk
# record 9 closed / −0.65R, and those closes pre-date the top-30
# validation restrictions — it hasn't earned a money seat yet). 🥇
# PRIME was already out (2026-08-09). Both keep proving on the desk;
# they return only when their OWN live record turns green.


def lev_for(src: str, conf=None, burst=None) -> float:
    """GEN 16 leverage (user 2026-09-14: "leverage of 10x"): a flat
    10x on all four lanes. Leverage DRIVES SIZE in this engine —
    margin = balance / MAX_SLOTS, notional = margin x this number —
    so 10x on a $100 seat is a $1,000 position, and the dollar risk
    that follows is notional x the stop distance.
    It also caps stop width: try_open refuses stop_pct >= 0.8 / lev,
    i.e. stops wider than 8% at 10x. The early lanes' median stop is
    3.25%, so that guard bites only on the genuinely wild plans.
    ONE source of truth — the 💸 live executor calls this too.
    (The GEN 15 star 6x/8x-by-burst ladder is in git at 2a56c58.)"""
    return {"early_lane": 10.0, "early_movers": 10.0,
            "best_zone": 10.0, "strong_trigger": 10.0,
            "strig_kr": 10.0}.get(src, LEV_GEN13)


def load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict) and "balance" in s \
                and s.get("gen") == GEN:
            return s
    except Exception:
        pass
    return {"gen": GEN, "balance": START_BAL, "start": START_BAL,
            "started_at": time.time(), "open": [], "closed": [],
            "equity_hist": []}


def save(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def rank_candidates(pools: dict, tier_form: dict) -> list:
    """pools: {stream: [signal dicts]} -> ranked candidates.

    CONFLUENCE RULE (user 2026-08-09: "if most of the system agree and
    the confidence score is highest we take that trade"): the same
    coin+side appearing in MULTIPLE systems gets +25 rank per extra
    agreeing system — agreement dominates the slot race. The plan
    (entry/stop/TPs) comes from the highest-class system that fired it.
    """
    agg: dict = {}
    for name, sigs in pools.items():
        # 🎮 GEN 14 ROSTER GUARD: CLASS_W *is* the roster. A stream
        # that is not on it takes no seat, no matter what a caller
        # puts in the pools — previously an unlisted name inherited a
        # default weight and could seat on rank alone.
        if name not in CLASS_W:
            continue
        w = CLASS_W[name]
        form = max(-10.0, min(float(tier_form.get(name, 0.0) or 0.0),
                              10.0))
        for p in sigs or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            if not sym or side not in ("LONG", "SHORT"):
                continue
            # 🏦 B-stock money gate (user 2026-08-17: "give them real
            # size when validated") — tokenized symbols get NO demo
            # money until their cohort validation flips the flag.
            if sym in getattr(config, "TOKENIZED_STOCKS", ()) \
                    and not getattr(config, "BSTOCK_VALIDATED", False):
                continue
            # 🎯 GEN 10 conf-band seat gate (user 2026-09-07): each
            # stream trades ONLY in its measured-green band(s). A
            # candidate with no conf can't prove its band — no seat.
            # chain > 0 = momentum re-entry, exempt by design.
            _bands = CONF_GATE.get(name)
            if _bands is not None and not p.get("chain"):
                try:
                    _gcf = float(p.get("conf"))
                except (TypeError, ValueError):
                    _gcf = None
                if _gcf is None or not any(
                        lo <= _gcf < hi for lo, hi in _bands):
                    continue
            try:
                e = float(p.get("entry") or 0)
                st = float(p.get("stop") or 0)
                t1 = float(p.get("tp1") or 0)
            except (TypeError, ValueError):
                continue
            if min(e, st, t1) <= 0 or e == st or t1 == e:
                continue
            sc = float(p.get("score") or 60)
            t2 = p.get("tp2")
            base_rank = w + sc / 2 + form
            k = (sym, side)
            cur = agg.get(k)
            if cur is None:
                agg[k] = {"symbol": sym,
                          "base": p.get("base")
                          or sym.replace("USDT", ""),
                          "side": side, "entry": e, "stop": st,
                          "tp1": t1,
                          "tp2": float(t2) if t2 else None,
                          "src": name, "score": sc, "w": w,
                          "srcs": {name}, "rank": base_rank,
                          "burst": float(p.get("burst") or 0),
                          "conf": float(p.get("conf") or 0),
                          "kr_ok": bool(p.get("kr_agree"))}
            else:
                cur["srcs"].add(name)
                cur["rank"] = max(cur["rank"], base_rank)
                cur["score"] = max(cur["score"], sc)
                cur["burst"] = max(float(cur.get("burst") or 0),
                                   float(p.get("burst") or 0))
                cur["conf"] = max(float(cur.get("conf") or 0),
                                  float(p.get("conf") or 0))
                cur["kr_ok"] = cur.get("kr_ok") \
                    or bool(p.get("kr_agree"))
                if w > cur["w"]:        # higher-class plan wins
                    cur.update({"entry": e, "stop": st, "tp1": t1,
                                "tp2": float(t2) if t2 else None,
                                "src": name, "w": w})
    out = list(agg.values())
    # 🔀 the either/or gate: conditional-only candidates trade ONLY
    # with a kronos agreement or a second agreeing model.
    out = [c for c in out
           if not (c["srcs"] <= CONDITIONAL_SRC
                   and len(c["srcs"]) < 2
                   and not c.get("kr_ok"))]
    for c in out:
        c["agree"] = len(c["srcs"])
        bonus = 25 * (c["agree"] - 1)
        # GEN 6 priority ladder (user 2026-08-23: "top priority is
        # strong triggers and reruns... elite conviction max or high
        # can be secondary"): a hard class sort, not just points —
        # any candidate carrying a top stream sorts ABOVE every
        # elite-only candidate, no matter the rank it stacked. The
        # A-grade burst (>=85, validated) orders top-stream cards
        # among themselves.
        # GEN 13: the hard top-sort is OFF — CLASS_W is the whole
        # priority ladder now (premium > star > rider > my-watch >
        # moonshot > kr_strong > trig×kr > plain trigger > sniper).
        _top6 = set()
        if _top6:
            bonus += 80
        if float(c.get("burst") or 0) >= 85:
            bonus += 40
        # GEN 7: 🎯 98+ confidence = the true best-of-best — outranks
        # everything inside its 3-seat lane
        if "best_conf" in c["srcs"] and float(c.get("conf") or 0) >= 98:
            bonus += 30
        c["rank"] += bonus
        c["top"] = 1 if _top6 else 0
        c["srcs"] = ",".join(sorted(c["srcs"]))
    # GEN 13: HARD class ladder — the plan-winning stream's CLASS_W
    # sorts first (premium > star > rider > ...), score/agreement
    # order candidates only within a class. Heat and collateral go
    # to the best-measured stream first.
    out.sort(key=lambda x: (-x.get("top", 0),
                            -CLASS_W.get(x.get("src"), 30),
                            -x["rank"]))
    return out


def try_open(state: dict, cands: list, live_fn, active=None):
    """Fill free slots with the best in-zone candidates. Real-account
    rules: seat caps, one per coin, margin sized off the CURRENT
    balance, entry fee paid immediately.

    GEN 7 ROTATION (user 2026-08-26: "if the signals get healthier
    from other coins we should close the weak ones"): `active` = the
    (symbol, side) pairs with a live signal this cycle. When a
    qualified candidate is blocked by a full board/family/source, ONE
    position whose signal has DIED may be rotated out — banked if
    positive, cut if negative. Healthy signals are never rotated;
    at most ROTATE_MAX rotations per cycle.
    Returns (opened, rotated)."""
    opened, rotated = [], []
    # 🚧 GEN 11 DAILY RAILS (user 2026-09-10: "cap of 500 dollars
    # daily maximum earn and 150 dollars maximum per day lost — no
    # trades to be taken if that hits"): realized P&L over the last
    # 24h decides whether NEW seats open. Open positions always keep
    # their SL/TP — the rails stop entries, never management.
    _day0 = time.time() - 24 * 3600
    _day_pnl = sum(float(c9.get("pnl") or 0)
                   for c9 in state.get("closed") or []
                   if float(c9.get("closed_at") or 0) >= _day0)
    # GEN 13: the loss rail scales with the account (15% of the
    # day-start equity) so it means the same thing at $1.5k and $3k.
    _eq_day0 = max(1.0, float(state["balance"]) - _day_pnl)
    _loss_rail = DAY_MAX_LOSS_PCT * _eq_day0
    if _day_pnl >= DAY_MAX_GAIN or _day_pnl <= -_loss_rail:
        return [], []
    # 🪑 dynamic seats (user: "10 slots at the best days of winning
    # ... when the signals are low we can trim down to 5 or 6"):
    # full 10 only on a non-losing day WITH rich signal flow; else 6.
    _slot_cap = (MAX_SLOTS if (_day_pnl >= 0 and len(cands) >= 6)
                 else MIN_SLOTS)
    held = {p["symbol"] for p in state["open"]}
    src_n: dict = {}
    for p in state["open"]:
        src_n[p.get("src")] = src_n.get(p.get("src"), 0) + 1

    def _rotate(scope=None):
        if active is None or len(rotated) >= ROTATE_MAX:
            return False
        best = None
        for p in state["open"]:
            if scope is not None and p.get("src") not in scope:
                continue
            if (p["symbol"],
                    (p.get("side") or "").upper()) in active:
                continue        # signal healthy — never rotated
            try:
                lv = float(live_fn(p["symbol"]) or 0)
            except Exception:
                lv = 0.0
            if lv <= 0:
                continue
            r0 = float(p.get("risk0") or 0) or \
                abs(p["entry"] - p["stop"]) or p["entry"] * 0.02
            pr = (lv - p["entry"]) * \
                (1 if p["side"] == "LONG" else -1) / r0
            key = (0 if pr >= 0 else 1, -pr)
            if best is None or key < best[0]:
                best = (key, p, lv, pr)
        if best is None:
            return False        # every position's signal is healthy
        _, p, lv, pr = best
        rec = _close_qty(
            state, p, p["qty"], lv,
            f"rotated — signal gone, stronger setup waiting "
            f"({'banked' if pr >= 0 else 'cut'} at {pr:+.2f}R)")
        state["open"].remove(p)
        state["closed"].append(rec)
        held.discard(p["symbol"])
        src_n[p.get("src")] = max(0, src_n.get(p.get("src"), 0) - 1)
        rotated.append(rec)
        return True

    for c in cands:
        if c.get("rank", 0) < MIN_RANK:
            continue            # two-key sort (top, rank) — a low
                                # top-stream rank must not gate the
                                # cards sorted after it
        if c["symbol"] in held:
            continue
        if len(state["open"]) >= _slot_cap and not _rotate():
            continue            # board full, nothing rotatable
        _cap = MAX_PER_SRC.get(c["src"])
        if _cap is not None and src_n.get(c["src"], 0) >= _cap:
            if not _rotate({c["src"]}) or \
                    src_n.get(c["src"], 0) >= _cap:
                continue        # per-source seats full
        if c["src"] in TOP_FAMILY:
            if sum(src_n.get(s, 0) for s in TOP_FAMILY) \
                    >= TOP_FAMILY_CAP and (
                    not _rotate(TOP_FAMILY)
                    or sum(src_n.get(s, 0) for s in TOP_FAMILY)
                    >= TOP_FAMILY_CAP):
                continue        # 💥 top-family 5 seats full
        if c["src"] in ELITE_FAMILY:
            if sum(src_n.get(s, 0) for s in ELITE_FAMILY) \
                    >= ELITE_FAMILY_CAP and (
                    not _rotate(ELITE_FAMILY)
                    or sum(src_n.get(s, 0) for s in ELITE_FAMILY)
                    >= ELITE_FAMILY_CAP):
                continue        # 💎 elite-family 2 seats full
        try:
            live = float(live_fn(c["symbol"]) or 0)
        except Exception:
            live = 0.0
        if live <= 0:
            continue
        lng = c["side"] == "LONG"
        prog = ((live - c["entry"]) / (c["tp1"] - c["entry"]) if lng
                else (c["entry"] - live) / (c["entry"] - c["tp1"]))
        dead = live <= c["stop"] if lng else live >= c["stop"]
        if dead or prog > ZONE_MAX:
            continue
        stop_pct = abs(live - c["stop"]) / live
        if stop_pct <= 0.001 or stop_pct > STOP_MAX_PCT:
            continue
        # 📐 RR-AT-OPEN GUARD (GEN 15, from the 09-13 star autopsy):
        # seats open at the LIVE price with the plan's stop/TP1, so
        # the traded reward:risk drifts off the profile that earned
        # the stream its seat — star losers PUMP (rr 1.81) and CHIP
        # (1.22) were both outside the <1.2R profile by the time
        # they opened, and both stopped out. Streams whose EDGE IS
        # an rr law re-check it here against the live entry; a plan
        # that drifted outside its measured band is not the trade
        # that was validated, so it takes no seat.
        _rrb = RR_OPEN_BOUNDS.get(c["src"])
        if _rrb is not None:
            _rr_live = (abs(c["tp1"] - live)
                        / max(1e-12, abs(live - c["stop"])))
            _rlo, _rhi = _rrb
            if ((_rlo is not None and _rr_live < _rlo)
                    or (_rhi is not None and _rr_live >= _rhi)):
                continue
        # 💪 GEN 15 LEVERAGE-DRIVEN SIZING (user 2026-09-13: "leverage
        # to drive size — bigger positions at 10x, the way GEN 10-12
        # worked... yes thats what i want"). The SEAT is a fixed slice
        # of the bank and LEVERAGE decides how big the position on it
        # is; the dollar risk is then whatever the stop happens to
        # cost, recorded rather than chosen. This is the GEN 10-12
        # engine restored verbatim.
        #   margin   = balance / MAX_SLOTS
        #   notional = margin x lev_for(src, conf)
        #   risk     = notional x stop distance   (an OUTPUT now)
        # The two GEN 13 portfolio guards are KEPT, because they are
        # what stops a wide-stopped seat from quietly betting the
        # account: HEAT_CAP on total open risk, and free collateral.
        lev = lev_for(c["src"], c.get("conf"), c.get("burst"))
        # real-account physics: the stop must sit well inside the
        # slot's margin — a stop past ~liquidation is not a trade.
        if stop_pct >= 0.8 / lev:
            continue
        _bal = max(1.0, float(state["balance"]))
        _heat = 0.0
        _m_used = 0.0
        for _op in state["open"]:
            try:
                _d = ((float(_op["entry"]) - float(_op["stop"]))
                      if _op.get("side") == "LONG"
                      else (float(_op["stop"]) - float(_op["entry"])))
                _heat += float(_op.get("qty") or 0) * max(0.0, _d)
                _m_used += float(_op.get("margin") or 0)
            except Exception:
                continue
        margin = _bal / MAX_SLOTS
        if margin > _bal - _m_used:
            continue            # collateral spent — no seat
        notional = margin * lev
        risk_usd = notional * stop_pct
        if (_heat + risk_usd) / _bal > HEAT_CAP:
            continue            # portfolio already carrying its heat
        fee_in = notional * FEE
        pos = {"symbol": c["symbol"], "base": c["base"],
               "side": c["side"], "entry": live, "stop": c["stop"],
               "tp1": c["tp1"], "tp2": c["tp2"],
               "qty": notional / live, "notional": notional,
               "lev": round(lev, 1), "margin": round(margin, 2),
               "risk_usd": round(risk_usd, 2),
               "risk_pct": round(risk_usd / _bal, 4),
               "burst": float(c.get("burst") or 0),
               "risk0": abs(live - c["stop"]),
               "src": c["src"], "score": c["score"],
               "agree": c.get("agree", 1),
               "srcs": c.get("srcs", c["src"]),
               "opened_at": time.time(), "fees": fee_in,
               "tp1_banked": 0.0, "be_set": False, "peak": live}
        state["balance"] -= fee_in
        state["open"].append(pos)
        held.add(c["symbol"])
        src_n[c["src"]] = src_n.get(c["src"], 0) + 1
        opened.append(pos)
    return opened, rotated


def _close_qty(state, p, qty, px, reason) -> dict:
    lng = p["side"] == "LONG"
    pnl = qty * (px - p["entry"]) * (1 if lng else -1)
    fee = qty * px * FEE
    state["balance"] += pnl - fee
    p["fees"] = p.get("fees", 0.0) + fee
    rec = {"symbol": p["symbol"], "base": p["base"], "side": p["side"],
           "entry": p["entry"], "exit": px, "qty": qty,
           "pnl": round(pnl - fee, 2), "reason": reason,
           "src": p["src"], "opened_at": p["opened_at"],
           "closed_at": time.time()}
    return rec


def manage(state: dict, live_fn, kr_get=None) -> list:
    """GEN 15 EXIT LAW (user 2026-09-13: "its sl and tp that should be
    set with it nothing less, just a smart exit when its close to tp
    and you sense momentum is dropping"). A position can close for
    exactly THREE reasons:
        1. its STOP is hit          (the original SL — stops never
                                     move in GEN 15: nothing sets
                                     be_set, so the BE/trail ratchet
                                     below is dormant)
        2. its TP1 is hit           (banked 100%, seat freed, the
                                     worker may re-enter on momentum)
        3. the NEAR-TP BANK         (printed >=85% of the way to TP1
                                     then rolled back to <=60% while
                                     still in profit)
    No time stop, no breakeven stop-out, no trail, and the kronos
    smart exit is off for every GEN 15 stream (SMART_EXIT_SKIP).
    The dormant TRAIL / RIDE / kronos machinery is kept below as the
    revert path for earlier generations.
    Returns events: (close|tp1|guard, rec)."""
    events = []
    keep = []
    for p in state["open"]:
        try:
            live = float(live_fn(p["symbol"]) or 0)
        except Exception:
            live = 0.0
        if live <= 0:
            keep.append(p)
            continue
        lng = p["side"] == "LONG"
        # 📈 peak tracking — the best favorable price this position has
        # printed; the trail ratchets off THIS, never off a dip.
        _pk = float(p.get("peak") or p["entry"])
        _pk = max(_pk, live) if lng else min(_pk, live)
        p["peak"] = _pk
        # 🧵 TRAIL TO TP2 (user 2026-08-15): once TP1 banked, the rest
        # doesn't sit at flat breakeven — the stop locks TRAIL_LOCK of
        # the PEAK open gain and only ever moves the safe way, riding
        # toward TP2. Strong signals that get flipped against tighten
        # to TRAIL_LOCK_FLIP instead of closing (below).
        if p.get("be_set") and p["qty"] > 0:
            _lk = float(p.get("trail_lock") or TRAIL_LOCK)
            _cand = p["entry"] + (_pk - p["entry"]) * _lk
            p["stop"] = (max(p["stop"], _cand) if lng
                         else min(p["stop"], _cand))
        hit_stop = live <= p["stop"] if lng else live >= p["stop"]
        hit_tp1 = live >= p["tp1"] if lng else live <= p["tp1"]
        # 🎯 NEAR-TP BANK — GEN 15: EVERY STREAM (user 2026-09-13:
        # "its sl and tp that should be set with it nothing less,
        # just a smart exit when its close to tp and you sense
        # momentum is dropping"). Was elite_star-only from GEN 11.
        # The momentum read is pure price geometry, no external
        # feed: the trade PRINTED >=85% of the way to TP1 and has
        # since given back to <=60% of it while still in profit —
        # i.e. it went for the target, stalled, and is rolling over.
        # This is the ONLY exit in GEN 15 that is neither SL nor TP.
        if not hit_stop and not hit_tp1 and p["qty"] > 0:
            _tpd = abs(p["tp1"] - p["entry"]) or 1e-12
            _pk_pr = abs(_pk - p["entry"]) / _tpd
            _now_pr = ((live - p["entry"])
                       * (1 if lng else -1)) / _tpd
            if _pk_pr >= NEAR_TP_PEAK and 0 < _now_pr <= NEAR_TP_FADE:
                rec = _close_qty(
                    state, p, p["qty"], live,
                    f"🎯 near-TP bank — printed {_pk_pr * 100:.0f}% "
                    f"of the way to TP1, momentum rolling over at "
                    f"{_now_pr * 100:.0f}%; profit taken")
                state["closed"].append(rec)
                events.append(("close", rec))
                continue
        t2 = p.get("tp2")
        hit_tp2 = (t2 is not None
                   and (live >= t2 if lng else live <= t2))
        _tsh = TIME_STOP_BY_SRC.get(p.get("src"), TIME_STOP_H)
        expired = time.time() - p["opened_at"] > _tsh * 3600
        # 🛡 SMART EXIT — in profit + read flipped against us.
        # 2026-08-15 STRENGTH-AWARE (user: "loosen a bit if the signal
        # strength is good to gain more"): the brain checks the
        # signal's own quality —
        #   WEAK signal  → hard close, bank the money (validated)
        #   STRONG, before TP1 → stop to SCRATCH, ride to TP1
        #   STRONG, after TP1  → trail tightens to 75% of the peak
        #     gain, rest keeps riding toward TP2
        if not hit_stop and not hit_tp2 and kr_get is not None \
                and p.get("src") not in SMART_EXIT_SKIP:
            _r0 = float(p.get("risk0") or 0) or \
                abs(p["entry"] - p["stop"]) or p["entry"] * 0.02
            _pr = (live - p["entry"]) * (1 if lng else -1) / _r0
            if _pr >= 0.3:
                try:
                    _kv = kr_get(p["symbol"], p["side"])
                except Exception:
                    _kv = None
                if _kv:
                    _against = ((_kv.get("direction") == "DOWN" and lng)
                                or (_kv.get("direction") == "UP"
                                    and not lng))
                    _ex = abs(float(_kv.get("exp_move_pct") or 0))
                    if _against and _ex >= 2.0 and not _is_strong(p):
                        rec = _close_qty(
                            state, p, p["qty"], live,
                            f"smart exit — read flipped "
                            f"{_kv.get('direction')} "
                            f"{float(_kv.get('exp_move_pct') or 0):+.1f}%"
                            f" at +{_pr:.1f}R")
                        state["closed"].append(rec)
                        events.append(("close", rec))
                        continue
                    if _against and _ex >= 2.0 and _is_strong(p):
                        if p.get("be_set"):
                            _new_lk = TRAIL_LOCK_FLIP
                            _tag = (f"trail tightened to "
                                    f"{int(_new_lk*100)}% of the "
                                    f"peak gain, riding to TP2")
                            p["trail_lock"] = max(
                                float(p.get("trail_lock")
                                      or TRAIL_LOCK), _new_lk)
                            _cand = p["entry"] + \
                                (_pk - p["entry"]) * p["trail_lock"]
                            p["stop"] = (max(p["stop"], _cand) if lng
                                         else min(p["stop"], _cand))
                        else:
                            _cush = p["entry"] * 2 * FEE
                            _cand = p["entry"] + (_cush if lng
                                                  else -_cush)
                            p["stop"] = (max(p["stop"], _cand) if lng
                                         else min(p["stop"], _cand))
                            _tag = ("stop to scratch, riding to TP1 "
                                    "— strong signal earns the room")
                        if not p.get("flip_guard"):
                            p["flip_guard"] = True
                            events.append(("guard", {
                                "base": p["base"], "side": p["side"],
                                "symbol": p["symbol"],
                                "stop": p["stop"],
                                "reason": (
                                    f"read flipped "
                                    f"{_kv.get('direction')} "
                                    f"{float(_kv.get('exp_move_pct') or 0):+.1f}%"
                                    f" at +{_pr:.1f}R — STRONG signal "
                                    f"({p.get('src')}), {_tag}")}))
        if hit_stop:
            px = p["stop"]
            rec = _close_qty(state, p, p["qty"], px,
                             "BE stop" if p["be_set"] else "stop")
            state["closed"].append(rec)
            events.append(("close", rec))
            continue
        if hit_tp1 and not p["be_set"]:
            # 💎🔮 GEN 12 RIDE (elite_kr only): the +1.141R cell was
            # earned by RIDING — bank HALF at TP1, stop to entry
            # (BE), trail machinery takes the rest toward TP2.
            if p.get("src") in RIDE_SRC and p.get("tp2"):
                _half = p["qty"] / 2.0
                rec = _close_qty(state, p, _half, p["tp1"],
                                 "TP1 — banked 50%, riding the "
                                 "rest to TP2 (💎🔮 ride law)")
                p["qty"] -= _half
                p["tp1_banked"] = _half
                p["be_set"] = True
                p["stop"] = max(p["stop"], p["entry"]) \
                    if p["side"] == "LONG" \
                    else min(p["stop"], p["entry"])
                state["closed"].append(rec)
                events.append(("tp1", rec))
                keep.append(p)
                continue
            # GEN 7 (user 2026-08-28: "bank full at tp1 and start
            # trade again if the signals hold with confidence"):
            # 100% banked AT TP1 — the GEN 6 half-bank geometry lost
            # money at a 67% win rate (winners paid ~0.5R, stops hit
            # full -1R). The seat frees immediately; if the signal
            # is still live next cycle with a fresh in-zone plan,
            # try_open re-enters it as a NEW trade.
            rec = _close_qty(state, p, p["qty"], p["tp1"],
                             "TP1 — banked 100% (GEN 9); reopens if "
                             "the momentum still holds")
            # GEN 8 re-entry payload (user: "if the momentum is still
            # there open the trade again") — the worker checks the 1h
            # burst and re-opens with the same plan geometry anchored
            # at the live price. Chain-capped at 2 re-entries.
            rec["replan"] = {
                "stop_d": float(p.get("risk0")
                                or abs(p["entry"] - p["stop"])),
                "tp1_d": abs(p["tp1"] - p["entry"]),
                "tp2_d": (abs(p["tp2"] - p["entry"])
                          if p.get("tp2") else None),
                "score": p.get("score"),
                "chain": int(p.get("chain") or 0)}
            state["closed"].append(rec)
            events.append(("close", rec))
            continue
        # 🚫 GEN 15: THE TIME STOP IS GONE (user 2026-09-13: "its sl
        # and tp that should be set with it nothing less"). A trade
        # now resolves at its stop, at its target, or on the near-TP
        # momentum bank above — never on a clock. `expired` is still
        # computed and surfaced as a stale-seat note so a position
        # that stalls forever is visible rather than silently closed.
        # Revert the clock: restore `or expired` here.
        if p["qty"] > 0 and hit_tp2:
            px = t2 if t2 else live
            rec = _close_qty(state, p, p["qty"], px, "TP2")
            state["closed"].append(rec)
            events.append(("close", rec))
            continue
        if expired and not p.get("stale_flag"):
            p["stale_flag"] = True
            events.append(("guard", {
                "base": p["base"], "side": p["side"],
                "symbol": p["symbol"], "stop": p["stop"],
                "reason": (f"held {_tsh:.0f}h without reaching SL or "
                           f"TP1 — the clock no longer closes trades "
                           f"(GEN 15), so this seat stays taken until "
                           f"the plan resolves")}))
        keep.append(p)
    state["open"] = keep
    # equity snapshot (balance + unrealized)
    unreal = 0.0
    for p in state["open"]:
        try:
            live = float(live_fn(p["symbol"]) or 0)
            if live > 0:
                unreal += p["qty"] * (live - p["entry"]) * \
                    (1 if p["side"] == "LONG" else -1)
        except Exception:
            pass
    state["equity_hist"].append(
        [time.time(), round(state["balance"] + unreal, 2)])
    if len(state["equity_hist"]) > 4200:      # ~2 weeks of 5-min points
        state["equity_hist"] = state["equity_hist"][-4200:]
    return events

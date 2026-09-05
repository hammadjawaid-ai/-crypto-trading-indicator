"""24/7 signal worker — the always-on brain.

Scans on a timer (independent of any browser), STORES every best-signal to
SQLite, and pushes ONLY the best setups to your phone via Telegram:
  ✅🔥 TAKE NOW HOT   (ELITE MAX/HIGH, pulled-back + confirmed + elevated ATR)
  💠 SST1 conv≥70     (the proven ~72% tier)

Alert-only — it does NOT place trades. Cloud-safe: no winotify, no Streamlit,
env-var config. Deploy on Railway/Render as an always-on worker
(see README_WORKER.md). Stop with Ctrl+C locally.
"""
from __future__ import annotations

import io
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import best_board
import binance_client
import btc_outlook
import market_context as _mc_w
import news as _news_w
import news_impact as _ni_w
import sentiment as _sent_w
import signals as _sig_w
import coinalyze_client as cz
import config
import demo_account
import entry_timing
import experimental_signals as es
import fast_confirm
import ignition
import kronos_forecast as kf
import liq_flush
import live_executor
import lunarcrush
import moonshot_desk
import one_trade
import polymarket_events
import true_signal
import scan_core
import shadow_trader
import smart_stop as _ss_w
import surge_radar
import telegram_notify as tg
import velocity_burst as _vb_w
import early_trend as _et_w
import derivatives as _dv_w
import worker_store as store

INTERVAL = max(1, int(getattr(config, "WORKER_INTERVAL_MIN", 5))) * 60
# 🔮 per-symbol Kronos forecast cache — the worker process is long-lived
# so this persists across cycles. 24h-horizon forecasts move slowly;
# 2h TTL + a per-cycle cap keeps CPU/RAM bounded on the deploy.
_KR_CACHE: dict = {}
# 🔄 flip-watch memory: last seen kronos direction per watched symbol
_FLIP_PREV: dict = {}
# last direction we actually BUZZED (debounce: FLAT notices only after
# a buzzed UP/DOWN — kills the UP→FLAT flicker spam, user 2026-08-07)
_FLIP_BUZZED: dict = {}
# 🎯 watchlist sentry: last entry-timing state per watched symbol
_SENTRY_PREV: dict = {}
# 🚀 moonshot desk memory: social snapshots per coin (ts, alt_rank,
# interactions), positioning cache on rotation, rotation pointer
_MOON_SOC: dict = {}
_MOON_POS: dict = {}
_MOON_ROT = [0]
# 🌋 armed coils waiting for their break — {sym: {"p": plan, "t": ts}}.
# A coil is NOT a trade until price crosses the trigger (2026-08-11
# fix); unbroken setups expire after PB_ARM_H hours.
_PB_ARMED: dict = {}
PB_ARM_H = 24.0
KR_TTL = 2 * 3600
KR_MAX_PER_CYCLE = 8
# extra on-demand forecasts per cycle, spent ONLY on in-zone
# approval candidates that the budgeted capture loop missed — so a
# 🔮✅ agreement reaches Telegram at fire time, not a cycle later.
KR_APPROVE_EXTRA = 6
# 🌋 rotating scan counter — top-100 universe in halves (50/cycle)
_PB_ROT = [0]
COOLDOWN = max(1, int(getattr(config, "WORKER_ALERT_COOLDOWN_MIN", 360))) * 60
MIN_CONV = float(getattr(config, "WORKER_SST1_MIN_CONV", 70))
LB_MIN = float(getattr(config, "WORKER_LEADERBOARD_MIN_SCORE", 85))
# 🎯 CONFIDENCE FLOOR for signal buzzes (user 2026-07-14: "only max
# confidence, 85 or above"). 85 == the 💎 bar: a validated top cell
# alone or 2+ systems agreeing. Lone single-system fires stay board-only.
# Loosen anytime via env ALERT_CONF_MIN (e.g. 60 = everything again).
import os as _os
ALERT_CONF_MIN = float(_os.environ.get("ALERT_CONF_MIN", "85") or 85)


def _tp2(p):
    return f" · TP2 `{p['tp2']:g}`" if p.get("tp2") else ""


def _fmt_takenow(p) -> str:
    return (f"✅🔥 *TAKE NOW HOT* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_ATR {p.get('atr_pct','?')}pct — firing with force "
            f"(validated higher-edge)_")


def _fmt_sst1(p) -> str:
    return (f"💠 *SST1 conv {p['conviction']:.0f}* — {p['base']} {p['side']}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_proven ~72% tier_")


def _fmt_leaderboard(p) -> str:
    return (f"🏆 *Leaderboard {p['tier']} {p['score']:.0f}* — "
            f"{p['base']} {p['side']}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_top-conviction ELITE — early heads-up_")


def _fmt_best(p) -> str:
    tags = " · ".join(p.get("tags") or [])
    prog = p.get("_prog")
    zone = (f" · 🟢 IN ZONE ({prog * 100:.0f}% to TP1)"
            if prog is not None else "")
    hold = p.get("hold_est") or "hours-2 days"
    return (f"💎 *BEST OF THE BEST* — {p['base']} {p['side']} "
            f"(stack {p.get('best_score', 0):g}){zone}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"⏱ hold: *{hold}*\n"
            f"_{tags} — systems agreeing; BE at +1R, trail after TP1._")


def _fmt_early_rest(p) -> str:
    prog = p.get("_prog")
    zone = (f" · 🟢 IN ZONE ({prog * 100:.0f}% to TP1)"
            if prog is not None else "")
    return (f"⚡ *EARLY MOVER* — {p['base']} {p['side']} "
            f"(STRONG {p['score']:.0f}){zone}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_STRONG + TAKE NOW 🔥 HOT (69% cell) — desk tier is 🟢 "
            f"green. Size smaller than 🚀 early-lane._")


def _fmt_surge(p) -> str:
    return (f"📡 *SURGE (fresh pump)* — {p['base']} LONG "
            f"(+{p.get('surge_pct')}% in {p.get('surge_age_bars')}x15m · "
            f"24h {p.get('chg24'):+.0f}%)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` (surge low) · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_Whole-market ignition radar — fires ONLY in a pump's "
            f"first ~2h; refuses extended chases. UNPROVEN construct, "
            f"desk tier 📡 surge is proving it. SIZE SMALL._")


def _fmt_fast30(p) -> str:
    return (f"⏱ *FAST CONFIRM 30m* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · 🚀 approved)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_30m-candle confirm — ~30min earlier than the proven 1h. "
            f"Measured weaker (68% / −0.02R vs 77% / +0.05R) — your "
            f"explicit call. SIZE SMALLER. Desk tier fast30 is proving "
            f"it forward._")


def _fmt_ignition(p) -> str:
    return (f"🚨 *IGNITION (early)* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · 🚀 approved)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_AT-FIRE — 1-2h earlier than confirmation, by your call "
            f"('fast even if it fails'). Honest odds ~50-65%. SIZE "
            f"SMALLER. Desk is proving it forward._")


# 💥 TRIGGER WATCH (user 2026-08-15, the BMT case: "just before it is
# about to pump hard... it gives me a buzz on telegram but this has to
# be before it fires hard"): a dedicated 60-second watch loop over the
# strongest armed setups — every 💎 approved ELITE CONVICTION card and
# every ⚡ STRONG watch coil — with a trigger at the 24-bar high (low
# for shorts), THE one construct that ever measured positive across
# six pre-burst studies (+0.10-0.12R break entry). The buzz lands the
# MINUTE the trigger breaks, not up to 5 minutes later when the next
# worker cycle happens to look. Honest boundary, measured six ways:
# predicting the pump BEFORE any price confirmation is a losing game
# (coil -0.21R, 15m thrust -0.15R, flips -0.05R, OWL -0.23R, flow
# -0.20R, at-fire unverified ~23%) — the break IS the earliest moment
# that pays, so that is the moment this watches, at 60s resolution.
_TRIG_ARMED: dict = {}
_TRIG_LOCK = threading.Lock()
_TRIG_STARTED = False
TRIG_POLL_S = 60
TRIG_ARM_H = 24.0
# 🔥 SECOND-LEG memory (user 2026-08-17, the ACE case: elite winner
# re-ignited days after its card expired and nothing was watching —
# "we make sure we dont miss out anything here again"): every elite
# MAX/HIGH fire is remembered for SECOND_LEG_DAYS after the card
# dies. Remembered coins stay armed on the 60s watch at their
# consolidation high (low for shorts) — the moment a second leg
# breaks out, the 🔶/💥 ladder speaks even though the composite
# reads NEUTRAL (its anti-chase suppression blinds it to second
# legs by design). Desk tier second_leg builds the live record;
# backtest_secondleg validates the construct + pattern cells.
_SECOND_LEG: dict = {}
SECOND_LEG_DAYS = 7.0
# 🎮 GEN 6 demo feed (user 2026-08-23: demo money goes ONLY to strong
# triggers, re-runs, and elite MAX/HIGH): the 60s watch appends every
# BREAK here — ⚡ arm → strong_trigger, 🔥 arm → rerun, 💎 arm →
# elite_conv entering on the validated break. The 5-min cycle drains
# fresh fires (<=30 min old) into the demo pools; the zone gate and
# one-per-coin rule in demo_account do the rest. Guarded by
# _TRIG_LOCK (written from the watch thread, read from the cycle).
_DEMO_FIRES: list = []
DEMO_FIRE_TTL_S = 1800
# 🎮 GEN 8 feeds (user 2026-09-05): the duo-pair buzzes and the ⚡
# waking lane get demo seats. Cycle-thread only; TTL-drained like
# _DEMO_FIRES. _DEMO_REOPEN holds TP1-banked winners whose momentum
# check passed — they re-enter next cycle ("if the momentum is still
# there open the trade again"), chain-capped at 2.
_DEMO_DUOS: list = []
_DEMO_WAKE: list = []
_DEMO_REOPEN: list = []
# 💎✅ ELITE CONFIRMED ENTRY watch (user 2026-08-23: "make this one
# then... built separately, no touching the elite conviction cards,
# and it have the buzz of its own"). The VALIDATED entry style on
# elite fires — pullback to the card's entry + a confirming candle
# with volume — measured 67.8% win / +0.025R after fees, green in
# BOTH history halves (backtest_elite_entry, 387 fires, 100 coins).
# Every MAX/HIGH fire is watched for 48h; the stream speaks only at
# the confirmed moment. Cycle-thread only — no lock needed.
_EC_WATCH: dict = {}
EC_WATCH_H = 48.0
# 🕵️ OI LOAD pre-spike radar clock (15-min cadence — the tell is an
# 8h positioning build; faster polling adds calls, not information)
_OI_LAST = 0.0
# 🎮 confirmed entries feed the GEN 6 demo too (user 2026-08-23
# follow-up: "lets also have elite confirm entry in place as well —
# 3 to 4 confirm elite entry and elite entry altogether"). Same
# TTL/drain pattern as _DEMO_FIRES; cycle-thread only.
_ECF_FIRES: list = []
# 🦅 EAGLE EYE (user 2026-08-29: "monitor very sharply like an eagle
# even if its 3m movement and the time we sense anything that is
# heating up it should buzz right at the point"): every 🌟 EARLY
# ELITE / 💎 BEST card at 🎯 conf >= 70 goes under the 60s daemon's
# fast-clock watch (3m + 5m) for 48h — falls included. Populated by
# the cycle, scanned by the trigger daemon, shared under _TRIG_LOCK.
_EAGLE_WATCH: dict = {}
EAGLE_WATCH_H = 48.0
EAGLE_MAX = 10
# 💎🔄 RE-QUALIFICATION (user 2026-08-19, after ALICE/BANK hit
# TP1): when a coin we already traded goes quiet and then
# qualifies MAX/HIGH AGAIN, that is a NEW setup and must be
# notified — approved OR unapproved — so he knows when to get
# back in. A gap of this many hours since the card last fired
# is what separates a fresh setup from a card still running.
RE_GAP_H = 6.0


def _conf_votes(df1h, side: str):
    """🎯 conf = 25 + 20 x stacked edge votes, computed from candles.

    The SAME ladder best_board.confidence encodes, but self-contained
    so it works on ANY symbol (LAST_VOTES only covers the scan
    universe and would fall back to 55). Votes: HOT ATR (top 40% of
    trailing 100) + HOT ROC (6-bar, top 40%) + 1h velocity burst >=78
    on the trade side. VALIDATED 2026-08-31 on 197 resolved confirms:
    conf>=65 -> 63.9% / +0.241R (older +0.119, recent +0.331 — green
    BOTH halves); conf<65 -> 50.7% / -0.035R (flat-to-red).
    """
    try:
        side = (side or "").upper()
        h = df1h["high"].to_numpy()
        l = df1h["low"].to_numpy()
        c = df1h["close"].to_numpy()
        if len(c) < 40:
            return None
        tr = h - l
        atr_now = float(tr[-15:-1].mean())
        hist = [float(tr[j - 14:j].mean())
                for j in range(max(15, len(tr) - 100), len(tr))]
        hot = (len(hist) >= 30
               and sum(1 for x in hist if x < atr_now)
               / len(hist) >= 0.6)
        roc_now = float(c[-1] / c[-7] - 1)
        rh = [float(c[j] / c[j - 6] - 1)
              for j in range(max(7, len(c) - 100), len(c))]
        hotroc = (len(rh) >= 30
                  and sum(1 for x in rh if x < roc_now)
                  / len(rh) >= 0.6)
        bs, bd, _ = _vb_w.lane_velocity_burst(df1h)
        b78 = bs >= 78 and (bd or "").upper() == side
        votes = int(hot) + int(hotroc) + int(b78)
        return int(min(98, 25 + 20 * votes))
    except Exception:
        return None


def _conf_chip(a: dict) -> str:
    """The 🎯 conf chip for a buzz line — empty when unknown."""
    cf = a.get("conf")
    if cf is None:
        return ""
    return (f" · 🎯 conf {int(cf)}/100"
            + (" 💪 EDGE ZONE" if int(cf) >= 65
               else " (below the 65 line)"))


def _atr_heat(df1h) -> int | None:
    """🌡 HEAT 0-100 — the ONE candle input that survived validation
    (2026-09-04 conf rebuild: HOT ATR spread +0.200R ON-vs-OFF, both
    halves; ROC inert, burst sign-flipped — both dropped). Continuous
    percentile of the current 14-bar ATR vs its trailing 100, instead
    of the old 0.6 cliff. Display-only, gates nothing."""
    try:
        h = df1h["high"].to_numpy()
        l = df1h["low"].to_numpy()
        if len(h) < 45:
            return None
        tr = h - l
        atr_now = float(tr[-15:-1].mean())
        hist = [float(tr[j - 14:j].mean())
                for j in range(max(15, len(tr) - 100), len(tr))]
        if len(hist) < 30:
            return None
        return int(round(sum(1 for x in hist if x < atr_now)
                         / len(hist) * 100))
    except Exception:
        return None


def _pair_chips(symbol, side) -> str:
    """🤝 cluster + 🌡 heat chips (2026-09-04 conf rebuild, display-
    only). Cluster = which other elite-family streams opened the same
    coin+side in the last 30 min — measured agreement instead of the
    abstract vote sum (2 streams was THE winner cell; 3+ downgrades).
    NEVER raises — a chip must not kill a buzz (the _b3 lesson)."""
    bits = []
    try:
        others = [t for t in store.live_cluster(symbol, side)]
        _nm = {"apex": "APEX", "best_board": "BEST",
               "one_trade": "ONE", "elite_conv": "ELITE",
               "elite_confirm": "CONFIRM", "elite_early": "E-ELITE",
               "takenow_hot": "TN"}
        if others:
            names = "+".join(_nm.get(t, t) for t in others[:3])
            warn = " ⚠️ crowd" if len(others) >= 3 else ""
            bits.append(f"🤝 with {names}{warn}")
    except Exception:
        pass
    try:
        _dfh = binance_client.get_klines(symbol, "1h", limit=120)
        _ht = _atr_heat(_dfh)
        if _ht is not None:
            bits.append(f"🌡 heat {_ht}")
    except Exception:
        pass
    return (" · " + " · ".join(bits)) if bits else ""


def _trigger_pass(a: dict, px: float) -> bool:
    """True when live price has broken the armed trigger."""
    if px <= 0:
        return False
    return (px >= a["trigger"] if a["side"] == "LONG"
            else px <= a["trigger"])


def _fmt_trigger(a: dict, px: float, vk: float) -> str:
    _t2 = (f" · TP2 `{a['tp2']:g}`" if a.get("tp2") else "")
    _age = (time.time() - float(a.get("armed_at") or time.time())) / 3600
    # 🔥 burst grade (validated 2026-08-18, backtest_secondleg, 346
    # breaks): a break carrying burst>=85 ran 64.7%/+0.288R vs
    # 55.4%/+0.107R without — nearly 3x the expectancy, and the most
    # stable cell measured all week (older +0.296 / recent +0.280).
    # Burst is also the only gate that transferred to STRONG at-fire,
    # so it earns a headline verdict on every break message.
    _bs = float(a.get("burst") or 0)
    _grade = (f"\n🔥 BURST {_bs:.0f} — the A-grade break (validated "
              f"64.7% · +0.288R)" if _bs >= 85
              else f"\n· burst {_bs:.0f} — no hard burst behind this "
                   f"break (baseline 55.4% · +0.107R)")
    return (f"💥 *{a['src']} TRIGGER* — {a['base']} {a['side']} "
            f"breaking `{a['trigger']:g}` NOW\n"
            f"live `{px:g}` · 15m vol {vk:.1f}x · score "
            f"{float(a.get('score') or 0):.0f} · armed {_age:.1f}h ago"
            f"{_conf_chip(a)}"
            f"{_grade}\n"
            f"entry `{a['entry']:g}` · SL `{a['stop']:g}` · "
            f"TP1 `{a['tp1']:g}`{_t2}\n"
            f"_the ignition moment, caught on the 60s watch — the "
            f"validated break construct. This is as early as the data "
            f"lets an honest signal be._")


# 🔶 the middle ground (user 2026-08-15: "armed heads-up AND buzz
# will create confusion — find a middle ground, a little before"):
# arming stays SILENT; the one early warning fires when price is
# PRESSING the trigger (within NEAR_PCT), minutes-not-days before
# the break — the smell-the-move moment. Then 💥 on the break.
TRIG_NEAR_PCT = 0.004          # within 0.4% of the trigger = near


def _trigger_near(a: dict, px: float) -> bool:
    """True when live price is pressing the trigger but not through."""
    if px <= 0:
        return False
    t = a["trigger"]
    if a["side"] == "LONG":
        return t * (1 - TRIG_NEAR_PCT) <= px < t
    return t < px <= t * (1 + TRIG_NEAR_PCT)


# 💎🌀 momentum re-fire (user 2026-08-16: "elite conviction max or
# high — if it notifies and the movement is soon, it refires again as
# soon as we see the momentum, even a little bit, no matter the
# time"): an armed 💎 card that moves MOM_PCT in its direction from
# the fire price re-notifies immediately — the wake-up call between
# the fire buzz and the trigger break. One per armed setup.
TRIG_MOM_PCT = 0.01            # +1% from the fire = momentum
                               # (1.5 -> 1.0 same day, user order:
                               # "even +1% from its fire price")


def _trigger_momentum(a: dict, px: float) -> bool:
    if px <= 0 or not a.get("entry"):
        return False
    if a["side"] == "LONG":
        return px >= a["entry"] * (1 + TRIG_MOM_PCT)
    return px <= a["entry"] * (1 - TRIG_MOM_PCT)


def _fmt_momentum(a: dict, px: float) -> str:
    _t2 = (f" · TP2 `{a['tp2']:g}`" if a.get("tp2") else "")
    _mv = abs(px / a["entry"] - 1) * 100
    return (f"💎🌀 *ELITE CONV MOMENTUM* — {a['base']} {a['side']} "
            f"waking up\n"
            f"live `{px:g}` — {_mv:+.1f}% from the fire · score "
            f"{float(a.get('score') or 0):.0f} · trigger "
            f"`{a['trigger']:g}` still ahead\n"
            f"plan: entry `{a['entry']:g}` · SL `{a['stop']:g}` · "
            f"TP1 `{a['tp1']:g}`{_t2}\n"
            f"_the notified card is MOVING — momentum showing before "
            f"the trigger. 🔶 pressing and 💥 break follow if it "
            f"keeps going._")


def _fmt_near(a: dict, px: float) -> str:
    _t2 = (f" · TP2 `{a['tp2']:g}`" if a.get("tp2") else "")
    _d = abs(px / a["trigger"] - 1) * 100
    return (f"🔶 *{a['src']} NEAR TRIGGER* — {a['base']} {a['side']}\n"
            f"live `{px:g}` pressing the trigger `{a['trigger']:g}` "
            f"({_d:.2f}% away) · score "
            f"{float(a.get('score') or 0):.0f}"
            f"{_conf_chip(a)}\n"
            f"plan: entry `{a['entry']:g}` · SL `{a['stop']:g}` · "
            f"TP1 `{a['tp1']:g}`{_t2}\n"
            f"_the smell-the-move moment — get ready. The 💥 fires "
            f"the minute it breaks. One warning per setup._")


def _bstock_quiet(sym) -> bool:
    """🏦 True while a tokenized symbol must stay off the phone.
    2026-08-17 later the same day: the user turned the buzz ON
    (BSTOCK_BUZZ) — B-stocks now notify like crypto through every
    stream. The MONEY gate (BSTOCK_VALIDATED, demo seats) stays
    separate and closed until the cohort validates."""
    if getattr(config, "BSTOCK_BUZZ", False) \
            or getattr(config, "BSTOCK_VALIDATED", False):
        return False
    return sym in getattr(config, "TOKENIZED_STOCKS", ())


def _trigger_watch() -> None:
    """60s daemon: watch armed setups, buzz the second one breaks."""
    while True:
        time.sleep(TRIG_POLL_S)
        try:
            _now = time.time()
            with _TRIG_LOCK:
                items = list(_TRIG_ARMED.items())
            for k, a in items:
                if _now - float(a.get("armed_at") or 0) \
                        > TRIG_ARM_H * 3600:
                    with _TRIG_LOCK:
                        _TRIG_ARMED.pop(k, None)
                    continue
                try:
                    px = float(binance_client.get_ticker_price(
                        a["symbol"]) or 0)
                except Exception:
                    continue
                if not _trigger_pass(a, px):
                    # 💎🌀 the notified elite card is MOVING (user
                    # 2026-08-16: refire on momentum, even a little,
                    # no matter the time) — one wake-up per setup.
                    if (str(a.get("src", "")).startswith("💎")
                            and not a.get("mom_sent")
                            and _trigger_momentum(a, px)):
                        with _TRIG_LOCK:
                            a["mom_sent"] = True
                        try:
                            if store.should_alert(
                                    f"trigmom:{a['symbol']}:"
                                    f"{a['side']}", 2 * 3600) \
                                    and not _bstock_quiet(
                                        a["symbol"]):
                                tg.send(_fmt_momentum(a, px))
                        except Exception as exc:
                            print("[trigger] mom-buzz error:", exc,
                                  flush=True)
                    # 📵 🔶 NEAR TRIGGER buzz OFF (user 2026-08-31:
                    # "remove near trigger buzz from telegram
                    # notifications just strong triggers only"). The
                    # arming and near-detection still run — only the
                    # phone stays quiet until the actual 💥 BREAK,
                    # which is the validated construct (79% live).
                    # Revert: uncomment the block below.
                    # if not a.get("near_sent") and _trigger_near(a, px):
                    #     with _TRIG_LOCK:
                    #         a["near_sent"] = True
                    #     try:
                    #         if store.should_alert(
                    #                 f"trignear:{a['symbol']}:"
                    #                 f"{a['side']}", 6 * 3600) \
                    #                 and not _bstock_quiet(
                    #                     a["symbol"]):
                    #             try:
                    #                 a["conf"] = _conf_votes(
                    #                     binance_client.get_klines(
                    #                         a["symbol"], "1h",
                    #                         limit=140), a["side"])
                    #             except Exception:
                    #                 a["conf"] = None
                    #             tg.send(_fmt_near(a, px))
                    #     except Exception as exc:
                    #         print("[trigger] near-buzz error:", exc,
                    #               flush=True)
                    continue
                # volume kick on the forming 15m bar — fetched only
                # on an actual break (rare), never in the hot loop
                vk = 0.0
                try:
                    d15 = binance_client.get_klines(a["symbol"], "15m",
                                                    limit=40)
                    v15 = d15["volume"].to_numpy()
                    vk = float(v15[-1] / max(1e-9, v15[-21:-1].mean()))
                except Exception:
                    pass
                # 🔥 burst AT the break — the A-grade tell (2026-08-18
                # validation: >=85 nearly triples expectancy). Same
                # rare path as the volume fetch, so it costs nothing
                # in the hot loop.
                try:
                    _dfb = binance_client.get_klines(a["symbol"], "1h",
                                                     limit=120)
                    _bsv, _bsd, _ = _vb_w.lane_velocity_burst(_dfb)
                    a["burst"] = (float(_bsv)
                                  if (_bsd or "").upper() == a["side"]
                                  else 0.0)
                    # 🎯 conf stamp on the break (user 2026-08-31:
                    # "for strong trigger and strong near triggers
                    # also set the confidence score") — free here,
                    # the 1h frame is already in hand.
                    a["conf"] = _conf_votes(_dfb, a["side"])
                except Exception:
                    a["burst"] = 0.0
                with _TRIG_LOCK:
                    _TRIG_ARMED.pop(k, None)
                # 🎮 GEN 6 demo feed — every break is demo-money
                # candidate material: ⚡ → strong_trigger, 🔥 →
                # rerun, 💎 → elite entering on the break.
                _src0 = str(a.get("src", ""))
                _dsrc = ("strong_trigger" if _src0.startswith("⚡")
                         else "rerun" if _src0.startswith("🔥")
                         else None if _src0.startswith("🕵️")
                         else "elite_conv")
                if _dsrc is not None:   # 🕵️ breaks: no demo money
                                        # until their ledger earns it
                    with _TRIG_LOCK:
                        _DEMO_FIRES.append(
                            {"symbol": a["symbol"], "base": a["base"],
                             "side": a["side"], "entry": px,
                             "stop": a["stop"], "tp1": a["tp1"],
                             "tp2": a.get("tp2"),
                             "score": float(a.get("score") or 80),
                             "burst": float(a.get("burst") or 0),
                             "src": _dsrc, "fired_at": _now})
                        del _DEMO_FIRES[:-40]
                try:
                    if store.should_alert(
                            f"trig:{a['symbol']}:{a['side']}",
                            6 * 3600):
                        if not _bstock_quiet(a["symbol"]):
                            tg.send(_fmt_trigger(a, px, vk))
                        store.record_signal("trigger_fire", a)
                        print(f"[trigger] 💥 {a['base']} {a['side']} "
                              f"@ {px:g}", flush=True)
                except Exception as exc:
                    print("[trigger] buzz error:", exc, flush=True)
                # 🧪 desk proof (user 2026-08-16: "strong early
                # trigger is something i am not really convinced —
                # test on decision desk separately, and with kronos
                # both"): every ⚡ STRONG trigger fire is shadow-taken
                # at the BREAK price under tier trig_strong; the
                # subset where the cached kronos read agrees at fire
                # time doubles into trig_strong_kr. Records only —
                # no money, no extra buzz; the two ledgers decide.
                # 🔥 second-leg fires build their own desk record
                # (validating construct — buzz already went out via
                # the ladder; the ledger decides its future).
                if str(a.get("src", "")).startswith("🔥"):
                    try:
                        _sig_sl = {"symbol": a["symbol"],
                                   "base": a["base"],
                                   "side": a["side"],
                                   "tier": "2NDLEG",
                                   "score": a.get("score"),
                                   "conf": a.get("conf"),
                                   "entry": px, "stop": a["stop"],
                                   "tp1": a["tp1"],
                                   "tp2": a.get("tp2")}
                        store.record_signal("second_leg", _sig_sl)
                        shadow_trader.open_from_signal(
                            "second_leg", _sig_sl, px)
                    except Exception as exc:
                        print("[trigger] 2ndleg-proof error:", exc,
                              flush=True)
                # 🕵️💥 OI-load arm broke — the fused pre-spike
                # construct completing (user 2026-08-28: "work with
                # the whole system"): its own desk tier proves what
                # a graded load's BREAK is worth live.
                if str(a.get("src", "")).startswith("🕵️"):
                    try:
                        _sig_oi = {"symbol": a["symbol"],
                                   "base": a["base"],
                                   "side": a["side"],
                                   "tier": "OILOAD",
                                   "score": a.get("score"),
                                   "conf": a.get("conf"),
                                   "entry": px, "stop": a["stop"],
                                   "tp1": a["tp1"],
                                   "tp2": a.get("tp2")}
                        store.record_signal("oi_break", _sig_oi)
                        shadow_trader.open_from_signal(
                            "oi_break", _sig_oi, px)
                    except Exception as exc:
                        print("[trigger] oi-proof error:", exc,
                              flush=True)
                if str(a.get("src", "")).startswith("⚡"):
                    try:
                        _sig_t = {"symbol": a["symbol"],
                                  "base": a["base"],
                                  "side": a["side"], "tier": "STRONG",
                                  "score": a.get("score"),
                                  "conf": a.get("conf"),
                                  "entry": px, "stop": a["stop"],
                                  "tp1": a["tp1"],
                                  "tp2": a.get("tp2")}
                        store.record_signal("trig_strong", _sig_t)
                        shadow_trader.open_from_signal(
                            "trig_strong", _sig_t, px)
                        _h2 = _KR_CACHE.get(a["symbol"])
                        _s2 = (_h2["s"] if _h2 and
                               time.time() - _h2["t"] <= KR_TTL
                               else None)
                        if _s2 and (
                                (_s2.get("direction") == "UP"
                                 and a["side"] == "LONG")
                                or (_s2.get("direction") == "DOWN"
                                    and a["side"] == "SHORT")):
                            store.record_signal("trig_strong_kr",
                                                _sig_t)
                            shadow_trader.open_from_signal(
                                "trig_strong_kr", _sig_t, px)
                    except Exception as exc:
                        print("[trigger] desk-proof error:", exc,
                              flush=True)
            # 🦅 EAGLE EYE fast-clock scan (user 2026-08-29: "I want
            # the signal when the coin is about to move... close to
            # trigger and can go big from there"). Up to 4 cards per
            # 60s tick, oldest-checked first — every card gets a
            # fast look every ~2-3 min. Heat = 5m burst >= 65 AND 5m
            # trend >= 55, both side-matched, price not past TP1 (no
            # chases). Watch survives falls for 48h.
            # 2026-09-03 FIX: the buzz f-string read `_b3`, a name that
            # was never assigned anywhere in this file (leftover from
            # the pre-validation 3m draft). Every eagle fire raised
            # NameError inside the try below, so the buzz never sent
            # and no desk trade ever opened — the tier had 0 rows.
            # Now reports the 5m burst the gate actually measures.
            with _TRIG_LOCK:
                _eg_items = sorted(
                    _EAGLE_WATCH.items(),
                    key=lambda kv: kv[1].get("last_chk", 0))
            _eg_done = 0
            for _ek, _ea in _eg_items:
                if _eg_done >= 4:
                    break
                if _now - float(_ea.get("added_at") or 0) \
                        > EAGLE_WATCH_H * 3600:
                    with _TRIG_LOCK:
                        _EAGLE_WATCH.pop(_ek, None)
                    continue
                if _now - float(_ea.get("last_chk") or 0) < 150:
                    continue
                _eg_done += 1
                with _TRIG_LOCK:
                    _ea["last_chk"] = _now
                try:
                    _es9 = _ea["symbol"]
                    _eside = _ea["side"]
                    _lng9 = _eside == "LONG"
                    _px9 = float(
                        binance_client.get_ticker_price(_es9) or 0)
                    if _px9 <= 0:
                        continue
                    _tp19 = float(_ea.get("tp1") or 0)
                    if _tp19 > 0 and ((_lng9 and _px9 >= _tp19)
                                      or (not _lng9
                                          and _px9 <= _tp19)):
                        continue      # move already paid — no chase
                    # VALIDATED gate (backtest_eagle, 387 fires:
                    # 63.5%/+0.221R, green both halves; MAX cell
                    # 69.7%/+0.431R): 5m burst >= 65 AND 5m trend
                    # >= 55, both side-matched — the exact studied
                    # shape, no 3m looseners.
                    _d5 = binance_client.get_klines(_es9, "5m",
                                                    limit=150)
                    _t5, _td5, _ = _et_w.detect(_d5)
                    _b5, _bd5, _ = _vb_w.lane_velocity_burst(_d5)
                    if not (_b5 >= 65
                            and (_bd5 or "").upper() == _eside
                            and _t5 >= 55 and _td5 == _eside):
                        continue
                    if _bstock_quiet(_es9):
                        continue
                    if not store.should_alert(
                            f"eagleheat:{_es9}:{_eside}", 4 * 3600):
                        continue
                    _l59 = (f"5m trend {_t5:.0f}"
                            if (_t5 >= 55 and _td5 == _eside)
                            else f"5m burst {_b5:.0f}")
                    _t29 = (f" · TP2 `{float(_ea['tp2']):g}`"
                            if _ea.get("tp2") else "")
                    ok, _ = tg.send(
                        f"🦅 *EAGLE EYE — {_ea['base']} {_eside} "
                        f"HEATING NOW* (card {_ea.get('tier')} "
                        f"{float(_ea.get('score') or 0):.0f} · 🎯 "
                        f"conf {_ea.get('conf')}/100)\n"
                        f"5m burst {_b5:.0f} + {_l59} — the first "
                        f"candles of the move · live `{_px9:g}`\n"
                        f"entry `{float(_ea['entry']):g}` · SL "
                        f"`{float(_ea['stop']):g}` · TP1 "
                        f"`{float(_ea['tp1']):g}`{_t29}\n"
                        f"_the 60s eagle on every conf-70+ 🌟/💎 "
                        f"card — the about-to-move look. Earliest "
                        f"tell = smaller size; 💥 break / 🟢 confirm "
                        f"stay the full green lights._")
                    try:
                        _sig_e = {"symbol": _es9,
                                  "base": _ea.get("base"),
                                  "side": _eside,
                                  "tier": _ea.get("tier"),
                                  "score": _ea.get("score"),
                                  "entry": _px9,
                                  "stop": _ea.get("stop"),
                                  "tp1": _ea.get("tp1"),
                                  "tp2": _ea.get("tp2"),
                                  "conf": _ea.get("conf")}
                        store.record_signal("eagle_heat", _sig_e)
                        shadow_trader.open_from_signal(
                            "eagle_heat", _sig_e, _px9)
                    except Exception as exc:
                        print("[eagle] proof error:", exc, flush=True)
                    print(f"[eagle] 🦅 {_ea['base']} {_eside} heat "
                          f"@ {_px9:g}", flush=True)
                except Exception as exc:
                    print("[eagle] scan error:", exc, flush=True)
        except Exception as exc:
            print("[trigger] loop error:", exc, flush=True)


def _fmt_ign_strong(p) -> str:
    return (f"⚡🚨 *STRONG IGNITION* — {p['base']} {p['side']} "
            f"(STRONG {p['score']:.0f} · burst {p.get('burst', 0)})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}{_kr_note(p)}\n"
            f"_the PIXEL catcher — STRONG at-fire + HARD burst ≥85 "
            f"same side (validated 55% · +0.24R, green both halves, "
            f"n=62). Rare by design. SIZE SMALL — desk is proving it "
            f"forward, no demo money yet._")


def _fmt_moonshot(p) -> str:
    _kr = (f"🔮 {p.get('kr_dir')} "
           f"{float(p.get('kr_exp') or 0):+.1f}% (color)"
           if p.get("kr_dir") else "🔮 no read")
    return (f"🚀 *MOONSHOT* — {p['base']} LONG "
            f"(votes {p.get('votes', 0)}/3 · break on "
            f"x{p.get('vx', 0):g} vol)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · TP1 "
            f"`{p['tp1']:g}` — *BANK 100% AT 1R* (trail measured "
            f"worse) · `{p['tp2']:g}` = optional runner, unvalidated\n"
            f"🔥 {p.get('heat_d', '—')}\n⛽ {p.get('fuel_d', '—')}\n"
            f"{_kr}\n"
            f"_validated core (top-30 fires only): 61.5% · +0.14R "
            f"banking 1R (n=96); coiled bases 78%. Heat layer proves "
            f"forward on desk tier 🚀. Size small._")


def _fmt_conviction(p) -> str:
    # 2026-08-07 user final call: "strong and max read both" bank
    # full — EVERY 💯 fire banks 100% at TP1, no runners. That is
    # exactly the validated construct (the 88%/+0.40R cell was
    # measured banking TP1 in full).
    _geo = "BANK 100% AT TP1 — the validated win-rate geometry"
    return (f"💯 *CONVICTION* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · 🚀 approved · "
            f"burst {float(p.get('burst') or 0):.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"➡️ {_geo}\n"
            f"_v2 cell (70.7% · +0.13R, green both halves): CONFIRMED "
            f"entry + 82+ + 🚀 approved + no spent thrust. Kronos "
            f"removed 2026-08-23 on the live evidence. Desk tier "
            f"`conviction` keeps the record._")


def _fmt_trend_rider(p) -> str:
    return (f"🌊 *TREND RIDER* — {p['base']} {p['side']} "
            f"(daily 20d breakout +{p.get('score', 0):g}%)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_daily-breakout rider — hold {p.get('hold', 'days')}. "
            f"Validated +0.15-0.32R/trade; desk 14d form was the "
            f"hottest tier when you re-enabled this buzz (ZBT case). "
            f"Kronos is COLOR not a gate here._")


def _fmt_prime(p) -> str:
    lanes = ", ".join(p.get("early_lanes") or [])
    prog = p.get("_prog")
    zone = (f" · 🟢 IN ZONE ({prog * 100:.0f}% to TP1)"
            if prog is not None else "")
    return (f"⭐🚀 *PRIME ENTRY* — {p['base']} {p['side']} "
            f"(STRONG {p['score']:.0f}){zone}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_early-lane cell ({lanes}) — 81.3% / +0.066R on 8 months. "
            f"Take while green; never chase._")


def _fmt_one(p) -> str:
    prog = p.get("_prog")
    zone = (f" · 🟢 IN ZONE ({prog * 100:.0f}% to TP1)"
            if prog is not None else "")
    return (f"👑 *ONE TRADE* — {p['base']} {p['side']} "
            f"[{p.get('_one_label', '')}]{zone}\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"R:R *{p.get('_one_rr', 0):g}x* to TP1 · "
            f"live `{p.get('_one_live', 0):g}` · "
            f"24h {p.get('_one_c24', 0):+g}% · 6h {p.get('_one_c6', 0):+g}%\n"
            f"_THE single best clean setup on the whole board right now — "
            f"in-zone, conf 70+, not extended, pays >=1x risk. Silence "
            f"means nothing qualifies. Stop is server-side, always._")


def _fmt_ts(p) -> str:
    return (f"🎯 *TRUE SIGNAL* — {p['base']} {p['side']} "
            f"[{p.get('ts_source', '')}]\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"R:R *{p.get('ts_rr', 0):g}x* · zone "
            f"{float(p.get('ts_prog') or 0) * 100:.0f}% · 🔮 kronos "
            f"{p.get('kr_dir')} {float(p.get('kr_exp') or 0):+.1f}%/24h\n"
            f"_ALL FIVE GATES PASSED incl the 🔮 top layer (backtest: "
            f"agree bucket 81.8% win / +0.26R vs baseline losing). "
            f"Rare by design. Desk tier 🎯 is proving it forward — "
            f"honest record on the Decision Desk._")


def _fmt_kr_approved(p) -> str:
    return (f"🔮✅ *KRONOS APPROVED* — {p['base']} {p['side']} "
            f"[{p.get('kr_src', '')}]\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"🔮 kronos {p.get('kr_dir')} "
            f"{float(p.get('kr_exp') or 0):+.1f}%/24h — AGREES\n"
            f"_The validated agree bucket: 86% win / +0.34R on our "
            f"entries (n=138 backtest). Live desk tier 🔮 is the "
            f"binding jury. Stop server-side, always._")


def _fmt_prime_board(p) -> str:
    # ⭐ TOP BAND (user 2026-08-07 "set to the best shape/highest
    # score"): score>=85 inside the funnel went 10-for-10 (+0.77R) in
    # the mining — FLAGGED, not gated (n=10 too thin to bet the board
    # on; the 80-floor funnel is the proven 78.8%/+0.42R shape).
    _top = float(p.get("score") or 0) >= 85
    _tb = "\n⭐ *TOP BAND* — 10-for-10 in mining, size with confidence" \
        if _top else ""
    return (f"🥇 *PRIME* — {p['base']} {p['side']} "
            f"({p.get('tier', 'HIGH')} {p.get('score', 0):.0f} · "
            f"30m-confirmed)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}` — *BANK AT TP1* (the measured "
            f"construct; riding tested worse){_tb}\n"
            f"_The winners-only board: score-80+ fire + mid-band "
            f"volatility + calm 6h ({p.get('c6', 0):+.1f}%). Measured "
            f"78.8% win · +0.42R/trade after fees (n=33/108d). Desk "
            f"tier 🥇 proving forward._")


def _fmt_preburst(p) -> str:
    return (f"🌋 *PRE-BURST* — {p['base']} {p['side']} (quiet coil + 🔮 "
            f"{p.get('kr_dir')} {float(p.get('kr_exp') or 0):+.1f}%/24h)\n"
            f"⚠️ STOP-ENTRY only: enter ON BREAK of `{p['entry']:g}` "
            f"(now `{float(p.get('last_px') or 0):g}`)\n"
            f"SL `{p['stop']:g}` (opposite edge) · TP1 `{p['tp1']:g}`"
            f"{_tp2(p)}\n"
            f"_Loaded base, caught BEFORE the burst (PORTAL construct). "
            f"Do NOT enter early — the shakeout punishes it (measured "
            f"-0.21R); the edge-break entry measured +0.12R/61%. If it "
            f"never breaks, there is no trade. Desk 🌋 proving. SIZE "
            f"SMALL._")


def _fmt_apex(p) -> str:
    edges = " · ".join(p.get("edges", []))
    return (f"🏆🔥 *APEX ×{p.get('apex', 0)}* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_best of the best — {edges} all agree_")


def _kr_note(p) -> str:
    """🔮 verdict line for alert messages (user 2026-08-03 + 2026-08-09
    'it should show kronos agreed or not' — the line is now on EVERY
    buzz): cached read when fresh, ONE direct forecast at buzz time
    otherwise (buzzes are rare; ~2.3s is fine), FLAT and no-read
    states spelled out instead of silently omitted."""
    try:
        _hit = _KR_CACHE.get(p.get("symbol"))
        s = _hit["s"] if _hit and time.time() - _hit["t"] <= KR_TTL \
            else None
        if s is None:
            try:
                if kf.available():
                    s = kf.forecast(p.get("symbol"), "1h", horizon=24)
                    if s:
                        _KR_CACHE[p["symbol"]] = {"t": time.time(),
                                                  "s": s}
            except Exception:
                s = None
        if not s:
            return "\n🔮 kronos: no read available"
        d = s.get("direction")
        _e = float(s.get("exp_move_pct") or 0)
        if d == "FLAT":
            return (f"\n🔮 kronos FLAT {_e:+.1f}%/24h — no conviction "
                    f"either way")
        agree = ((d == "UP" and p.get("side") == "LONG")
                 or (d == "DOWN" and p.get("side") == "SHORT"))
        return (f"\n🔮 kronos {d} {_e:+.1f}%/24h — "
                f"{'✅ AGREES (validated +0.34R edge)' if agree else '⚠️ CONFLICTS — caution'}")
    except Exception:
        return "\n🔮 kronos: no read available"


def _fmt_elite_early(p) -> str:
    return (f"🌟 *EARLY ELITE* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · {p.get('lanes', 0)} lanes)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}{_kr_note(p)}\n"
            f"_ELITE MAX/HIGH + 2+ lanes + TAKE NOW 🔥 HOT — early "
            f"high-conviction entry_")


def _fmt_elite_conv(p) -> str:
    """💎 every MAX/HIGH elite conviction fire (user 2026-08-15:
    "approved or unapproved, high and max should be notified")."""
    _ap = ("🚀 approved" if p.get("appr")
           else "⚠️ unapproved BUT 🔮 KRONOS AGREES — the rescue rule"
           if p.get("kr_rescue")
           else "⚠️ unapproved — size accordingly"
           if p.get("requal") else "approval unknown")
    if p.get("requal"):
        # 🚪 SAME DOOR stamp (user 2026-08-23: "same door is good
        # lets build it") — re-fires at an UNCHANGED level measured
        # 77.8% confirmed vs ~54% when the level already moved.
        _dr = ("\n🚪 SAME DOOR — re-fired at the SAME level (the "
               "77.8% shape; desk tier same_door proves it live)"
               if p.get("same_door") else
               "\n⚠️ level already moved — later entry (the ~50% "
               "shape, be picky)"
               if p.get("same_door") is False else "")
        return (f"💎🔄 *ELITE CONVICTION — RE-QUALIFIED* — {p['base']} "
                f"{p['side']} ({p['tier']} {p['score']:.0f} · {_ap})\n"
                f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
                f"TP1 `{p['tp1']:g}`{_tp2(p)}{_dr}{_kr_note(p)}\n"
                f"_a coin you already traded is back: it went quiet, "
                f"now it qualifies MAX/HIGH again — a NEW setup, new "
                f"plan, new stop. Fires approved or unapproved by "
                f"your order; the chip above says which._")
    return (f"💎 *ELITE CONVICTION* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · {_ap})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}{_kr_note(p)}\n"
            f"_the board that caught ACE, 2Z and PORTAL — MAX/HIGH "
            f"the moment it fires. Approved fires win 65.5% vs 48.5% "
            f"unapproved: the chip is the tell. Approved ones also "
            f"arm the 💥 60s trigger watch._")


def _fmt_fresh(p) -> str:
    return (f"🌱 *FRESH MOVER* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_first signal in 72h + TAKE NOW 🔥 HOT — validated 74% · "
            f"1.5R_")


def cycle() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # scan_n 60 -> 100 (user 2026-08-06: "30 coins is far less, it
    # should be 100") — every stream downstream (elite, fast30, PRIME,
    # 💯, ignition, takenow) now hunts the full top-100 by volume.
    # WORKER_SCAN_N env overrides if the Render cycle ever overruns.
    r = scan_core.scan_all(
        scan_n=int(getattr(config, "WORKER_SCAN_N", 100)),
        min_conv=MIN_CONV)
    sst1, takenow = r["sst1"], r["takenow"]
    apex = r.get("apex", [])
    lb_all = r.get("leaderboard", [])
    lb = [p for p in lb_all if float(p.get("score") or 0) >= LB_MIN]
    regime = (r.get("regime") or {}).get("regime", "?")

    # 🌱 freshness — first fire in 72h (excluding the current <2h sighting
    # streak), computed from the brain's own 24/7 memory BEFORE storing.
    # Validated cell (backtest_fresh2, 40 coins): FRESH+HOT = 74.1% / 1.5R.
    # Descriptive only — alerts stay the locked four streams.
    _now = time.time()
    for p in takenow:
        try:
            p["fresh"] = not store.seen_between(
                "takenow", p["symbol"], p["side"],
                _now - 72 * 3600, _now - 2 * 3600)
        except Exception:
            p["fresh"] = False

    # 🌙 LunarCrush social capture (user-approved 2026-07-11): ONE API call
    # per cycle; galaxy score / alt rank / sentiment ride along inside each
    # stored signal's extra JSON so the desk can validate later whether
    # social predicts wins. Data capture ONLY — no gating, no alert change.
    _lc_rows: list = []
    try:
        _lc_rows = lunarcrush.coin_list()
        _lc_map = lunarcrush.top_coins(_lc_rows)
    except Exception:
        _lc_map = {}
    if _lc_map:
        for _sigs in (apex, sst1, takenow, lb_all, r.get("elite", []),
                      r.get("early_strong", []), r.get("trend", [])):
            for p in _sigs:
                _s = _lc_map.get(str(p.get("base", "")).upper())
                if _s:
                    p["social"] = _s
    # market-wide social mood — one line in the daily reports
    _mood_line = ""
    try:
        _mood = lunarcrush.crypto_social(_lc_rows) if _lc_rows else None
        if _mood:
            _g = (f" · galaxy {_mood['galaxy']:.0f}"
                  if _mood.get("galaxy") else "")
            _mood_line = (f"🌙 social: {_mood['mood']} "
                          f"(sentiment {_mood['sentiment']:.0f}{_g})")
    except Exception:
        pass
    # ⚠️ Polymarket event radar (free public API, cached 30 min): binary
    # macro/crypto events resolving within 72h — a heads-up line in the
    # daily reports. Informational only; gates nothing.
    _event_line = ""
    try:
        _event_line = polymarket_events.radar_line(72)
    except Exception:
        pass

    # Store every best-signal this cycle (history for pattern analysis).
    # 🎯 conf stamped at record time (user 2026-08-28: "win rate at
    # confidence 87 and 98") — the score was buzz-only before, so no
    # historical slice exists; from today every apex/best/elite
    # record carries it in `extra` for exact slicing.
    for p in apex:
        try:
            p["conf"] = best_board.confidence(p.get("symbol"),
                                              p.get("side"))
        except Exception:
            pass
        store.record_signal("apex", p)
    for p in sst1:
        store.record_signal("sst1", p)
    for p in takenow:
        store.record_signal("takenow", p)
    for p in lb_all:
        store.record_signal("leaderboard", p)
    for p in r.get("elite", []):
        store.record_signal("elite", p)
    # ⚡ EARLY MOVERS (STRONG + TAKE_NOW + HOT) — board-only stream
    # (user 2026-07-05): stored + displayed, never alerted.
    for p in r.get("early_strong", []):
        store.record_signal("early_strong", p)
    # 🌊 TREND RIDER — the money core (user-approved 2026-07-08)
    for p in r.get("trend", []):
        store.record_signal("trend", p)

    # 🎯 TP2 RIDES (user 2026-07-05, ADA case): after a best-signal's TP1 is
    # hit, keep tracking it while momentum stays intact (trend + hot) so the
    # runner to TP2 stays visible. Board-only; never alerted.
    try:
        _rc: dict = {}
        for _stream in ("apex", "takenow", "early_strong"):
            for row in store.recent_by_stream(_stream, 20):
                ts0 = float(row.get("ts") or 0)
                if _now - ts0 > 48 * 3600:
                    continue
                k = (row.get("symbol"), row.get("side"))
                if k not in _rc:      # rows come newest-first
                    _rc[k] = row
        rides = scan_core.tp2_rides(list(_rc.values()), max_checks=10)
        for p in rides:
            store.record_signal("tp2ride", p)
    except Exception as exc:
        rides = []
        print("  tp2ride error:", exc, flush=True)

    # Alert policy (user 2026-07-05) — EXACTLY five streams, essential-grade
    # only. One buzz per setup, richest label wins:
    #   1. 🏆 APEX
    #   2. 🌟 EARLY ELITE — ELITE MAX/HIGH + 2+ lanes + TAKE_NOW + HOT
    #   3. 🌱 FRESH — first fire 72h + TAKE_NOW + HOT
    #   4. ✅🔥 TAKE NOW + HOT (the rest)
    #   5. 🚀 EARLY MOVER big-hit — STRONG + TAKE_NOW + HOT + early lanes
    #      (validated: 22% reach 2R+, 65% win — the VANRY-hunter subset only)
    # REMOVED: Leaderboard alerts (heads-up tier, ~33-45% forward — weakest
    # link; still stored + shown in-app). SST1 standalone removed earlier.
    n_alerts = 0

    # 🟢 DESK AUTO-GATE (user 2026-07-25: "skip the ones that aren't
    # good"): each stream buzzes only while its own desk tier is GREEN.
    # Degraded tiers silence themselves; re-proven tiers speak again.
    # Fail-open when the desk is unreadable. IGNITION is exempt (the
    # user wants it while unproven, by explicit call).
    try:
        _greens_alert = {rec["tier"] for rec in
                         shadow_trader.tier_records() if rec.get("green")}
    except Exception:
        _greens_alert = None

    def _push(items, key_prefix, fmt, conf_gated=True, min_conf=None,
              tier=None):
        nonlocal n_alerts
        for p in items:
            if (tier is not None and _greens_alert is not None
                    and tier not in _greens_alert):
                continue          # tier's live record not green — silent
            # 🏦 B-stock buzz gate — one shared rule (_bstock_quiet):
            # buzzes ON since 2026-08-17 (BSTOCK_BUZZ); money stays
            # gated separately in demo_account until validation.
            if _bstock_quiet(p.get("symbol")):
                continue
            # 🎯 confidence floor (user 2026-07-14): buzz only stacked
            # max-confidence setups; everything else stays board-only.
            # min_conf overrides the floor per stream (user 2026-07-18:
            # FRESH buzzes regardless of stacking — pass min_conf=0).
            if conf_gated:
                _cf = best_board.confidence(p.get("symbol"),
                                            p.get("side"))
                p["_conf"] = _cf
                _floor = ALERT_CONF_MIN if min_conf is None else min_conf
                if _cf < _floor:
                    continue
            if store.should_alert(f"{key_prefix}:{p['symbol']}:{p['side']}",
                                  COOLDOWN):
                _msg = fmt(p)
                # 🤝🌡 conf rebuild chips (2026-09-04, display-only)
                _chips = _pair_chips(p.get("symbol"), p.get("side"))
                if p.get("_conf") is not None and "\n" in _msg:
                    _msg = _msg.replace(
                        "\n", f" · 🎯 conf {p['_conf']}/100"
                              f"{_chips}\n", 1)
                elif _chips and "\n" in _msg:
                    _msg = _msg.replace("\n", f"{_chips}\n", 1)
                ok, msg = tg.send(_msg)
                n_alerts += 1 if ok else 0
                if not ok:
                    print("  tg:", msg, flush=True)

    def _push_elite(items):
        """💎 buzzes on a 2h re-fire clock for BOTH MAX and HIGH
        (user 2026-08-23 final call: "max/high or it have reconfirm
        elite entry" — top-confidence signals should tell; the 6h
        silence is out). One shared key per (coin, side), so a
        re-fire never double-buzzes; a card quietly persisting
        re-buzzes at most every 2h.
        📵 BUZZ DIET (user 2026-08-29, amended same day: "we can go
        with 55"): elite conv buzzes need 🎯 conf >= 55 (between the
        1-vote 48% and 2-vote 74% bands — the user's chosen line;
        65 was the measured cliff). The 💎✅ confirmed re-entry buzz
        stays UNGATED but SHOWS its conf, both by explicit call.
        Revert: delete the _cf9 gate below."""
        nonlocal n_alerts
        for _pmx in items:
            try:
                if _bstock_quiet(_pmx.get("symbol")):
                    continue
                _cf9 = _pmx.get("conf")
                if _cf9 is None:
                    try:
                        _cf9 = best_board.confidence(
                            _pmx.get("symbol"), _pmx.get("side"))
                    except Exception:
                        _cf9 = None
                # 📵 ELITE GATE — FINAL (user 2026-08-31 revert:
                # "elite conviction fires approved unapproved with
                # high and max with confidence score set to 40 and
                # above, also add edge to it"). Back to the original
                # design — EVERY MAX/HIGH fire speaks, approved or
                # not (the PORTAL lesson), with a conf FLOOR at 40
                # rather than a filter: an elite-only card scores
                # exactly 40 (W_ELITE_WATCH 0.75), so this admits the
                # whole stream and only blocks a card that somehow
                # scores beneath its own board weight. The edge-45
                # experiment is withdrawn — its 45-over-65 advantage
                # vanished in the recent half (53.1 vs 53.3), so it
                # was never both-halves validated. Both scores now
                # ride the buzz as INFORMATION: 🎯 conf (board
                # agreement) + ⚡ edge (candle heat). The validated
                # discriminator stays the 🚀 approval chip (65.5% vs
                # 48.5%). Revert: change the 40 below.
                if _cf9 is not None and _cf9 < 40:
                    continue
                if store.should_alert(
                        f"eliteconv:{_pmx['symbol']}:{_pmx['side']}",
                        2 * 3600):
                    _msg9 = _fmt_elite_conv(_pmx)
                    # 🎯 board-conf + ⚡ edge-conf side by side on
                    # elite only (user 2026-08-31). Two different
                    # measures: board = how many boards agree,
                    # edge = how hot this coin's own candles are.
                    # Edge on elite peaks at 45 (hump, not ladder) —
                    # the tag says so rather than implying higher is
                    # better. Neither gates anything here.
                    _eg9 = _pmx.get("edge_conf")
                    _cbits = []
                    if _cf9 is not None:
                        _cbits.append(f"🎯 conf {_cf9}/100")
                    _ht9 = _pmx.get("heat")
                    if _ht9 is not None:
                        _cbits.append(f"🌡 heat {_ht9}")
                    if _eg9 is not None:
                        _etag = (" sweet spot" if _eg9 == 45
                                 else " hot — may be late"
                                 if _eg9 >= 85 else "")
                        _cbits.append(f"⚡ edge {_eg9}/100{_etag}")
                    if _cbits and "\n" in _msg9:
                        _msg9 = _msg9.replace(
                            "\n", " · " + " · ".join(_cbits) + "\n", 1)
                    ok, _m9 = tg.send(_msg9)
                    n_alerts += 1 if ok else 0
            except Exception as _mx_exc:
                print("  elite buzz error:", _mx_exc, flush=True)

    tn_hot = [p for p in takenow if p.get("hot")]
    elite_early = [p for p in tn_hot
                   if p.get("tier") in ("MAX", "HIGH")
                   and int(p.get("lanes") or 0) >= 2]
    _ee_keys = {(p["symbol"], p["side"]) for p in elite_early}
    # 🌱 FRESH stream (user-approved add-on 2026-07-05): first fire in 72h +
    # TAKE_NOW + HOT (validated 74% / 1.5R). One buzz per setup — priority:
    # APEX > EARLY ELITE > FRESH > TAKE NOW rest > leaderboard.
    fresh_m = [p for p in tn_hot if p.get("fresh")
               and (p["symbol"], p["side"]) not in _ee_keys]
    _fr_keys = _ee_keys | {(p["symbol"], p["side"]) for p in fresh_m}
    tn_rest = [p for p in tn_hot
               if (p["symbol"], p["side"]) not in _fr_keys]
    # 🚀 EARLY MOVER big-hit subset (STRONG tier — no overlap with the
    # takenow stream, which is MAX/HIGH + SST1 only).
    em_big = [p for p in r.get("early_strong", [])
              if p.get("early_lanes")]

    # 💎 BEST TRADE ZONE (user 2026-07-11): ONE consolidated board — every
    # validated lane votes on the same candidate (weights = each system's
    # validated after-fee record, incl the 🌊🟢 spot-driven OI cell). Only
    # stacked confluence or a top cell qualifies. Stored + desk-taken +
    # alerted with the in-zone gate.
    try:
        best = best_board.compose(r.get("trend", []), apex, elite_early,
                                  fresh_m, tn_hot, em_big,
                                  elite_watch=r.get("elite", []))
    except Exception as exc:
        best = []
        print("  best_board error:", exc, flush=True)
    for p in best:
        try:
            p["conf"] = best_board.confidence(p.get("symbol"),
                                              p.get("side"))
        except Exception:
            pass
        store.record_signal("best", p)

    def _in_zone(p):
        """🟢 gate: alert only while <=25% of entry→TP1 is gone and the
        stop is untouched. Price-fetch failure fails open (alerts fire
        at signal birth when progression is ~0 by construction)."""
        try:
            _lv = binance_client.get_ticker_price(p["symbol"])
            _e, _t1 = float(p["entry"]), float(p["tp1"])
            _st = float(p["stop"])
            if not _lv or _t1 == _e:
                return True
            _f = ((_lv - _e) / (_t1 - _e) if p["side"] == "LONG"
                  else (_e - _lv) / (_e - _t1))
            _dd = _lv <= _st if p["side"] == "LONG" else _lv >= _st
            if _dd or _f > 0.25:
                return False
            p["_prog"] = _f
            return True
        except Exception:
            return True

    # Alert policy (user 2026-07-18): INDEPENDENT streams — every tier
    # buzzes on its own; duplicates across streams are fine ("it can
    # buzz with multiple notifications, that is ok"). 💎 BEST still
    # fires on top when systems agree. The 85-conf floor now applies
    # only where min_conf isn't overridden; 🎯 conf shown everywhere.
    # In-zone gates stay on the entry-timing-sensitive streams (no
    # chasing). 🌊 TREND RIDER entry fires RE-ENABLED 2026-08-06 by
    # explicit user call (ZBT +51% ripped with no buzz; tier was the
    # desk's hottest at +35.1R/14d) — entry fires only, the 2026-07-13
    # removal of health pings stands. The lean proven-only gating
    # stays shelved until the keyword "Lets deploy The new system".
    # 🚨 IGNITION (user 2026-07-25: "fast and early even if it fails —
    # I need that anyhow"): at-fire ELITE MAX/HIGH + validated approval
    # gate. Earliest buzz in the system; honest ~50-65% odds stated in
    # every message; desk shadow tier proves it forward; the LIVE
    # executor does NOT trade it unless it ever earns green + user go.
    try:
        _ign = ignition.scan(r.get("elite", []))
    except Exception as _ign_exc:
        _ign = []
        print("  ignition error:", _ign_exc, flush=True)
    for p in _ign:
        store.record_signal("ignition", p)
    # 2026-08-15 user order 7: IGNITION buzz muted until its desk
    # record turns GREEN (record was on a losing spree; this reverses
    # the 07-25 while-unproven exemption on his own call). The tier=
    # gate auto-unmutes the day the record goes green.
    _push([p for p in _ign if _in_zone(p)], "ignition", _fmt_ignition,
          min_conf=0, tier="ignition")
    # ⚡🚨 STRONG IGNITION (user 2026-08-14, the PIXEL case): STRONG
    # at-fire + hard burst>=85 same side — the one cell of the at-fire
    # radius study green in both halves (55.2%/+0.236R, n=62; plain
    # STRONG at-fire and even 🚀-approved STRONG are noise). Buzz +
    # desk proving tier; NO demo money until the live record is green.
    # No greens gate — like IGNITION, wanted while unproven (the whole
    # point is the early look).
    try:
        _igs = ignition.scan_strong(r.get("strong", []))
    except Exception as _igs_exc:
        _igs = []
        print("  ign_strong error:", _igs_exc, flush=True)
    for p in _igs:
        store.record_signal("ignition_strong", p)
    # 2026-08-28 user order: ⚡🚨 STRONG IGNITION buzz OFF ("I dont
    # want the telegram notification for surge and strong ignitions
    # now") — 🕵️ OI LOAD is the upgraded pre-spike layer. Board +
    # desk tier keep recording; re-enable is this one line.
    # _push([p for p in _igs if _in_zone(p)], "ignstrong",
    #       _fmt_ign_strong, min_conf=0)
    # ⏱ FAST CONFIRM 30m (user 2026-07-25: "remove 1h, 30 min confirm").
    # The proven tiers + executor STAY on 1h (his own tests measured 30m
    # as the loser twice this week); this is the sanctioned early outlet
    # — labeled stream + silent desk tier "fast30" earning its record.
    try:
        _f30 = fast_confirm.scan(r.get("elite", []))
    except Exception as _f30_exc:
        _f30 = []
        print("  fast30 error:", _f30_exc, flush=True)
    for p in _f30:
        store.record_signal("fast30", p)
    # ⏱ fast30 buzz PAUSED 2026-08-11 (user: "for 30m confirm pause it
    # for now"). Everything downstream is untouched — fast30 still
    # feeds 💯 CONVICTION and 🥇 PRIME, still records its desk tier,
    # still shows on the boards. Only the Telegram stream is quiet.
    # Restore by uncommenting on his word.
    # _push([p for p in _f30 if _in_zone(p)], "fast30", _fmt_fast30,
    #       min_conf=0)
    # 🥇 PRIME (user 2026-08-05: "deploy the board") — the winners-only
    # construct mined from 134 entries / 108 days: elite HIGH fire +
    # ATR 40-80 band + calm 6h -> 30m confirm -> bank at TP1.
    # Measured 74.5% win / +0.31R after fees (n=47); quiet-ATR,
    # already-moving and MAX-tier entries measured NEGATIVE and are
    # excluded by construction. Desk tier proves it forward.
    def _atr_pctile(sym):
        """ATR14 percentile vs its trailing 100 on 1h — the EXACT mined
        definition (backtest_elite_edge). fast30 picks carry no atr_pct
        key, so the old `p.get("atr_pct") or 0` read 0 every cycle and
        PRIME could never fire (user caught it 2026-08-06: "not a
        single fire since development")."""
        import numpy as _np
        import pandas as _pd
        d = binance_client.get_klines(sym, "1h", limit=150)
        if d is None or len(d) < 40:
            return None
        _h = d["high"].astype(float).to_numpy()
        _l = d["low"].astype(float).to_numpy()
        _c = d["close"].astype(float).to_numpy()
        _tr = _np.maximum(_h[1:] - _l[1:], _np.maximum(
            abs(_h[1:] - _c[:-1]), abs(_l[1:] - _c[:-1])))
        _atr = _pd.Series(_np.concatenate([[_tr[0]], _tr])).rolling(
            14, min_periods=1).mean().to_numpy()
        _t = len(_atr) - 1
        return float((_atr[max(0, _t - 100):_t] <= _atr[_t - 1]).mean()
                     * 100)

    _prime = []
    try:
        for p in _f30:
            # user 2026-08-06 "make it 80 not 82": floor is score>=80,
            # any tier except MAX (MAX measured +0.06R vs +0.33R).
            # .prime80.py check: the widened band added ZERO historical
            # entries inside the ATR+calm filters, so the validated
            # cell (75%/+0.33R n=28) is unchanged — live it can only
            # widen the funnel.
            if (float(p.get("score") or 0) < 80
                    or p.get("tier") == "MAX"):
                continue
            _ap = p.get("atr_pct")
            if _ap is None:
                try:
                    _ap = _atr_pctile(p["symbol"])
                except Exception:
                    _ap = None
            if _ap is None or not (40 <= float(_ap) < 80):
                continue
            try:
                _c24p, _c6p = one_trade._extension(p["symbol"])
            except Exception:
                continue
            # calm gate 3->4% (user 2026-08-06, .calm_bands.py: <4%
            # measured 78.8%/+0.42R n=33 vs <3% 75%/+0.33R n=28; the
            # added 3-4% band went 5-for-5. 4%+ tail stays out —
            # unmeasured, n=4).
            if abs(_c6p) < 4.0:
                _p2 = dict(p)
                _p2["atr_pct"] = round(float(_ap))
                _p2["c6"] = round(_c6p, 1)
                _prime.append(_p2)
    except Exception as _pr_exc:
        _prime = []
        print("  prime error:", _pr_exc, flush=True)
    for p in _prime:
        store.record_signal("prime", p)
    # 2026-08-15 user order 7: PRIME buzz muted until GREEN.
    # 📵 diet amendment (user 2026-08-29: "dont remove... prime") —
    # restored to its pre-diet form: the tier gate keeps it silent
    # until its desk record turns green, then it speaks by itself.
    _push(list(_prime), "prime", _fmt_prime_board, min_conf=0,
          tier="prime")
    # 📡 SURGE RADAR (user 2026-07-26, LPT case): whole-market fresh-
    # pump ignition — fires only in a pump's first ~2h, refuses
    # extended chases. Unproven: labeled stream + desk tier proving.
    try:
        _srg = surge_radar.scan()
    except Exception as _srg_exc:
        _srg = []
        print("  surge error:", _srg_exc, flush=True)
    for p in _srg:
        store.record_signal("surge", p)
    # 2026-08-28 user order: 📡 SURGE buzz OFF ("I dont want the
    # telegram notification for surge and strong ignitions now") —
    # 🕵️ OI LOAD is the upgraded pre-spike layer for this mover
    # class. Board + desk tier keep recording; re-enable is this
    # one line. (History: muted 07-26, restored 08-06 on the green
    # record, muted again today on user call.)
    # _push([p for p in _srg if _in_zone(p)], "surge", _fmt_surge,
    #       min_conf=0, tier="surge")
    # 📵 BUZZ DIET (user 2026-08-29): BEST ZONE + APEX buzz only at
    # 🎯 conf >= 70 (the measured edge zone: 73-78% win vs 38-48%
    # below; 80 was considered and rejected — it cuts the 74% band
    # for ~4pts). Revert: best had the default 85 floor (no min_conf
    # arg), apex had min_conf=0.
    # 2026-09-03 user order: "bring back the best of the best to the
    # notification on my cellphone" — the stream had gone silent NOT by
    # any conf gate but because best_board's 14d desk form turned
    # negative and the greens gate muted the tier. tier=None exempts
    # BEST from that gate (the conf>=70 floor stands); the desk tier
    # still records everything.
    # 2026-09-04 user order: "best of the best zone is still not giving
    # notification — make it live." Diagnosis: silencer #2. The _push
    # conf gate recomputes best_board.confidence from FORM-WEIGHTED
    # votes; with most tiers' 14d form red, voters are halved and a
    # qualifying 💎 card can score 55-65 at buzz time — dying on the 70
    # floor even though the card shows 85+ on the page. The stream is
    # already self-gated by its own qualification bar (and deflation
    # double-counts form), so the floor drops to 0. Revert: min_conf=70.
    # 2026-09-05 later: user order "best and one trade as per the
    # confidence score previously" — BEST floor back to 70 (the Aug 29
    # diet number). tier stays None: the form mute stays off, only the
    # conf floor gates. Same deflation note as apex applies.
    # 2026-09-05 final: same user order for BEST — audible regardless.
    # Revert: min_conf=70.
    _push([p for p in best if _in_zone(p)], "best", _fmt_best,
          min_conf=0, tier=None)
    # 2026-09-05 user order: "apex seems closed... can we have it back
    # please and best of the best and one trade as well" — same two
    # silencers as BEST: the greens gate (14d form) and the conf-70
    # floor bitten by form-deflated votes. tier=None + min_conf=0
    # restores the stream; HONEST NOTE: the 70 gate was the one
    # measured earner (it silenced a 32%/-0.228R band) on the OLD
    # undeflated scale — on today's deflated scale 70 is nearly
    # unreachable, so the floor had become a mute, not a filter.
    # Revert: min_conf=70, tier="apex".
    # 2026-09-05 later: user set the APEX floor back to 70 ("apex
    # confidence score 70 above") — the measured gate (it silenced a
    # 32%/-0.228R band). tier stays None so the 14d-form mute cannot
    # silently kill the stream again; only the conf floor gates.
    # NOTE: with form-deflated votes, 70 is a HIGH bar in red regimes
    # — fewer apex buzzes until tier forms recover, by design.
    # 2026-09-06 (user: "the confidence score for apex should be above
    # 70"): APEX floor at 70 — the measured gate (silenced a
    # 32%/-0.228R band). tier stays None (no form mute; only the conf
    # floor filters). Deflation note stands: 70 is a high bar in red
    # regimes, apex buzzes will be rare until tier forms recover.
    # Revert to audible-always: min_conf=0.
    _push(apex, "apex", _fmt_apex, min_conf=70, tier=None)
    # 2026-08-15 user order: 🌟 EARLY ELITE buzzes ALWAYS — no greens
    # gate. Kronos disagreeing is fine ("if kronos dont agree thats
    # ok"): the 🔮 line on every buzz already spells out all three
    # states — AGREES / CONFLICTS / FLAT (no conviction either way).
    # 📵 diet amendment (user same day: "dont remove... early elite")
    # — 🌟 EARLY ELITE restored to its pre-diet ALWAYS form.
    _push(elite_early, "elite_early", _fmt_elite_early, min_conf=0)
    # 🦅 EAGLE EYE enrol (user 2026-08-29): every 🌟 EARLY ELITE and
    # 💎 BEST card at 🎯 conf >= 70 goes under the daemon's 60s
    # fast-clock watch for 48h — falls included. The daemon watches;
    # this just keeps the roster fresh.
    try:
        _eg_now = time.time()
        for _ep in list(elite_early) + list(best[:8]):
            if not (_ep.get("entry") and _ep.get("stop")
                    and _ep.get("tp1")):
                continue
            try:
                _ec9 = best_board.confidence(_ep.get("symbol"),
                                             _ep.get("side"))
            except Exception:
                continue
            if _ec9 < 70:
                continue
            _ekey = (_ep["symbol"], _ep["side"])
            with _TRIG_LOCK:
                _old9 = _EAGLE_WATCH.get(_ekey) or {}
                _EAGLE_WATCH[_ekey] = {
                    "symbol": _ep["symbol"],
                    "base": _ep.get("base"), "side": _ep["side"],
                    "tier": _ep.get("tier"),
                    "score": _ep.get("score"), "conf": _ec9,
                    "entry": _ep.get("entry"),
                    "stop": _ep.get("stop"),
                    "tp1": _ep.get("tp1"), "tp2": _ep.get("tp2"),
                    "added_at": _old9.get("added_at", _eg_now),
                    "last_chk": _old9.get("last_chk", 0)}
        with _TRIG_LOCK:
            _ex9 = len(_EAGLE_WATCH) - EAGLE_MAX
            if _ex9 > 0:
                for _k9 in sorted(
                        _EAGLE_WATCH,
                        key=lambda k: _EAGLE_WATCH[k]
                        .get("added_at", 0))[:_ex9]:
                    _EAGLE_WATCH.pop(_k9, None)
    except Exception as _eg_exc:
        print("  eagle enrol error:", _eg_exc, flush=True)
    # 💎 ELITE CONVICTION fires — EVERY MAX/HIGH, approved or not
    # (user 2026-08-15, the PORTAL lesson: HIGH 87 fired 47h before a
    # +50% move and no buzz existed for it). The approval verdict and
    # kronos line ride on each message; approved ones also feed the
    # demo pool and the 💥 trigger arms below. 6h per-coin cooldown.
    _ec_mh = []
    for _ec in (r.get("elite") or []):
        if (_ec.get("tier") or "").upper() not in ("MAX", "HIGH"):
            continue
        _ec_b9 = 0.0
        try:
            _ec_df = binance_client.get_klines(_ec["symbol"], "1h",
                                               limit=120)
            _ec_ok = _vb_w.lane_approved(_ec_df, _ec.get("side"))
            # the BURST edge — same read that lights the yellow ⚡
            # edge chip on the openable cards (>=78, card's own side)
            _b9, _bd9, _ = _vb_w.lane_velocity_burst(_ec_df)
            if (_bd9 or "").upper() == \
                    (_ec.get("side") or "").upper():
                _ec_b9 = float(_b9)
        except Exception:
            _ec_ok = None
        _ec2 = dict(_ec)
        _ec2["appr"] = _ec_ok
        _ec2["burst_live"] = _ec_b9
        # ⚡ EDGE-conf alongside the board-conf (user 2026-08-31:
        # "can we have the confidence score and edge confidence both
        # on elite conviction only?"). Free here — the 1h frame is
        # already fetched above for approval + burst. Measured shape
        # on elite (1,232 filled entries): it is a HUMP not a ladder
        # — edge 45 was the best cell in both entry styles (54.4%
        # at-fire / 72.8% confirmed) while edge 85 UNDERperformed it,
        # consistent with burst>=85 at an elite fire measuring
        # -0.218R: a screaming chart on a fire candle means late,
        # not early. Display only — it gates nothing.
        try:
            _ec2["edge_conf"] = _conf_votes(_ec_df,
                                            _ec.get("side"))
        except Exception:
            _ec2["edge_conf"] = None
        # 🌡 conf rebuild (2026-09-04): the continuous ATR percentile
        # — the one candle input that survived validation — rides
        # along for display next to the legacy edge chip.
        try:
            _ec2["heat"] = _atr_heat(_ec_df)
        except Exception:
            _ec2["heat"] = None
        _ec_mh.append(_ec2)
    # 🦅 EAGLE enrol #2 (user 2026-08-29 follow-up: "for every elite
    # conviction... it have its eye to monitor its movement right?"):
    # every 💎 MAX/HIGH fire joins the eagle watch — NO conf gate
    # here, because the validation universe WAS these fires (387 of
    # them, all-comers: 63.5%/+0.221R; MAX cell 69.7%/+0.431R). The
    # heat gate itself does the filtering.
    try:
        _eg_now2 = time.time()
        for _ep2 in _ec_mh:
            if not (_ep2.get("entry") and _ep2.get("stop")
                    and _ep2.get("tp1")):
                continue
            try:
                _ec92 = best_board.confidence(_ep2.get("symbol"),
                                              _ep2.get("side"))
            except Exception:
                _ec92 = None
            _ekey2 = (_ep2["symbol"], _ep2["side"])
            with _TRIG_LOCK:
                _old92 = _EAGLE_WATCH.get(_ekey2) or {}
                _EAGLE_WATCH[_ekey2] = {
                    "symbol": _ep2["symbol"],
                    "base": _ep2.get("base"), "side": _ep2["side"],
                    "tier": _ep2.get("tier"),
                    "score": _ep2.get("score"), "conf": _ec92,
                    "entry": _ep2.get("entry"),
                    "stop": _ep2.get("stop"),
                    "tp1": _ep2.get("tp1"), "tp2": _ep2.get("tp2"),
                    "added_at": _old92.get("added_at", _eg_now2),
                    "last_chk": _old92.get("last_chk", 0)}
    except Exception as _eg_exc2:
        print("  eagle elite enrol error:", _eg_exc2, flush=True)
    # 💎🔥 ELITE + BURST EDGE buzz (user 2026-08-23: "the yellow burst
    # chip on the elite conviction openable trades — apply
    # notification for it on my telegram asap"): the moment an elite
    # MAX/HIGH card carries the live BURST edge (>=78 same side — the
    # exact read behind the yellow ⚡ chip), it buzzes with the full
    # plan. Honest grade per the 2026-08-23 studies: >=85 AT the fire
    # candle measured -0.218R (thrust already spent) — those messages
    # point to the 💎✅ confirmed entry instead of the chase.
    # Notification only; boards unchanged. 6h per-coin cooldown.
    # 2026-08-28 user call ("burst edge... not necessarily for
    # notification"): 💎🔥 buzz OFF — the yellow ⚡ edge chip on the
    # cards carries the same read, approval already buzzes the same
    # coins, and the >=85 variant is a don't-act message. burst_live
    # stays stamped on cards/records. Re-enable: flip _EB_BUZZ.
    _EB_BUZZ = False
    for _p8 in (_ec_mh if _EB_BUZZ else []):
        _b8 = float(_p8.get("burst_live") or 0)
        if _b8 < 78:
            continue
        try:
            if _bstock_quiet(_p8["symbol"]):
                continue
            if not store.should_alert(
                    f"eliteburst:{_p8['symbol']}:{_p8.get('side')}",
                    6 * 3600):
                continue
            _e8 = float(_p8.get("entry") or 0)
            _s8 = float(_p8.get("stop") or 0)
            _t8 = float(_p8.get("tp1") or 0)
            if min(_e8, _s8, _t8) <= 0:
                continue
            _ap8 = ("🚀 approved" if _p8.get("appr")
                    else "approval unknown"
                    if _p8.get("appr") is None else "unapproved")
            _tag8 = ("⚠️ burst maxed AT the fire — chasing this "
                     "candle measured −0.218R; the validated way in "
                     "is the 💎✅ CONFIRMED ENTRY buzz when it prints"
                     if _b8 >= 85 else
                     "🔥 BURST edge live — stacked-edge cards ran "
                     "74-78% in the edge study")
            _t28 = (f" · TP2 `{float(_p8['tp2']):g}`"
                    if _p8.get("tp2") else "")
            # 📵 MUTE (user 2026-09-03, "mute 2"): built on the
            # burst>=78 vote that sign-flipped between halves
            # (+0.160R older / -0.182R recent). Detection + records
            # unchanged. Revert: _mute_ebe -> tg.send.
            _mute_ebe = (lambda _m: (False, "muted"))
            ok, _ = _mute_ebe(
                f"💎🔥 *ELITE + BURST EDGE* — "
                f"{_p8.get('base') or _p8['symbol'].replace('USDT', '')} "
                f"{_p8.get('side')} (elite {_p8.get('tier')} "
                f"{float(_p8.get('score') or 0):.0f} · {_ap8} · "
                f"🔥 burst {_b8:.0f})\n{_tag8}\n"
                f"entry `{_e8:g}` · SL `{_s8:g}` · "
                f"TP1 `{_t8:g}`{_t28}")
            n_alerts += 1 if ok else 0
        except Exception as _exc8:
            print("  eliteburst buzz error:", _exc8, flush=True)
    # NOTE: the buzz for these happens in the kronos section below
    # (the 2026-08-15 rescue rule needs the reads): approved → buzz;
    # unapproved → buzz only if kronos agrees; else silent.
    # 🔥 remember every elite MAX/HIGH fire for the second-leg watch —
    # the window extends while the card keeps firing.
    for _p in _ec_mh:
        _sd9 = (_p.get("side") or "").upper()
        if _sd9 in ("LONG", "SHORT"):
            # 💎🔄 was this coin quiet for RE_GAP_H+ and is now back?
            # That is a NEW setup on a coin already traded — it buzzes
            # regardless of the approval chip (user order).
            _prev9 = _SECOND_LEG.get(_p["symbol"]) or {}
            if _prev9 and (_now - float(_prev9.get("winner_at") or 0)
                           >= RE_GAP_H * 3600):
                _p["requal"] = True
                # 🚪 SAME DOOR (user 2026-08-23, validated
                # backtest_flipreq: re-fires at an UNCHANGED level =
                # 69.2%/+0.346R at-fire, 77.8%/+0.127R confirmed;
                # level moved >= ~1 risk unit = the ~50% chase).
                _lv0 = float(_prev9.get("level") or 0)
                _e9 = float(_p.get("entry") or 0)
                _rk9 = abs(_e9 - float(_p.get("stop") or 0))
                if _lv0 > 0 and _e9 > 0 and _rk9 > 0:
                    _p["same_door"] = bool(
                        abs(_e9 - _lv0) <= 0.8 * _rk9)
                if _p.get("same_door"):
                    # silent desk tier — the live ledger decides if
                    # the 78% survives (n=18 backtest is a hint, not
                    # proof; the 💯 88%->39% lesson).
                    try:
                        _px9 = float(binance_client.get_ticker_price(
                            _p["symbol"]) or 0)
                        if _px9 > 0:
                            store.record_signal("same_door", _p)
                            shadow_trader.open_from_signal(
                                "same_door", _p, _px9)
                    except Exception as _sd_exc:
                        print("  same-door proof error:", _sd_exc,
                              flush=True)
            _SECOND_LEG[_p["symbol"]] = {
                "side": _sd9,
                "base": _p.get("base")
                or _p["symbol"].replace("USDT", ""),
                "score": float(_p.get("score") or 0),
                "level": float(_p.get("entry") or 0),
                "winner_at": _now}
    # 💎✅ ELITE CONFIRMED ENTRY — separate stream, own buzz/board/
    # desk tier. Watches every MAX/HIGH fire for the validated
    # pullback+confirmation entry; elite cards/buzzes untouched.
    try:
        for _p9 in _ec_mh:
            _sd0 = (_p9.get("side") or "").upper()
            _e0 = float(_p9.get("entry") or 0)
            _s0 = float(_p9.get("stop") or 0)
            _t0 = float(_p9.get("tp1") or 0)
            if _sd0 not in ("LONG", "SHORT") \
                    or min(_e0, _s0, _t0) <= 0 or _e0 == _s0:
                continue
            _kw = (_p9["symbol"], _sd0)
            if _kw not in _EC_WATCH:
                _EC_WATCH[_kw] = {
                    "symbol": _p9["symbol"],
                    "base": _p9.get("base")
                    or _p9["symbol"].replace("USDT", ""),
                    "side": _sd0, "tier": _p9.get("tier"),
                    "score": float(_p9.get("score") or 0),
                    "appr": _p9.get("appr"), "entry": _e0,
                    "stop": _s0, "tp1": _t0,
                    "tp2": _p9.get("tp2"), "fired_at": _now,
                    "pulled": False}
        for _kw in list(_EC_WATCH):
            _w9 = _EC_WATCH[_kw]
            if _now - _w9["fired_at"] > EC_WATCH_H * 3600:
                _EC_WATCH.pop(_kw, None)
                continue
            try:
                _dfc = binance_client.get_klines(_w9["symbol"],
                                                 "1h", limit=60)
            except Exception:
                continue
            if _dfc is None or len(_dfc) < 25:
                continue
            _lng9 = _w9["side"] == "LONG"
            # judge on CLOSED candles only — the forming bar lies
            _cc = _dfc.iloc[:-1]
            if len(_cc) < 22:
                continue
            _lo9 = float(_cc["low"].iloc[-1])
            _hi9 = float(_cc["high"].iloc[-1])
            _cl9 = float(_cc["close"].iloc[-1])
            _op9 = float(_cc["open"].iloc[-1])
            _pv9 = float(_cc["close"].iloc[-2])
            if (_lng9 and _lo9 <= _w9["stop"]) or \
                    ((not _lng9) and _hi9 >= _w9["stop"]):
                _EC_WATCH.pop(_kw, None)   # stop taken pre-confirm
                continue
            # 💎📈 / 💎🔻 entry-zone follow-ups (user 2026-08-28:
            # "if the entry point is showing strength and going
            # 1-1.5% it should notify... if it falls below the
            # entry which makes my trade even better it should
            # notify"). One-shot each per fire, on live price.
            try:
                _lp9 = float(binance_client.get_ticker_price(
                    _w9["symbol"]) or 0)
            except Exception:
                _lp9 = 0.0
            if _lp9 > 0 and not _bstock_quiet(_w9["symbol"]):
                _mv9 = (_lp9 / float(_w9["entry"]) - 1) * 100 \
                    * (1 if _lng9 else -1)
                if _mv9 >= 1.2 and not _w9.get("ran_sent"):
                    _w9["ran_sent"] = True
                    # 📵 MUTE (user 2026-09-03, "mute 4"): commentary
                    # ladder, no action attached. Revert: _mute_run
                    # -> tg.send.
                    _mute_run = (lambda _m: (False, "muted"))
                    ok, _ = _mute_run(
                        f"💎📈 *RUNNING* — {_w9['base']} "
                        f"{_w9['side']} is +{_mv9:.1f}% past the "
                        f"buzz entry `{float(_w9['entry']):g}` — "
                        f"strength confirmed\n"
                        f"_the card is doing its job. SL "
                        f"`{float(_w9['stop']):g}` · TP1 "
                        f"`{float(_w9['tp1']):g}` still stand; "
                        f"chasing here adds {_mv9:.1f}% to the "
                        f"risk._")
                    n_alerts += 1 if ok else 0
                # 🔻 discount LADDER (user 2026-08-28 follow-up:
                # "discount can be even lower, 2 to 3%, or
                # re-entry") — one-shot per depth; a straight drop
                # fires only the deepest applicable tier.
                _dtiers = ((3.0, "dip3_sent", "DEEPEST DISCOUNT",
                            "⚠️ this deep sits near the plan stop "
                            "— if the stop level breaks, the setup "
                            "is DEAD, not cheap"),
                           (2.0, "dip2_sent", "DEEP DISCOUNT",
                            "a serious re-entry price IF the level "
                            "holds"),
                           (1.0, "dip_sent", "DISCOUNT",
                            "a better price IF it holds"))
                for _dt9, _df9, _lb9, _nt9 in _dtiers:
                    if _mv9 <= -_dt9 and not _w9.get(_df9):
                        for _dt8, _df8, _l8, _n8 in _dtiers:
                            if _dt8 <= _dt9:
                                _w9[_df8] = True
                        # 🔊 RESTORED (user 2026-09-04: "discount and
                        # deep discount should be a buzz... remove the
                        # running one") — the discount ladder is the
                        # one buzz class that improves entry price
                        # instead of chasing; RUNNING stays muted.
                        ok, _ = tg.send(
                            f"💎🔻 *{_lb9}* — {_w9['base']} "
                            f"{_w9['side']} now {abs(_mv9):.1f}% "
                            f"BELOW the buzz entry "
                            f"`{float(_w9['entry']):g}` (SL "
                            f"`{float(_w9['stop']):g}`)\n"
                            f"_{_nt9} — heads-up, not the green "
                            f"light: bare-dip entries measured 49% "
                            f"· −0.08R, the CONFIRMED re-entry "
                            f"67.8% · +0.03R. The 💎✅ buzz fires "
                            f"when the confirmation candle prints "
                            f"— that one is the get-in._")
                        n_alerts += 1 if ok else 0
                        break
            if (_lng9 and _lo9 <= _w9["entry"]) or \
                    ((not _lng9) and _hi9 >= _w9["entry"]):
                _w9["pulled"] = True
            if not _w9["pulled"]:
                continue
            _em9 = float(_cc["close"].ewm(span=20, adjust=False)
                         .mean().iloc[-1])
            try:
                _vm9 = float(_cc["volume"].rolling(20)
                             .mean().iloc[-1])
            except Exception:
                _vm9 = 0.0
            _vv9 = float(_cc["volume"].iloc[-1])
            _ok9 = (((_cl9 > _op9 and _cl9 > _pv9 and _cl9 > _em9)
                     if _lng9 else
                     (_cl9 < _op9 and _cl9 < _pv9 and _cl9 < _em9))
                    and _vm9 > 0 and _vv9 > 1.2 * _vm9)
            if not _ok9:
                continue
            _okp9 = (_w9["stop"] < _cl9 < _w9["tp1"]) if _lng9 \
                else (_w9["stop"] > _cl9 > _w9["tp1"])
            _EC_WATCH.pop(_kw, None)
            if not _okp9:
                continue                   # confirm landed off-plan
            # 🎯 conf on the confirmed entry too (user 2026-08-29:
            # "elite confirm entry should also hold the confidence
            # score on mobile buzz") — stamped on the buzz AND the
            # record/shadow so the band win-rates stay answerable.
            try:
                _cf0 = best_board.confidence(_w9["symbol"],
                                             _w9["side"])
            except Exception:
                _cf0 = None
            _sig9 = {"symbol": _w9["symbol"], "base": _w9["base"],
                     "side": _w9["side"], "tier": _w9.get("tier"),
                     "score": _w9.get("score"), "entry": _cl9,
                     "stop": _w9["stop"], "tp1": _w9["tp1"],
                     "tp2": _w9.get("tp2"), "conf": _cf0}
            store.record_signal("elite_confirm", _sig9)
            shadow_trader.open_from_signal("elite_confirm", _sig9,
                                           _cl9)
            _ECF_FIRES.append(dict(_sig9, fired_at=_now,
                                   burst=0.0))
            del _ECF_FIRES[:-20]
            # 2h clock (user 2026-08-23: confirmed entries break the
            # 6h silence too — "or it have reconfirm elite entry")
            if store.should_alert(
                    f"ecconf:{_w9['symbol']}:{_w9['side']}",
                    2 * 3600) and not _bstock_quiet(_w9["symbol"]):
                _ap0 = ("🚀 approved" if _w9.get("appr")
                        else "approval unknown"
                        if _w9.get("appr") is None else "unapproved")
                _t20 = (f" · TP2 `{float(_w9['tp2']):g}`"
                        if _w9.get("tp2") else "")
                _cf0s = (f" · 🎯 conf {_cf0}/100"
                         if _cf0 is not None else "")
                # ⚡ edge score on the confirmed re-entry too (user
                # 2026-08-31). Measured on the CONFIRM style, the
                # middle band is where the money is — 45 (+0.041 /
                # +0.171 both halves) and 65 (+0.006 / +0.074) are
                # green, while 25 and 85 are negative in BOTH halves.
                # Display only; the confirm stream stays ungated.
                try:
                    _eg0 = _conf_votes(_cc, _w9.get("side"))
                except Exception:
                    _eg0 = None
                if _eg0 is not None:
                    _etag0 = (" sweet spot" if _eg0 in (45, 65)
                              else " — thin edge" if _eg0 <= 25
                              else " hot — may be late")
                    _cf0s += f" · ⚡ edge {_eg0}/100{_etag0}"
                # 📵 MUTE (user 2026-09-03: "go with 1 mute elite
                # confirm now") — replaced by the 🦅 eagle as the
                # right-moment voice on elite cards (eagle validated
                # 63.5%/+0.221R vs confirm's live 42%/-19R over 174).
                # Records + desk tier keep accruing untouched.
                # Revert: _mute_ecf -> tg.send.
                _mute_ecf = (lambda _m: (False, "muted"))
                ok, _ = _mute_ecf(
                    f"💎✅ *ELITE CONFIRMED ENTRY* — {_w9['base']} "
                    f"{_w9['side']} (elite {_w9.get('tier')} "
                    f"{float(_w9.get('score') or 0):.0f} · {_ap0})"
                    f"{_cf0s}\n"
                    f"pulled back to the plan and CONFIRMED — the "
                    f"validated entry style (67.8% · +0.025R after "
                    f"fees, green both halves; live ledger decides)\n"
                    f"enter `{_cl9:g}` · SL `{_w9['stop']:g}` · "
                    f"TP1 `{_w9['tp1']:g}`{_t20}")
                n_alerts += 1 if ok else 0
    except Exception as _exc0:
        print("  elite-confirm error:", _exc0, flush=True)
    # 📵 BUZZ DIET (user 2026-08-29): 🌱 FRESH buzz OFF — deep
    # validation had already shown its 74% caption was window luck
    # (55.3%/−0.142R on 8 months). Board keeps it. Revert: uncomment.
    # _push(fresh_m, "fresh", _fmt_fresh, min_conf=0, tier="fresh")
    # 2026-08-15 user order: ✅🔥 TAKE NOW, 🚀 EARLY-LANE and ⚡ EARLY
    # MOVERS move to the ALWAYS list ("its green on decision desk
    # bro") — greens gates off.
    # 📵 BUZZ DIET (user 2026-08-29 "only the following"): ✅🔥 TAKE
    # NOW buzz OFF (reverses the 08-15 ALWAYS order on his own call).
    # Board + desk tier keep recording. Revert: uncomment.
    # _push(tn_rest, "takenow", _fmt_takenow, min_conf=0)
    # 📵 diet amendment (user same day: "dont remove... early lane
    # and early movers") — 🚀 EARLY-LANE (the 81.3% cell) + ⚡ EARLY
    # MOVERS restored to their pre-diet ALWAYS forms.
    _push([p for p in em_big if _in_zone(p)], "em", _fmt_prime,
          min_conf=0)
    _em_rest = [p for p in r.get("early_strong", [])
                if not p.get("early_lanes")]
    _push([p for p in _em_rest if _in_zone(p)], "emrest",
          _fmt_early_rest, min_conf=0)
    # 🌊 TREND RIDER buzz MUTED AGAIN same day (user 2026-08-06 after
    # the honest 25%-win framing: "not effective for me") — the 3-of-4
    # loser cadence doesn't fit how he trades, even net-positive.
    # Board + desk tier keep proving silently; re-enable by restoring
    # the _push below ONLY on his explicit word.
    # _push([p for p in r.get("trend", []) if _in_zone(p)], "trendr",
    #       _fmt_trend_rider, min_conf=0, tier="trend_rider")

    # 👑 ONE TRADE (user 2026-07-28): the concierge ritual, permanent —
    # every cycle look at EVERY lane's candidates together and buzz AT
    # MOST ONE: highest conf >= 70, in-zone, not extended (LA/LPT
    # anti-chase rule), R:R >= 1 at live price. Silent when blank by
    # explicit request ("its ok if its blank when there is no clear
    # point"). No desk-tier gate — the stream is self-gated and its own
    # desk tier below builds the honest forward record of the selector.
    _one = None
    try:
        _one = one_trade.pick((("💎 BEST", best), ("🚨 IGNITION", _ign),
                               ("🏆 APEX", apex),
                               ("🌟 EARLY ELITE", elite_early),
                               ("🌱 FRESH", fresh_m),
                               ("✅🔥 TAKE NOW", tn_hot),
                               ("🚀 EARLY-LANE", em_big)))
    except Exception as _one_exc:
        print("  one_trade error:", _one_exc, flush=True)
    if _one is not None:
        store.record_signal("one_trade", _one)
        # 2026-08-15 user order: 👑 ONE TRADE is losing on the desk —
        # buzz removed behind the greens gate. The selector keeps
        # recording so the record can still earn its voice back.
        _push([_one], "one", _fmt_one, min_conf=0,
              tier=None)  # 2026-09-05 user order: greens-gate
                          # exempt, same as apex/best

    # 🔮 KRONOS capture (user 2026-07-28, validated same day: agree
    # +0.259R vs veto -0.143R on our own entries, n=81). Forecast the
    # candidates the boards are showing, cache 2h, store for the app's
    # card strips + the 🎯 gate below. Fail-soft: no torch -> no rows.
    _kr_ok = False
    try:
        _kr_ok = kf.available()
    except Exception:
        _kr_ok = False
    if _kr_ok:
        _kr_new = 0
        _kr_seen: set = set()
        for _kp in (list(best) + list(_ign) + list(apex)
                    + list(elite_early) + list(fresh_m) + list(tn_hot)
                    + list(em_big) + list(_f30)):
            _ks = _kp.get("symbol")
            if not _ks or _ks in _kr_seen:
                continue
            _kr_seen.add(_ks)
            _hit = _KR_CACHE.get(_ks)
            if _hit and _now - _hit["t"] < KR_TTL:
                continue
            if _kr_new >= KR_MAX_PER_CYCLE:
                continue
            try:
                _kv = kf.forecast(_ks, "1h", horizon=24)
            except Exception as _kexc:
                print(f"  kronos {_ks}: {_kexc}", flush=True)
                continue
            _kr_new += 1
            if not _kv:
                continue
            _KR_CACHE[_ks] = {"t": _now, "s": _kv}
            store.record_signal("kronos", {
                "symbol": _ks, "base": _kp.get("base"),
                "side": {"UP": "LONG", "DOWN": "SHORT"}.get(
                    _kv["direction"], ""),
                "kr_dir": _kv["direction"],
                "kr_exp": _kv["exp_move_pct"],
                "kr_hi": _kv["path_high_pct"],
                "kr_lo": _kv["path_low_pct"]})

    def _kr_get(sym, side):
        _hit = _KR_CACHE.get(sym)
        return _hit["s"] if _hit and _now - _hit["t"] < KR_TTL else None

    # 🔄 KRONOS FLIP WATCH (user 2026-08-06: in KAITO against the
    # veto — "when it flips please notify me"): fresh read EVERY cycle
    # for watched symbols (bypasses the 2h TTL), buzz on any direction
    # change. First cycle after a restart only sets the baseline.
    _watch_syms = [s.strip().upper() for s in
                   str(getattr(config, "WORKER_FLIP_WATCH", "")
                       ).split(",") if s.strip()]
    if _kr_ok:
        for _fs in _watch_syms:
            try:
                _fv = kf.forecast(_fs, "1h", horizon=24)
            except Exception as _fexc:
                print(f"  flipwatch {_fs}: {_fexc}", flush=True)
                _fv = None
            if not _fv:
                continue
            _KR_CACHE[_fs] = {"t": _now, "s": _fv}
            _prev = _FLIP_PREV.get(_fs)
            _FLIP_PREV[_fs] = _fv["direction"]
            # flicker debounce (user 2026-08-07: "it gives UP and then
            # FLAT in 5-10 minutes — not what I want"): UP/DOWN flips
            # buzz only with |exp| >= 2% conviction; FLAT notices only
            # after a buzzed UP/DOWN (conviction-loss on something you
            # were actually told about).
            _newd = _fv["direction"]
            _buzzable = ((_newd in ("UP", "DOWN")
                          and abs(float(_fv["exp_move_pct"] or 0)) >= 2.0)
                         or (_newd == "FLAT"
                             and _FLIP_BUZZED.get(_fs) in ("UP", "DOWN")))
            # 🔇 flip-change buzzes MUTED 2026-08-10 (user: "skip the
            # updates from the 18 coins — only tell me the entry
            # points"). Reads keep refreshing (the sentry, demo smart
            # exit and 💯 gates all consume the cache); only the
            # 🎯🔥 WATCH ENTRY buzz speaks now. Re-enable by removing
            # the False guard below on his word — note this also
            # silences the 🔴 protection buzz (the KAITO service).
            if False and _prev and _prev != _newd and _buzzable:
                if store.should_alert(
                        f"krflip:{_fs}:{_fv['direction']}", 4 * 3600):
                    # action-oriented buzz (user 2026-08-07: "when to
                    # take the trade... as soon as the signal says").
                    # Flip-test data so far: UP-flips on crypto are the
                    # validated entry (~63%/+0.13R); DOWN-flips are
                    # exit/protection, NOT short entries (-0.27R).
                    # 2026-08-07 30-coin/1161-flip verdict: flips as
                    # ENTRIES measured negative (UP-flips -0.05R) —
                    # wording is heads-up/protection, never auto-entry.
                    _fd = _fv["direction"]
                    _act = ("🟢 read turned UP — *heads-up, not an "
                            "auto-entry* (flip entries measured "
                            "~flat; strongest when a 💯/🥇 fire "
                            "agrees)" if _fd == "UP"
                            else "🔴 read turned DOWN — *protect the "
                                 "position / no fresh longs* (fresh "
                                 "shorts NOT validated)"
                            if _fd == "DOWN"
                            else "⚪ conviction gone — stand aside")
                    _lvl = ""
                    try:
                        _dk = binance_client.get_klines(_fs, "1h",
                                                        limit=30)
                        _hk = _dk["high"].astype(float).to_numpy()
                        _lk = _dk["low"].astype(float).to_numpy()
                        _ck = _dk["close"].astype(float).to_numpy()
                        _trk = [max(_hk[i] - _lk[i],
                                    abs(_hk[i] - _ck[i - 1]),
                                    abs(_lk[i] - _ck[i - 1]))
                                for i in range(len(_ck) - 14,
                                               len(_ck))]
                        _a14 = sum(_trk) / len(_trk)
                        _px = float(_ck[-1])
                        if _fd == "UP":
                            # target tier scales with momentum (user
                            # 2026-08-07: "1R 2R or 3R based on the
                            # momentum") — kronos |exp| is the gauge.
                            # 1R bank is the validated base; runners
                            # are guidance, unvalidated.
                            _ex = abs(float(_fv["exp_move_pct"] or 0))
                            _rr = 3.0 if _ex >= 5 else \
                                2.0 if _ex >= 3 else 1.0
                            _rk = _px + _rr * 1.5 * _a14
                            _run = ("" if _rr == 1.0 else
                                    f" · runner `{_rk:g}` ({_rr:g}R — "
                                    f"momentum-scaled)")
                            _lvl = (f"\nentry `{_px:g}` · SL "
                                    f"`{_px - 1.5 * _a14:g}` · TP1 "
                                    f"`{_px + 1.5 * _a14:g}` (bank "
                                    f"{'100%' if _rr == 1.0 else 'half'}"
                                    f" at 1R){_run}")
                    except Exception:
                        pass
                    # 📵 MUTE (user 2026-09-03, "mute 3"): the kronos
                    # family bleeds live (KR-APPROVED -17R); a flip is
                    # information, not an entry. Records unchanged.
                    # Revert: _mute_krf -> tg.send.
                    _mute_krf = (lambda _m: (False, "muted"))
                    ok, _ = _mute_krf(
                        f"🔄 *KRONOS FLIP* — "
                        f"{_fs.replace('USDT', '')} read changed "
                        f"{_prev} → *{_fd}* "
                        f"({_fv['exp_move_pct']:+.1f}% · path "
                        f"{_fv['path_low_pct']:+.1f}%.."
                        f"{_fv['path_high_pct']:+.1f}%)\n"
                        f"{_act}{_lvl}")
                    n_alerts += 1 if ok else 0
                    if ok:
                        _FLIP_BUZZED[_fs] = _newd

    # 🎯 WATCHLIST SENTRY (user 2026-08-07: "I need to know EXACTLY
    # when to take the trade... best entry point... 24/7 readings") —
    # the VALIDATED entry stack (score + pullback/confirmation timing,
    # the machinery under the 73-88% cells) runs on every flagged coin
    # every cycle. Buzzes on escalation to TAKE_NOW — the measured
    # entry moment — with the full plan; GET_READY sends one heads-up.
    # Kronos is color. Flip-entries were killed by the 30-coin verdict
    # (-0.05R); THIS is the honest "enter now" signal.
    _sentry_fires: list = []
    for _ss in _watch_syms:
        try:
            _d1s = binance_client.get_klines(_ss, "1h", limit=400)
            _d4s = binance_client.get_klines(_ss, "4h", limit=200)
            if _d1s is None or len(_d1s) < 60:
                continue
            _rs = es.score_from_data(_ss, _d1s, df_4h=_d4s,
                                     oi_hist=None, pct_24h=0.0,
                                     skip_deriv=True)
            _sd_s = _rs.get("side")
            _sc_s = float(_rs.get("score") or 0)
            if _sd_s not in ("LONG", "SHORT") or _sc_s < 60:
                _SENTRY_PREV[_ss] = "NONE"
                continue
            _cls = _d1s["close"].astype(float).tolist()
            _his = _d1s["high"].astype(float).tolist()
            _los = _d1s["low"].astype(float).tolist()
            _epx = float(_cls[-1])
            _trs = [max(_his[i] - _los[i],
                        abs(_his[i] - _cls[i - 1]),
                        abs(_los[i] - _cls[i - 1]))
                    for i in range(len(_cls) - 14, len(_cls))]
            _a14 = sum(_trs) / len(_trs)
            if _a14 <= 0:
                continue
            if _sd_s == "LONG":
                _stp = min(_los[-10:]) - 0.25 * _a14
                if not (0 < _epx - _stp <= 4 * _a14):
                    _stp = _epx - 1.5 * _a14
                _t1s = _epx + (_epx - _stp)
                _t2s = _epx + 2 * (_epx - _stp)
            else:
                _stp = max(_his[-10:]) + 0.25 * _a14
                if not (0 < _stp - _epx <= 4 * _a14):
                    _stp = _epx + 1.5 * _a14
                _t1s = _epx - (_stp - _epx)
                _t2s = _epx - 2 * (_stp - _epx)
            _et = entry_timing.entry_signal(_ss, _sd_s, _epx,
                                            stop=_stp, df=_d1s)
            _st_s = _et.get("status")
            _prev_s = _SENTRY_PREV.get(_ss)
            _SENTRY_PREV[_ss] = _st_s
            _kv_s = _kr_get(_ss, _sd_s) if _kr_ok else None
            _krl = (f"🔮 {_kv_s.get('direction')} "
                    f"{float(_kv_s.get('exp_move_pct') or 0):+.1f}%/24h"
                    if _kv_s else "🔮 no fresh read")
            _b_s = _ss.replace("USDT", "")
            # 🧪 desk proof (user 2026-08-11: "I want that on the
            # decision desk to be tested as well") — every sentry
            # ENTRY becomes a shadow trade so the 18-coin watch builds
            # its own honest live record, 7-day hold on the desk.
            if _st_s == "TAKE_NOW" and _prev_s != "TAKE_NOW":
                _sig_s = {"symbol": _ss, "base": _b_s, "side": _sd_s,
                          "tier": _rs.get("tier") or "SENTRY",
                          "score": _sc_s, "entry": _epx,
                          "stop": _stp, "tp1": _t1s, "tp2": _t2s,
                          "hot": bool(_et.get("hot"))}
                store.record_signal("sentry", _sig_s)
                _sentry_fires.append(_sig_s)
            if (_st_s == "TAKE_NOW" and _prev_s != "TAKE_NOW"
                    and store.should_alert(
                        f"sentry:{_ss}:{_sd_s}:tn", 4 * 3600)):
                _hot_s = " · ⚡HOT" if _et.get("hot") else ""
                # 📇 coin grade (user 2026-08-15: the deep-dive table
                # travels with every alert) — this exact signal's
                # measured 4-month record ON THIS COIN.
                _gr = getattr(config, "SENTRY_GRADES", {}).get(_ss)
                _grl = ""
                if _gr:
                    _hint = (" — history says SIZE DOWN or skip"
                             if _gr[0] == "🔴"
                             else " — unmeasured, treat as new"
                             if _gr[0] == "⚪" else "")
                    _grl = (f"\n{_gr[0]} this coin's record on this "
                            f"signal: {_gr[1]}{_hint}")
                ok, _ = tg.send(
                    f"🎯🔥 *ENTRY — {_b_s} {_sd_s}* · confidence "
                    f"{_sc_s:.0f}/100{_hot_s}\n"
                    f"entry `{_epx:g}` · SL `{_stp:g}` · TP1 "
                    f"`{_t1s:g}` (bank) · TP2 `{_t2s:g}`\n{_krl}"
                    f"{_grl}\n"
                    f"_pullback + confirmation candle just completed "
                    f"— the validated entry moment on your coin. Bank "
                    f"at TP1; runner to TP2 only if ⚡HOT._")
                n_alerts += 1 if ok else 0
            # 🔇 GET_READY pre-alerts MUTED 2026-08-10 (user: entry
            # points ONLY). State machine keeps tracking so the
            # 🎯🔥 escalation still fires at the right moment.
        except Exception as _sn_exc:
            print(f"  sentry {_ss}: {_sn_exc}", flush=True)

    # 🚀 MOONSHOT DESK (user 2026-08-09 "bestest build") — the
    # SEPARATE big-move desk: 🔥 social heat (LunarCrush, one call
    # covers the universe) + ⛽ positioning fuel (Coinalyze, 12-coin
    # rotation ≈ full universe every 25 min) + 🏗 base + ⏱ confirmed
    # break, fused per coin over the top-60. UNPROVEN: its own desk
    # tier proves forward; the live executor NEVER reads it. Watch
    # snapshots are stored so every future BMT-class runner becomes
    # measurable precursor data.
    _moon_fires, _moon_watch = [], []
    try:
        _mu = binance_client.get_top_symbols(
            moonshot_desk.UNIVERSE_N)["symbol"].tolist()
        _now_m = time.time()
        _soc = moonshot_desk.map_social(lunarcrush.coin_list())
        for _ms in _mu:
            _sv = _soc.get(_ms)
            if _sv:
                _MOON_SOC.setdefault(_ms, []).append(
                    (_now_m, _sv.get("alt_rank"), _sv.get("inter")))
                if len(_MOON_SOC[_ms]) > 320:
                    _MOON_SOC[_ms] = _MOON_SOC[_ms][-320:]
        _rot0 = _MOON_ROT[0] % max(1, len(_mu))
        _MOON_ROT[0] = (_rot0 + 12) % max(1, len(_mu))
        for _ms in _mu[_rot0:_rot0 + 12]:
            try:
                _mkt = cz.resolve_perp(_ms)
                if not _mkt:
                    continue
                _oi = cz.oi_history(_mkt, "1hour", days=2)
                _lsr = cz.long_short_history(_mkt, "1hour", days=2)
                _fu = (cz.current_funding([_mkt]) or {}).get(_mkt)
                _d_oi = _d_ls = None
                if _oi is not None and len(_oi) >= 25 and \
                        len(_oi.columns):
                    _c0 = _oi.columns[0]
                    if float(_oi[_c0].iloc[-25]) > 0:
                        _d_oi = (float(_oi[_c0].iloc[-1])
                                 / float(_oi[_c0].iloc[-25]) - 1) * 100
                if _lsr is not None and len(_lsr) >= 25 and \
                        len(_lsr.columns):
                    _c1 = _lsr.columns[0]
                    _d_ls = float(_lsr[_c1].iloc[-1]) - \
                        float(_lsr[_c1].iloc[-25])
                _MOON_POS[_ms] = {"d_oi": _d_oi, "d_ls": _d_ls,
                                  "fund": _fu, "t": _now_m}
            except Exception:
                continue
        _moon_fires, _moon_watch = moonshot_desk.scan(
            _mu, _MOON_SOC, _MOON_POS, binance_client.get_klines,
            _kr_get if _kr_ok else None)
    except Exception as _mn_exc:
        print("  moonshot error:", _mn_exc, flush=True)
    for p in _moon_fires:
        store.record_signal("moonshot", p)
    for p in _moon_watch:
        store.record_signal("moon_watch", p)
    # 2026-08-15 user order 7: MOONSHOT buzz muted until GREEN.
    _push(list(_moon_fires), "moon", _fmt_moonshot, min_conf=0,
          tier="moonshot")

    # 🔮 KRONOS APPROVED desk tier (user 2026-08-03: "can the 86% be
    # treated separately?") — every elite-stream signal where Kronos
    # agrees, REGARDLESS of the other 🎯 gates. The live forward
    # record of the backtest's agree bucket (86%/+0.34R, n=36) at its
    # natural breadth. Desk-only: no buzz, no votes.
    _kr_appr = []
    _kr_strong = []      # ⚡🔮 silent proving tier (fills under _kr_ok)
    if _kr_ok:
        _ka_seen: set = set()
        _ka_extra = [0]          # on-demand forecast budget this cycle
        # ⚡ EARLY MOVERS + 🚀 EARLY-LANE added 2026-08-11 (user:
        # "fresh movers, take now, apex, early movers with kronos
        # agreement should land on telegram immediately").
        for _ka_src, _ka_pool in (("🏆 APEX", apex),
                                  ("🌟 EARLY ELITE", elite_early),
                                  ("🌱 FRESH", fresh_m),
                                  ("✅🔥 TAKE NOW", tn_hot),
                                  ("🚀 EARLY-LANE", em_big),
                                  ("⚡ EARLY MOVERS", _em_rest)):
            for _kp in _ka_pool:
                _kk = (_kp.get("symbol"), _kp.get("side"))
                if _kk in _ka_seen or not _kk[0]:
                    continue
                _ka_seen.add(_kk)
                _kv2 = _kr_get(_kk[0], _kk[1])
                if not _kv2:
                    # 2026-08-11: don't silently skip a candidate just
                    # because the budgeted capture loop hadn't reached
                    # it — fetch a read on demand (in-zone candidates
                    # only, small extra budget) so an agreeing setup
                    # actually reaches Telegram instead of being lost
                    # to cache timing. ~2.3s each; capped per cycle.
                    if _ka_extra[0] >= KR_APPROVE_EXTRA or \
                            not _in_zone(_kp):
                        continue
                    _ka_extra[0] += 1
                    try:
                        _kv2 = kf.forecast(_kk[0], "1h", horizon=24)
                    except Exception:
                        _kv2 = None
                    if _kv2:
                        _KR_CACHE[_kk[0]] = {"t": time.time(),
                                             "s": _kv2}
                if not _kv2:
                    continue
                if ((_kv2.get("direction") == "UP"
                     and _kk[1] == "LONG")
                        or (_kv2.get("direction") == "DOWN"
                            and _kk[1] == "SHORT")):
                    _kp2 = dict(_kp)
                    _kp2["kr_dir"] = _kv2.get("direction")
                    _kp2["kr_exp"] = _kv2.get("exp_move_pct")
                    _kp2["kr_src"] = _ka_src
                    _kr_appr.append(_kp2)
        for p in _kr_appr:
            store.record_signal("kr_approved", p)
        # 💎 ELITE CONVICTION buzz rule (user 2026-08-15 refinement,
        # the PORTAL lesson): approved MAX/HIGH → always buzz;
        # UNAPPROVED MAX/HIGH → buzz ONLY when 🔮 kronos agrees (the
        # rescue — "unapproved skippable, but kronos agrees on high
        # and max should be notified"); unapproved with no agreement
        # stays SILENT (the 48.5% coin-flip junk). On-demand reads
        # capped at 2/cycle for the unapproved candidates.
        _ec_buzz = []
        _ec_extra = [0]
        for _pe in _ec_mh:
            if _pe.get("appr"):
                _ec_buzz.append(_pe)
                continue
            # 💎🔄 RE-QUALIFIED (user 2026-08-19): a coin that already
            # ran, went quiet, and now qualifies MAX/HIGH again is a
            # NEW setup — it buzzes approved OR unapproved so he knows
            # when to get back in. The message says which it is.
            if _pe.get("requal"):
                _ec_buzz.append(_pe)
                continue
            _kv3 = _kr_get(_pe["symbol"], _pe["side"])
            if not _kv3 and _ec_extra[0] < 2:
                _ec_extra[0] += 1
                try:
                    _kv3 = kf.forecast(_pe["symbol"], "1h",
                                       horizon=24)
                    if _kv3:
                        _KR_CACHE[_pe["symbol"]] = {
                            "t": time.time(), "s": _kv3}
                except Exception:
                    _kv3 = None
            if _kv3 and ((_kv3.get("direction") == "UP"
                          and _pe["side"] == "LONG")
                         or (_kv3.get("direction") == "DOWN"
                             and _pe["side"] == "SHORT")):
                _ec_buzz.append(dict(_pe, kr_rescue=True))
        for _pe in _ec_buzz:
            try:
                _pe["conf"] = best_board.confidence(
                    _pe.get("symbol"), _pe.get("side"))
            except Exception:
                pass
            store.record_signal("elite_conv", _pe)
        _push_elite(list(_ec_buzz))
        # ⚡🔮 KR-STRONG proving tier (user 2026-08-15: "testing
        # strong elite convictions with kronos") — SILENT: no buzz,
        # no board card yet. Cache-only reads, zero extra forecast
        # budget. The shadow desk tier builds the live record in
        # parallel with the backtest_krstrong verdict; a board and
        # telegram voice ship ONLY if both come back green, as a
        # SEPARATE stream. Nothing existing is touched.
        for _sp in (r.get("strong") or []):
            _sv = _kr_get(_sp.get("symbol"), _sp.get("side"))
            if not _sv:
                continue
            if ((_sv.get("direction") == "UP"
                 and _sp.get("side") == "LONG")
                    or (_sv.get("direction") == "DOWN"
                        and _sp.get("side") == "SHORT")):
                _sp2 = dict(_sp)
                _sp2["kr_dir"] = _sv.get("direction")
                _sp2["kr_exp"] = _sv.get("exp_move_pct")
                _kr_strong.append(_sp2)
        for _sp2 in _kr_strong:
            store.record_signal("kr_strong", _sp2)
        # 🔮✅ buzz (user 2026-08-05: "kronos with apex / take now /
        # fresh mover / early elite approved should be on telegram") —
        # the live face of the validated agree bucket (86%/+0.34R,
        # n=138 backtest; desk tier kr_approved is the binding jury).
        # 📵 BUZZ DIET (user 2026-08-29): 🔮✅ KR-APPROVED buzz off
        # the roster. Desk tier kr_approved keeps judging silently.
        # Revert: uncomment.
        # _push([p for p in _kr_appr if _in_zone(p)], "krapp",
        #       _fmt_kr_approved, min_conf=0)

    if not _kr_ok:
        # kronos down → the rescue can't be judged; buzz the approved
        # elite conviction fires so the stream never goes fully dark.
        _ec_buzz = [p for p in _ec_mh if p.get("appr")]
        for _pe in _ec_buzz:
            try:
                _pe["conf"] = best_board.confidence(
                    _pe.get("symbol"), _pe.get("side"))
            except Exception:
                pass
            store.record_signal("elite_conv", _pe)
        _push_elite(list(_ec_buzz))

    # 💯 CONVICTION v2 (user 2026-08-23: "remove kronos its not even
    # proven effective anyway... make it better somehow"). Kronos is
    # OUT — the old 88.6% backtest cell collapsed to 39% live, and
    # standalone Kronos measured -26R. The v2 gate keeps ONLY
    # discriminators that measured green in BOTH history halves on
    # the 387-fire entry study (.conv_gate_pick, n=147): CONFIRMED
    # entry (fast30 pullback+confirm) + score>=82 (user's floor) +
    # 🚀 approved + burst<85 at the card (the anti-chase law: a
    # maxed thrust AT the signal measured -0.218R). Measured cell:
    # 70.7% win · +0.130R after fees (+0.076R older / +0.187R
    # recent). Bonus: no Kronos = the stream no longer goes dark
    # when the model is down. The live desk ledger outranks this
    # backtest too — 39% taught us that.
    _conv = []
    for _cp in _f30:
        if float(_cp.get("score") or 0) < 82:
            continue
        try:
            # construct fidelity: the cell banks TP1 at ~1:1 — a
            # plan whose TP1 pays < ~1R isn't the measured trade.
            _rk = abs(float(_cp["entry"]) - float(_cp["stop"]))
            _rw = abs(float(_cp["tp1"]) - float(_cp["entry"]))
            if _rk <= 0 or _rw / _rk < 0.95:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        try:
            _cd9 = binance_client.get_klines(_cp["symbol"], "1h",
                                             limit=120)
            if not _vb_w.lane_approved(_cd9, _cp.get("side")):
                continue
            _cb9, _cbd9, _ = _vb_w.lane_velocity_burst(_cd9)
            _cb9 = (float(_cb9)
                    if (_cbd9 or "").upper()
                    == (_cp.get("side") or "").upper() else 0.0)
            if _cb9 >= 85:
                continue      # thrust already spent — not the cell
        except Exception:
            continue
        _conv.append(dict(_cp, burst=_cb9))
    for p in _conv:
        store.record_signal("conviction_v2", p)
    # 📵 BUZZ DIET (user 2026-08-29): 💯 v2 buzz off the roster (his
    # earlier read: "100 conviction is not worthy at all with win
    # rates") — the fresh conviction_v2 ledger keeps recording
    # silently and can earn the buzz back. Revert: uncomment.
    # _push([p for p in _conv if _in_zone(p)], "conv",
    #       _fmt_conviction, min_conf=0)

    # 🎯 TRUE SIGNAL (user 2026-07-28: "one solid system, no fuzz") —
    # five gates, Kronos on top with the last word. Desk tier proves it
    # forward from day one; NO Telegram until it earns it (~20 closed
    # positive). Kronos offline -> zero cards, and the app says so.
    _ts_rows = []
    try:
        if _kr_ok:
            _ts_form = {}
            for _tf_t in ("elite_early", "ignition", "fast30"):
                try:
                    _ts_form[_tf_t] = store.shadow_recent_net(
                        _tf_t)["net_r"]
                except Exception:
                    _ts_form[_tf_t] = 0.0
            _ts_rows = true_signal.compose(
                {"elite_early": elite_early, "ignition": _ign,
                 "fast30": _f30},
                _ts_form, (r.get("regime") or {}).get("regime"),
                binance_client.get_ticker_price,
                one_trade._extension, _kr_get)
    except Exception as _ts_exc:
        _ts_rows = []
        print("  true_signal error:", _ts_exc, flush=True)
    for p in _ts_rows:
        store.record_signal("true_signal", p)
    # 🎯 straight to Telegram (user 2026-07-28: "predictions early so I
    # can bang on the trade") — always-buzz, no desk gate: the stream
    # is already the strictest construct in the system (5 gates + 🔮),
    # fires rarely, and every message carries the honest odds. The desk
    # tier keeps scoring it in parallel.
    # 2026-08-15 user order 7: TRUE SIGNAL buzz muted until GREEN
    # (reverses the always-buzz note above — the losing record loses
    # its voice; the tier= gate restores it the day it earns green).
    _push(_ts_rows, "ts", _fmt_ts, min_conf=0, tier="true_signal")
    # 🔬 funnel audit rows — feed the page's living board (every
    # candidate + which gate it died at), even when no card qualifies.
    try:
        for _au in true_signal.LAST_AUDIT:
            store.record_signal("ts_audit", _au)
    except Exception:
        pass

    # 🌋 PRE-BURST radar (user 2026-08-03, PORTAL case: "predict before
    # they burst — do whatever it takes"): quiet coils where Kronos
    # forecasts a big move. Deployed unproven by explicit user call
    # (IGNITION precedent) — honest label in every buzz, desk tier
    # proving, backtest_coil_kronos.py recalibrating in parallel.
    _pb = []
    if _kr_ok:
        _pb_budget = [5]      # fresh coil forecasts per cycle

        def _kr_pb(sym):
            _hit = _KR_CACHE.get(sym)
            if _hit and _now - _hit["t"] < KR_TTL:
                return _hit["s"]
            if _pb_budget[0] <= 0:
                return None
            _pb_budget[0] -= 1
            _kv = kf.forecast(sym, "1h", horizon=24)
            if _kv:
                _KR_CACHE[sym] = {"t": _now, "s": _kv}
            return _kv

        try:
            import preburst as _pb_mod
            # top-100 universe (user 2026-08-03: "make it 100 with max
            # efficiency") — rotating halves: 50 coins per 5-min cycle,
            # full 100 covered every 10 min. Coils live for hours, so
            # nothing is lost; API load stays flat and the Kronos
            # budget (5 fresh/cycle) is unchanged.
            _PB_ROT[0] += 1
            _pb_syms = binance_client.get_top_symbols(
                100)["symbol"].tolist()
            _pb_half = (_pb_syms[:50] if _PB_ROT[0] % 2 == 0
                        else _pb_syms[50:])
            _pb_found = _pb_mod.scan(_pb_half, _kr_pb, max_checks=50)
        except Exception as _pb_exc:
            _pb_found = []
            print("  preburst error:", _pb_exc, flush=True)

        # 🌋 THE BREAK GATE (2026-08-11 — the fix that explains the
        # tier's -11.4R). preburst.py emits a STOP-ENTRY plan: entry
        # is the coil EDGE, price is still inside the range. But the
        # desk opens every signal AT LIVE PRICE, so recording at coil
        # time made the desk take the COIL-CLOSE entry — the construct
        # measured at -0.21R — while the module's own comment says
        # "enter ON BREAK only" (+0.122R/61%, n=59). The board said
        # one thing, the record measured another.
        # Now: a fresh coil is ARMED (stream pb_armed, board-only, no
        # trade). Only when price actually crosses the trigger in
        # Kronos's direction do we record "preburst" — so the desk
        # opens at ~the trigger and finally measures the construct we
        # validated. Unbroken coils expire after PB_ARM_H hours.
        _pb = []
        for _p in _pb_found:
            _k = _p["symbol"]
            if _k not in _PB_ARMED:
                _PB_ARMED[_k] = {"p": _p, "t": _now}
                store.record_signal("pb_armed", _p)
        for _k in list(_PB_ARMED):
            _a = _PB_ARMED[_k]
            if _now - _a["t"] > PB_ARM_H * 3600:
                del _PB_ARMED[_k]
                continue
            _ap = _a["p"]
            try:
                _apx = float(binance_client.get_ticker_price(_k) or 0)
            except Exception:
                continue
            if _apx <= 0:
                continue
            _trg = float(_ap["trigger"])
            _broke = (_apx >= _trg if _ap["side"] == "LONG"
                      else _apx <= _trg)
            if _broke:
                del _PB_ARMED[_k]
                _pb.append(_ap)
        for p in _pb:
            store.record_signal("preburst", p)
        # 🌋 buzzes SILENCED (user 2026-08-05: "useless and losing
        # money") — the SURGE precedent: desk tier keeps proving
        # silently, boards stay visible, no Telegram. Re-enable by
        # restoring the _push line ONLY if the desk record earns it.
        # _push(list(_pb), "preburst", _fmt_preburst, min_conf=0)

    # 🟢 GREEN LIGHT announcements stay (desk reports, rare + informative)
    try:
        _green = {rec["tier"] for rec in shadow_trader.tier_records()
                  if rec.get("green")}
    except Exception:
        _green = set()
    for _gt in _green:
        if store.should_alert(f"green:{_gt}", 30 * 24 * 3600):
            ok, _ = tg.send(f"🟢 *GREEN LIGHT* — `{_gt}` is now PROVEN "
                            f"profitable after fees in its live forward "
                            f"record on the Decision Desk.")
            n_alerts += 1 if ok else 0

    # ✳️ DECISION DESK — the brain TAKES every tier's signal itself as a
    # forward shadow trade (live entry price, real fees, ladder + 48h
    # time-stop) and manages open ones each cycle. This builds the per-tier
    # LIVE track record; a tier earns 🟢 GREEN LIGHT only when its own
    # record is profitable after fees. (User 2026-07-08: forward proof.)
    n_shadow_open = n_shadow_closed = 0
    try:
        # user 2026-07-08: SST1 tier cut from the desk — purge any rows the
        # brief earlier deploy created (idempotent, cheap).
        store.shadow_purge_tier("sst1")
    except Exception:
        pass
    try:
        def _live(sym):
            try:
                return binance_client.get_ticker_price(sym)
            except Exception:
                return None
        # 🩸 LIQ FLUSH (2026-07-17): long-liquidation snapback — validated
        # provisionally on 60d of 1h data (57.4% / +0.084R vs -0.087R
        # baseline, both halves positive). SILENT proving tier: desk
        # shadow record only — no alerts, no 💎 votes, no live trading
        # until it earns its own 🟢 GREEN LIGHT.
        try:
            _lf = liq_flush.scan(
                binance_client.get_top_symbols(40)["symbol"].tolist())
        except Exception as _lf_exc:
            _lf = []
            print("  liq_flush error:", _lf_exc, flush=True)
        for p in _lf:
            store.record_signal("liq_flush", p)
        # 🏆 TOP CONVICTION desk tier (user 2026-07-28: "I clearly can't
        # see it on the desk") — worker-side mirror of the app's
        # size-up board: confirmed TAKE_NOW + HOT picks ranked by
        # score, top 8. (The app board adds page-side injections the
        # worker can't see; this tracks the core construct honestly.)
        _topc = sorted(tn_hot,
                       key=lambda p: -float(p.get("score") or 0))[:8]
        for p in _topc:
            store.record_signal("top_conviction", p)
        # 💎🏆 ELITE × TOP CONVICTION AGREE (user 2026-08-23,
        # screenshot order — the GALA case): an elite conviction card
        # that ALSO earns a seat on the confirmed size-up board is the
        # double stamp — buzz it with the full confirmed plan and
        # every chip. Notification only; both boards unchanged.
        _ec_by_key = {(p.get("symbol"), (p.get("side") or "").upper()):
                      p for p in _ec_mh}
        for _tc in _topc:
            _ep9 = _ec_by_key.get(
                (_tc.get("symbol"), (_tc.get("side") or "").upper()))
            if not _ep9 or _bstock_quiet(_tc["symbol"]):
                continue
            try:
                if not store.should_alert(
                        f"elitetop:{_tc['symbol']}:{_tc['side']}",
                        6 * 3600):
                    continue
                _ap9 = ("🚀 approved" if _ep9.get("appr")
                        else "approval unknown"
                        if _ep9.get("appr") is None
                        else "unapproved — size accordingly")
                _t29 = (f" · TP2 `{float(_tc['tp2']):g}`"
                        if _tc.get("tp2") else "")
                # 📵 MUTE (user 2026-09-03, "mute 6" — the GREEN
                # LIGHT half of #6 STAYS live per the same message).
                # Revert: _mute_etc -> tg.send.
                _mute_etc = (lambda _m: (False, "muted"))
                ok, _ = _mute_etc(
                    f"💎🏆 *ELITE × TOP CONVICTION AGREE* — "
                    f"{_tc['base']} {_tc['side']}\n"
                    f"💎 elite {_ep9.get('tier')} "
                    f"{float(_ep9.get('score') or 0):.0f} ({_ap9}) · "
                    f"🏆 top conviction "
                    f"{float(_tc.get('score') or 0):.0f} · "
                    f"{int(_tc.get('lanes') or 0)} lanes · "
                    f"confirmed entry\n"
                    f"entry `{float(_tc['entry']):g}` · SL "
                    f"`{float(_tc['stop']):g}` · TP1 "
                    f"`{float(_tc['tp1']):g}`{_t29}\n"
                    f"_the double stamp — the elite board fired it "
                    f"AND the confirmed size-up board seated it_")
                n_alerts += 1 if ok else 0
            except Exception as _exc9:
                print("  elitetop buzz error:", _exc9, flush=True)
        # 🩸 LIQ FLUSH RETIRED (2026-07-28, its own pre-registered rule:
        # still negative past ~50 closed — final record -22.6R/110).
        # Signals stay recorded above for the archive; the desk stops
        # taking them. Re-add here only if a NEW validation earns it.
        _tiers = (("top_conviction", _topc),
                  # 💎 ELITE CONVICTION desk tier (user 2026-08-31:
                  # "confidence score should be recorded for elite
                  # conviction"). It was the ONE requested stream with
                  # no desk tier at all — recorded as a signal but
                  # never shadow-taken, so it could never appear on
                  # the desk or in the conf panel. RECORDS ONLY: the
                  # elite board, scoring, approval and buzz are
                  # untouched (standing rule). open_from_signal
                  # dedupes one open per (tier, symbol), so a card
                  # persisting across cycles is taken once.
                  ("elite_conv", _ec_mh),
                  ("best_board", best),
                  ("apex", apex), ("takenow_hot", tn_hot),
                  ("elite_early", elite_early),
                  ("fresh", fresh_m), ("early_movers",
                                       r.get("early_strong", [])),
                  ("early_lane", em_big),
                  ("ignition", _ign),
                  ("ignition_strong", _igs),
                  ("fast30", _f30),
                  ("surge", _srg),
                  ("one_trade", [_one] if _one else []),
                  ("true_signal", _ts_rows),
                  ("preburst", _pb),
                  ("kr_approved", _kr_appr),
                  ("kr_strong", _kr_strong),
                  ("prime", _prime),
                  # 💯 v2 gets a FRESH ledger (user 2026-08-23:
                  # "restart conviction v2 from new entries now,
                  # leave the trades taken before") — the kronos-era
                  # record stays archived under `conviction`.
                  ("conviction_v2", _conv),
                  ("moonshot", _moon_fires),
                  ("sentry", _sentry_fires),
                  ("trend_rider", r.get("trend", [])))
        for _tname, _sigs in _tiers:
            for p in _sigs:
                # 🎯 conf on EVERY desk trade (user 2026-08-28: "the
                # confidence on telegram... I want to know their win
                # rates") — stamped at open, stored in the trade row,
                # so the desk answers win-rate-by-band directly.
                if p.get("conf") is None:
                    try:
                        p["conf"] = best_board.confidence(
                            p.get("symbol"), p.get("side"))
                    except Exception:
                        pass
                # 🌡 heat stamp on EVERY desk trade (user 2026-09-05:
                # "have the confidence score on them because in this
                # way we can measure") — klines are cycle-cached, so
                # this is mostly a cache hit. Fail-soft.
                if p.get("heat") is None:
                    try:
                        p["heat"] = _atr_heat(binance_client.get_klines(
                            p.get("symbol"), "1h", limit=120))
                    except Exception:
                        pass
                if shadow_trader.open_from_signal(_tname, p,
                                                  _live(p.get("symbol"))):
                    n_shadow_open += 1
        _open_syms = {t["symbol"] for t in store.shadow_open_trades()}
        _pxs = {s: _live(s) for s in _open_syms}
        _sh_closed = shadow_trader.manage(
            {k: v for k, v in _pxs.items() if v})
        n_shadow_closed = len(_sh_closed)
    except Exception as exc:
        _sh_closed = []
        _pxs = {}
        print("  shadow error:", exc, flush=True)

    # 🤝 DUO 85+ (user 2026-09-03: "when 2 streams fire with conf 85+
    # buzz me that one") — the measured winner cell from the live
    # confluence panel: EXACTLY 2 elite-family streams on the same
    # coin+side within 30 min at conf 85+ ran 50% / +0.218R, while the
    # 3+ swarm ran 31% / -0.167R. Exactly-two is the construct — if a
    # third stream joins, the cluster leaves this cell and no buzz
    # fires. Own desk tier `duo85` proves it forward from day one.
    try:
        for _du in store.fresh_duo_clusters(1800.0):
            if _bstock_quiet(_du["symbol"]):
                continue
            # NAMED PAIRS — buzz at ANY conf, each on its own desk
            # tier so its record is judged separately:
            #   💎👑 kingpair (user 2026-09-03): BEST + ONE TRADE —
            #   the measured best pair, 51% / +0.540R over 86 closed.
            #   🔥💎 tnelite (user 2026-09-04: "take hot and elite
            #   conviction both agree... their win rate is high") —
            #   HONEST NOTE: this pair has almost NO record yet
            #   (elite_conv desk born Sep 1; its pair cells are n=2).
            #   Ships on the user's call, proves on tier `tnelite`;
            #   the MEASURED strong TN pair is apex+takenow_hot
            #   (52% / +0.354R, n=142), covered by DUO 85+.
            #   🏆🔥 apextn (user go 2026-09-04): APEX + TAKE NOW HOT
            #   — the strongest measured pair not yet named: 52% /
            #   +0.354R over 142 closed, second only to the king pair.
            _NAMED_PAIRS = {
                frozenset(("best_board", "one_trade")): "kingpair",
                frozenset(("takenow_hot", "elite_conv")): "tnelite",
                frozenset(("apex", "takenow_hot")): "apextn",
            }
            _du_key = _NAMED_PAIRS.get(frozenset(_du["tiers"]))
            if _du_key is None:
                # 🤝 DUO gate at 85 — the measured winner cell (50% /
                # +0.218R at conf 85+; user briefly set 80 on
                # 2026-09-03 and reverted to 85 the same minute).
                if (_du.get("conf") or 0) < 85:
                    continue
                _du_key = "duo85"
            _du_king = _du_key == "kingpair"
            if not store.should_alert(
                    f"{_du_key}:{_du['symbol']}:{_du['side']}",
                    4 * 3600):
                continue
            _du_b = _du["symbol"].replace("USDT", "")
            _du_names = {"apex": "🏆 APEX", "best_board": "💎 BEST",
                         "one_trade": "👑 ONE TRADE",
                         "elite_conv": "💎 ELITE CONV",
                         "elite_confirm": "💎✅ ELITE CONFIRM",
                         "elite_early": "🌟 EARLY ELITE",
                         "takenow_hot": "✅🔥 TAKE NOW HOT"}
            _du_t = " + ".join(_du_names.get(t, t) for t in _du["tiers"])
            _du_t2 = (f" · TP2 `{float(_du['tp2']):g}`"
                      if _du.get("tp2") else "")
            _du_cf = (f"{float(_du['conf']):.0f}"
                      if _du.get("conf") is not None else "—")
            if _du_king:
                _du_msg = (
                    f"💎👑 *KING PAIR — {_du_b} {_du['side']}* — "
                    f"BEST + ONE TRADE together\n"
                    f"both fired within 30 min · 🎯 conf "
                    f"{_du_cf}/100\n"
                    f"entry `{float(_du['entry']):g}` · SL "
                    f"`{float(_du['stop']):g}` · TP1 "
                    f"`{float(_du['tp1']):g}`{_du_t2}\n"
                    f"_the measured best pair on the board: 51% / "
                    f"+0.540R over 86 closed (57% at conf 85+)._")
            elif _du_key == "apextn":
                _du_msg = (
                    f"🏆🔥 *APEX × TN — {_du_b} {_du['side']}* — "
                    f"APEX + TAKE NOW HOT agree\n"
                    f"both fired within 30 min · 🎯 conf "
                    f"{_du_cf}/100\n"
                    f"entry `{float(_du['entry']):g}` · SL "
                    f"`{float(_du['stop']):g}` · TP1 "
                    f"`{float(_du['tp1']):g}`{_du_t2}\n"
                    f"_measured pair: 52% / +0.354R over 142 closed "
                    f"— second only to the king pair._")
            elif _du_key == "tnelite":
                _du_msg = (
                    f"🔥💎 *TN × ELITE — {_du_b} {_du['side']}* — "
                    f"TAKE NOW HOT + ELITE CONV agree\n"
                    f"both fired within 30 min · 🎯 conf "
                    f"{_du_cf}/100\n"
                    f"entry `{float(_du['entry']):g}` · SL "
                    f"`{float(_du['stop']):g}` · TP1 "
                    f"`{float(_du['tp1']):g}`{_du_t2}\n"
                    f"_user-picked pair, record still PROVING (desk "
                    f"tier tnelite). Conf benchmark from the panel: "
                    f"2-stream clusters at 85+ ran 50% / +0.218R; "
                    f"below 85 the duo bands measured red — weight "
                    f"the 🎯 number accordingly._")
            else:
                _du_msg = (
                    f"🤝 *DUO 85+ — {_du_b} {_du['side']}* — the "
                    f"measured winner cell\n"
                    f"{_du_t} both fired within 30 min · 🎯 conf "
                    f"{_du_cf}/100\n"
                    f"entry `{float(_du['entry']):g}` · SL "
                    f"`{float(_du['stop']):g}` · TP1 "
                    f"`{float(_du['tp1']):g}`{_du_t2}\n"
                    f"_2 streams + conf 85+ = 50% / +0.218R live "
                    f"(n=28). A 3rd stream joining downgrades the "
                    f"cell — don't chase re-fires._")
            ok, _ = tg.send(_du_msg)
            n_alerts += 1 if ok else 0
            try:
                _du_sig = {"symbol": _du["symbol"], "base": _du_b,
                           "side": _du["side"], "entry": _du["entry"],
                           "stop": _du["stop"], "tp1": _du["tp1"],
                           "tp2": _du["tp2"], "conf": _du["conf"],
                           "tier": "+".join(_du["tiers"])}
                store.record_signal(_du_key, _du_sig)
                try:
                    _du_px = binance_client.get_ticker_price(
                        _du["symbol"])
                except Exception:
                    _du_px = None
                shadow_trader.open_from_signal(
                    _du_key, _du_sig, _du_px)
            except Exception as _du_exc2:
                print(f"  {_du_key} record error:", _du_exc2,
                      flush=True)
            print(f"[{_du_key}] 🤝 {_du_b} {_du['side']} "
                  f"({_du_t})", flush=True)
            # 🎮 GEN 8 P2 feed: every pair buzz is a demo candidate
            _DEMO_DUOS.append(
                {"symbol": _du["symbol"], "base": _du_b,
                 "side": _du["side"], "entry": _du["entry"],
                 "stop": _du["stop"], "tp1": _du["tp1"],
                 "tp2": _du.get("tp2"),
                 "score": float(_du.get("conf") or 90),
                 "src": "duo_band", "fired_at": time.time()})
            del _DEMO_DUOS[:-20]
    except Exception as _du_exc:
        print("  duo85 error:", _du_exc, flush=True)

    # 🤖💸 AGENTIC LIVE EXECUTOR (user go 2026-07-13, after the desk gate
    # was met on live forward records). Real Bybit orders from the PROVEN
    # tiers only (early_lane > apex > fresh > early_movers, deduped,
    # in-zone). Armed ONLY when LIVE_EXECUTOR=1 + Bybit keys are set in
    # the environment; every rail lives in live_executor/live_broker
    # (1% risk, max 3 open, daily -3% halt, -15% kill switch, exchange-
    # side stops, 48h policy parity with the desk).
    try:
        def _live_px(sym):
            try:
                return binance_client.get_ticker_price(sym)
            except Exception:
                return None
        _lx = live_executor.run_cycle(
            {"early_lane": em_big, "apex": apex, "fresh": fresh_m,
             "early_movers": r.get("early_strong", [])}, _live_px)
        for _po in _lx.get("opened", []):
            ok, _ = tg.send(
                f"💸 *LIVE OPENED* — {_po.get('base')} {_po.get('side')} "
                f"({_po.get('tier')})\n"
                f"qty `{_po.get('qty')}` @ `{_po.get('entry'):g}` · "
                f"SL `{_po.get('stop'):g}` · TP1 `{_po.get('tp1'):g}` · "
                f"ride to `{_po.get('target'):g}` · {_po.get('leverage')}x\n"
                f"_exchange stop set · BE at +1R · TP1 locks the win · "
                f"trail rides · 48h max_")
            n_alerts += 1 if ok else 0
        for _pc in _lx.get("closed", []):
            _pu = float(_pc.get("pnl_usd") or 0)
            ok, _ = tg.send(
                f"💸 *LIVE CLOSED* — {_pc.get('base')} "
                f"{_pc.get('exit_reason')} · "
                f"${_pu:+,.2f} ({float(_pc.get('pnl_pct') or 0):+.2f}%)")
            n_alerts += 1 if ok else 0
        if _lx.get("killed"):
            ok, _ = tg.send(
                "🛑 *KILL SWITCH FIRED* — live equity hit the max-drawdown "
                "floor. Everything closed at market; live trading is "
                "HALTED and stays halted until you and Claude review.")
            n_alerts += 1 if ok else 0
        for _note in _lx.get("notes", []):
            if ("loss limit" in _note.lower()
                    and store.should_alert("live_daily_halt", 20 * 3600)):
                ok, _ = tg.send(
                    "⛔ *LIVE DAILY HALT* — the -"
                    f"{live_executor.DAILY_LOSS_PCT:g}% daily loss cap "
                    "was hit. No new live entries for the next 24h; open "
                    "positions keep their exchange stops and ladder. "
                    "This is the seatbelt working, not a malfunction.")
                n_alerts += 1 if ok else 0
            if ("adopted external" in _note
                    and store.should_alert(f"live_adopt:{_note[:60]}",
                                           12 * 3600)):
                ok, _ = tg.send(f"👀 *LIVE* — {_note}")
                n_alerts += 1 if ok else 0
            if "ARMED" in _note:
                ok, _ = tg.send(
                    f"🤖💸 *LIVE EXECUTOR {_note}* — trading the proven "
                    f"tiers (early-lane, apex, fresh, early movers) at "
                    f"{live_executor.RISK_PCT:g}% risk/trade, max "
                    f"{live_executor.MAX_CONCURRENT} open, daily "
                    f"-{live_executor.DAILY_LOSS_PCT:g}% halt, "
                    f"-{live_executor.KILL_PCT:g}% kill switch.")
                n_alerts += 1 if ok else 0
            print(f"  live_exec: {_note}", flush=True)
    except Exception as exc:
        print("  live_exec error:", exc, flush=True)

    # 🌊 TREND HEALTH pings (🔴 exit / 🟡 caution) REMOVED entirely per
    # user 2026-07-13 ("I don't want the trend rider notification") —
    # the desk shadow record keeps building silently on the app.

    # 📟 ELITE PULSE (user 2026-08-25 v2: "i want it for every coin —
    # if this happens on elite conviction or elite confirm you should
    # watch every move of them"). Every coin with a LIVE 💎 elite
    # MAX/HIGH card or an active 💎✅ confirm watch gets the 15m
    # fast-clock check each cycle: a turn with strength (early-trend
    # >= 80 side-matched) or a 15m burst ignition (>= 78) buzzes
    # IMMEDIATELY. Pulse WITH the card's side = igniting NOW; pulse
    # AGAINST it = the fast clock turning on the card — the warning.
    # The FF lesson made general (his coin ran +7.5% in ~90 min while
    # the 1h clock was silent; the 15m tells had it 90 min early).
    # Info alarm, honestly labeled. 2h per (coin, side) cooldown.
    try:
        _pl_cards = {}
        for _p9 in _ec_mh:
            _sd0 = (_p9.get("side") or "").upper()
            if _sd0 in ("LONG", "SHORT"):
                _pl_cards[_p9["symbol"]] = (
                    _sd0, f"💎 {_p9.get('tier')} "
                          f"{float(_p9.get('score') or 0):.0f}")
        for _kw9, _w9 in list(_EC_WATCH.items()):
            _pl_cards.setdefault(_kw9[0], (
                _kw9[1], f"💎✅ watch · {_w9.get('tier')} "
                         f"{float(_w9.get('score') or 0):.0f}"))
        for _hp_sym, (_pl_side, _pl_tag) in _pl_cards.items():
            try:
                _hp_df = binance_client.get_klines(_hp_sym, "15m",
                                                   limit=200)
            except Exception:
                continue
            if _hp_df is None or len(_hp_df) < 60:
                continue
            try:
                _hp_ts, _hp_td, _ = _et_w.detect(_hp_df)
            except Exception:
                _hp_ts, _hp_td = 0.0, ""
            try:
                _hp_bs, _hp_bd, _ = _vb_w.lane_velocity_burst(_hp_df)
            except Exception:
                _hp_bs, _hp_bd = 0.0, ""
            _hp_td = (_hp_td or "").upper()
            _hp_bd = (_hp_bd or "").upper()
            _hp_side = None
            if _hp_bs >= 78 and _hp_bd in ("LONG", "SHORT"):
                _hp_side = _hp_bd
            elif _hp_ts >= 80 and _hp_td in ("LONG", "SHORT"):
                _hp_side = _hp_td
            if not _hp_side:
                continue
            # 2026-08-28 user call: 🟢 with-the-card pulse OFF (the
            # 💥 trigger ladder owns the igniting moment, with a
            # plan attached). Only the 🔴 AGAINST-the-card warning
            # buzzes — the one read no other stream provides.
            if _hp_side == _pl_side:
                continue
            if _bstock_quiet(_hp_sym):
                continue
            if not store.should_alert(
                    f"pulse:{_hp_sym}:{_hp_side}", 2 * 3600):
                continue
            _hp_c = _hp_df["close"].to_numpy()
            _hp_v = _hp_df["volume"].to_numpy()
            _hp_mv = (float(_hp_c[-1]) / float(_hp_c[-7]) - 1) * 100 \
                if len(_hp_c) > 7 else 0.0
            _hp_vk = (float(_hp_v[-1])
                      / max(1e-9, float(_hp_v[-21:-1].mean())))
            _hp_b = _hp_sym.replace("USDT", "")
            _hp_word = (f"🔴 15m turning AGAINST the card "
                        f"({_pl_tag}) — caution")
            # 📵 BUZZ DIET 2 (user 2026-08-29: "rest mute") — 📟
            # pulse red warnings off Telegram. Detection + records
            # unchanged. Revert: uncomment the tg.send below.
            # ok, _ = tg.send(
            #     f"📟 *ELITE PULSE* — {_hp_b} {_hp_word}\n"
            #     f"trend {_hp_ts:.0f} {_hp_td or '-'} · 15m burst "
            #     f"{_hp_bs:.0f} {_hp_bd or '-'} · last 90m "
            #     f"{_hp_mv:+.1f}% · vol x{_hp_vk:.1f}\n"
            #     f"_the fast clock on every elite-family coin — "
            #     f"moves start here ~30-90 min before the 1h engine "
            #     f"speaks. Info alarm, not a sized entry._")
            print(f"  📟 pulse (muted): {_hp_b} {_hp_word}",
                  flush=True)
    except Exception as _hp_exc:
        print("  elite-pulse error:", _hp_exc, flush=True)

    # 🕵️ OI LOAD — the PRE-SPIKE radar (user 2026-08-26: "strong
    # ignition is shown when the candles show a spike... i want to
    # sense and know the trade BEFORE the spike"). Every price-based
    # early construct measured red — candles cannot precede
    # themselves. The ONE validated pre-spike tell is POSITIONING:
    # futures OI building >= 3% in the trailing 8h while price is
    # still quiet ran at 2.19x the base rate before >=10% runs
    # (backtest_insider, 206 events vs 778 controls). This buzzes
    # the loading and records it for the capture ledger; it never
    # sizes a trade itself (the direct entry construct measured
    # -0.21R — the alarm plus the armed-levels ladder IS the play).
    global _OI_LAST
    if _now - _OI_LAST >= 900:
        _OI_LAST = _now
        try:
            _oi_syms = binance_client.get_top_symbols(
                100)["symbol"].tolist()
            for _os in _oi_syms:
                try:
                    _oh = _dv_w._fapi_get(
                        "/futures/data/openInterestHist",
                        {"symbol": _os, "period": "1h",
                         "limit": 10})
                    if not _oh or len(_oh) < 9:
                        continue
                    _o0 = float(_oh[0]["sumOpenInterestValue"])
                    _o1 = float(_oh[-1]["sumOpenInterestValue"])
                    if _o0 <= 0:
                        continue
                    _bld = (_o1 / _o0 - 1) * 100
                    # ⚡ FAST LANE (user 2026-08-28: "why is it 8h —
                    # silent coins... short time stamps"): a 15m OI
                    # read catches a sudden load in ~90 min instead
                    # of hours. Measured WEAKER alone (the short
                    # window ran 1.27x vs 2.19x for the slow build),
                    # so fast-only detections need grade A
                    # corroboration before they may buzz.
                    _kick = 0.0
                    try:
                        _oh15 = _dv_w._fapi_get(
                            "/futures/data/openInterestHist",
                            {"symbol": _os, "period": "15m",
                             "limit": 8}) or []
                        if len(_oh15) >= 6:
                            _k0 = float(
                                _oh15[0]["sumOpenInterestValue"])
                            _k1 = float(
                                _oh15[-1]["sumOpenInterestValue"])
                            if _k0 > 0:
                                _kick = (_k1 / _k0 - 1) * 100
                    except Exception:
                        pass
                    _slow = _bld >= 3.0
                    _fast = _kick >= 2.0
                    if not (_slow or _fast):
                        continue
                    _dfq = binance_client.get_klines(_os, "1h",
                                                     limit=130)
                    if _dfq is None or len(_dfq) < 40:
                        continue
                    _cq = _dfq["close"].to_numpy()
                    _chq = (float(_cq[-1]) / float(_cq[-25]) - 1) \
                        * 100
                    if abs(_chq) >= 5.0:
                        continue    # already moving — not pre-spike
                    _hq = _dfq["high"].to_numpy()
                    _lq = _dfq["low"].to_numpy()
                    _atrq = float((_hq[-14:] - _lq[-14:]).mean())
                    _pxq = float(_cq[-1])
                    # ── v2 FUSION (user 2026-08-28: "make this with
                    # pulse and candles and movement... work with the
                    # whole system"): grade every load with every
                    # validated tell the system owns. More agreeing
                    # tells = earlier + stronger; graded honestly,
                    # never called certain.
                    _gp, _gn = 0, []
                    # 1) 📟 the 15m pulse — earliest candles stirring
                    try:
                        _d15q = binance_client.get_klines(
                            _os, "15m", limit=120)
                        _t15, _t15d, _ = _et_w.detect(_d15q)
                        _b15, _b15d, _ = _vb_w.lane_velocity_burst(
                            _d15q)
                        if (_t15 >= 60 and _t15d == "LONG") or \
                                (_b15 >= 55 and (_b15d or "").upper()
                                 == "LONG"):
                            _gp += 1
                            _gn.append("📟 15m stirring")
                    except Exception:
                        pass
                    # 2) 🌀 tight coil — the one pre-burst shape that
                    # ever measured green (armed-coil break +0.12R)
                    try:
                        _r24 = (float(_hq[-24:].max())
                                - float(_lq[-24:].min())) / _pxq
                        _rpr = (float(_hq[-120:-24].max())
                                - float(_lq[-120:-24].min())) / _pxq
                        if _rpr > 0 and _r24 / (_rpr / 4) < 0.9:
                            _gp += 1
                            _gn.append("🌀 tight coil")
                    except Exception:
                        pass
                    # 3) 🏗 loaded spring — sitting AT the high, not
                    # the bottom of a dump
                    if _pxq >= float(_hq[-24:].max()) * 0.985:
                        _gp += 1
                        _gn.append("🏗 at the high")
                    # 4) 💸 funding jump — the rare 4.2x tell
                    try:
                        _fr9 = _dv_w._fapi_get(
                            "/fapi/v1/fundingRate",
                            {"symbol": _os, "limit": 6}) or []
                        if len(_fr9) >= 4:
                            _fnew = float(_fr9[-1]["fundingRate"])
                            _fold = sum(
                                float(x["fundingRate"])
                                for x in _fr9[:-1]) / (len(_fr9) - 1)
                            if (_fnew - _fold) * 1e4 >= 2.0:
                                _gp += 1
                                _gn.append("💸 funding jump")
                    except Exception:
                        pass
                    # 5) 💎 a card already sniffing it
                    if _os in {p9.get("symbol") for p9 in _ec_mh} or \
                            _os in {p9.get("symbol")
                                    for p9 in (r.get("strong") or [])}:
                        _gp += 1
                        _gn.append("💎 card live")
                    # 6) ⚡ the fast kick corroborating the slow build
                    if _fast:
                        _gp += 1
                        _gn.append(f"⚡ fast kick "
                                   f"+{_kick:.1f}%/90m")
                    _grade = ("A" if _gp >= 3 else
                              "B" if _gp == 2 else "C")
                    _hi24 = float(_hq[-24:].max())
                    _sigq = {"symbol": _os,
                             "base": _os.replace("USDT", ""),
                             "side": "LONG",
                             "build": round(_bld, 1),
                             "kick": round(_kick, 1),
                             "lane": ("slow+fast" if _slow and _fast
                                      else "slow" if _slow
                                      else "fast"),
                             "ch24": round(_chq, 1),
                             "grade": _grade, "tells": _gp,
                             "notes": " · ".join(_gn)}
                    if _atrq > 0 and _pxq > 0:
                        _sigq.update(
                            entry=_pxq, stop=_pxq - 1.5 * _atrq,
                            tp1=_pxq + 1.5 * _atrq,
                            tp2=_pxq + 3.0 * _atrq)
                    store.record_signal("oi_load", _sigq)
                    # 🧪 desk proving tier — one per coin, ATR plan
                    # at detection; the live ledger grades the alarm.
                    try:
                        if _sigq.get("entry"):
                            shadow_trader.open_from_signal(
                                "oi_load", _sigq, _pxq)
                    except Exception:
                        pass
                    # 💥 A/B loads ARM the trigger ladder at the 24h
                    # high — the whole system takes over: 🔶 near and
                    # 💥 break buzzes, desk fire on the break. The
                    # earliest tell feeding the proven machinery.
                    if _grade in ("A", "B") and _atrq > 0 \
                            and _hi24 > _pxq:
                        with _TRIG_LOCK:
                            _k_oi = (_os, "LONG")
                            if _k_oi not in _TRIG_ARMED:
                                _TRIG_ARMED[_k_oi] = {
                                    "symbol": _os,
                                    "base": _os.replace("USDT", ""),
                                    "side": "LONG",
                                    "trigger": _hi24,
                                    "entry": _hi24,
                                    "stop": _hi24 - 1.5 * _atrq,
                                    "tp1": _hi24 + 1.5 * _atrq,
                                    "tp2": _hi24 + 3.0 * _atrq,
                                    "score": 60 + 10 * _gp,
                                    "src": f"🕵️ OI LOAD {_grade}",
                                    "armed_at": _now,
                                    "near_sent": False,
                                    "mom_sent": False}
                    if _bstock_quiet(_os):
                        continue
                    if _grade == "C":
                        continue    # C = OI alone — board + records
                                    # only (the buzz diet holds)
                    if not _slow and _grade != "A":
                        continue    # ⚡ fast-only lane is the weaker
                                    # measured tell — it must earn an
                                    # A (3+ tells) to buzz
                    if not store.should_alert(f"oiload:{_os}",
                                              4 * 3600):
                        continue
                    _ld9 = (f"positioning +{_bld:.1f}%/8h"
                            if _slow else
                            f"⚡ sudden load +{_kick:.1f}%/90m")
                    # 📵 BUZZ DIET 2 (user 2026-08-29: "rest mute")
                    # — 🕵️ OI LOAD detection buzz off Telegram. The
                    # ARMING stays: breaks still fire through the 💥
                    # trigger ladder (roster item), and oi_load /
                    # oi_break desk tiers keep recording. Revert:
                    # uncomment the tg.send below.
                    # ok, _ = tg.send(
                    #     f"🕵️ *OI LOAD {_grade} — PRE-SPIKE* — "
                    #     f"{_os.replace('USDT', '')} "
                    #     f"({_gp + 1} tells)\n"
                    #     f"{_ld9} · price "
                    #     f"{_chq:+.1f}%/24h · {_sigq['notes']}\n"
                    #     f"💥 armed at `{_hi24:g}` — the ladder "
                    #     f"buzzes 🔶 near and 💥 on the break\n"
                    #     f"_money loading BEFORE the spike; grade "
                    #     f"{_grade} = OI + "
                    #     f"{_gp} system tells agreeing. Early, "
                    #     f"graded, never guaranteed._")
                    print(f"  🕵️ load (muted): {_os} {_grade} "
                          f"{_ld9}", flush=True)
                except Exception:
                    continue
                time.sleep(0.12)
        except Exception as _oi_exc:
            print("  oi-load radar error:", _oi_exc, flush=True)

    # 🎮 DEMO ZONE — the $1,200 one-week live-fire test (user
    # 2026-08-09): the worker auto-picks the HIGHEST-QUALITY signals
    # (💯>🥇>🎯>🔮✅>🚀>elite, boosted by live 14d form + score) under
    # REAL-account constraints: 3 slots, one per coin, 2% risk off the
    # current balance, taker fees both sides, TP1 half-bank + BE,
    # TP2/48h exits. Simulated only — no real orders; buzzes every
    # move so the user watches it trade.
    try:
        _dz = demo_account.load()
        # GEN 6 (user 2026-08-23: "we only go with Strong triggers
        # and Re Run, and Elite conviction max... nothing else should
        # be a part of demo trading except the ones i told"): exactly
        # three streams. Form boosts come from each stream's own live
        # desk ledger.
        # GEN 8 form boosts: each pool's own live desk ledger (duo
        # form = the duo85 tier; young tiers just read ~0 = neutral).
        _dz_form = {}
        for _dt, _sh in (("strong_trigger", "trig_strong"),
                         ("duo_band", "duo85"),
                         ("pw_waking", "personal_watch_early")):
            try:
                _dz_form[_dt] = store.shadow_recent_net(_sh)["net_r"]
            except Exception:
                _dz_form[_dt] = 0.0
        # 💎 ELITE CONVICTION (SECONDARY, max 2 of 6 seats — capped
        # in demo_account.MAX_PER_SRC): only the CREAM spends (user
        # 2026-08-23: "max or approved and calculated trades that
        # have the best outcomes not some that are bleh") — 🚀
        # approved (65.5% vs 48.5%, the proven gate) AND top grade:
        # MAX tier, a 90+ score, or (user follow-up the same day)
        # 2+ lanes agreeing with a score of 85+. Approved HIGH in
        # the low 80s with no lane agreement keeps its buzz and its
        # board; it just doesn't spend demo money.
        _dz_elite = [dict(p, lane_approved=True) for p in _ec_mh
                     if p.get("appr")
                     and ((p.get("tier") or "").upper() == "MAX"
                          or float(p.get("score") or 0) >= 90
                          or (int(p.get("lanes") or 0) >= 2
                              and float(p.get("score") or 0) >= 85))]
        # 💎🔄 RE-QUALIFIED cards are re-runs by definition (user
        # 2026-08-19: a coin already traded that qualifies again is a
        # NEW setup, approved or unapproved) — they take the TOP seat.
        _dz_requal = [dict(p) for p in _ec_mh if p.get("requal")]
        # 💥 fresh BREAKS from the 60s watch (<=30 min old — the zone
        # gate in try_open rejects anything that already ran away).
        with _TRIG_LOCK:
            _DEMO_FIRES[:] = [f for f in _DEMO_FIRES
                              if _now - f["fired_at"]
                              <= DEMO_FIRE_TTL_S]
            _dz_fires = list(_DEMO_FIRES)
        # 💎✅ confirmed entries (user follow-up: elite family seats
        # are elite cards + confirmed entries together, capped in
        # demo_account.ELITE_FAMILY_CAP)
        _ECF_FIRES[:] = [f for f in _ECF_FIRES
                         if _now - f["fired_at"] <= DEMO_FIRE_TTL_S]
        # 🎯 GEN 7 BEST-OF-BEST seats (user 2026-08-26: "best of the
        # best... confidence score 98/100 or above, above 80/100 as
        # we have it on telegram — 3 slots"): 💎 BEST ZONE cards
        # carrying the telegram 🎯 confidence read >= 80, ranked by
        # it — the 98+ ones outrank everything in the lane.
        _dz_best = []
        for _bp7 in best:
            try:
                _cf7 = float(best_board.confidence(
                    _bp7.get("symbol"), _bp7.get("side")) or 0)
            except Exception:
                _cf7 = 0.0
            if _cf7 >= 80:
                _dz_best.append(dict(_bp7, conf=_cf7, score=_cf7))
        # 🎮 GEN 8 POOLS (user 2026-09-05): exactly the named three,
        # in priority order — 💥 strong triggers (P1, includes 🔄
        # re-run breaks: same construct re-firing), 🤝 the measured
        # duo/pair buzzes (P2), ⚡ the 20-coin waking lane (P3). The
        # GEN 7 best_conf / elite pools retire with their generation.
        _DEMO_DUOS[:] = [d for d in _DEMO_DUOS
                         if _now - d["fired_at"] <= DEMO_FIRE_TTL_S]
        _DEMO_WAKE[:] = [d for d in _DEMO_WAKE
                         if _now - d["fired_at"] <= DEMO_FIRE_TTL_S]
        # 🔁 momentum re-entries from last cycle's TP1 banks
        _dz_reo = [d for d in _DEMO_REOPEN
                   if _now - d["fired_at"] <= 900]
        _DEMO_REOPEN[:] = []
        _dz_pools = {
            "strong_trigger": ([f for f in _dz_fires
                                if f["src"] in ("strong_trigger",
                                                "rerun")]
                               + [d for d in _dz_reo
                                  if d["src"] == "strong_trigger"]),
            "duo_band": (list(_DEMO_DUOS)
                         + [d for d in _dz_reo
                            if d["src"] == "duo_band"]),
            "pw_waking": (list(_DEMO_WAKE)
                          + [d for d in _dz_reo
                             if d["src"] == "pw_waking"])}
        # 🔄 GEN 7 rotation input: every (coin, side) with a LIVE
        # signal this cycle — positions outside this set are the
        # rotation candidates ("a losing trade stands only while
        # its signals are healthy").
        _dz_active = set()
        for _pl7 in _dz_pools.values():
            for _p7 in _pl7:
                _dz_active.add((_p7.get("symbol"),
                                (_p7.get("side") or "").upper()))
        def _dz_kr(sym, side):
            """Cached kronos read; force-fetch for the demo's few open
            positions so the smart exit always has a fresh view."""
            _h = _KR_CACHE.get(sym)
            if _h and _now - _h["t"] < KR_TTL:
                return _h["s"]
            if not _kr_ok:
                return None
            try:
                _v = kf.forecast(sym, "1h", horizon=24)
                if _v:
                    _KR_CACHE[sym] = {"t": _now, "s": _v}
                return _v
            except Exception:
                return None
        _dz_events = demo_account.manage(_dz, _live, _dz_kr)
        # 🔁 GEN 8 MOMENTUM RE-ENTRY (user 2026-09-05: "let it ride
        # to tp1 and close it. if the momentum is still there open
        # the trade again"): every TP1 bank gets a 1h-burst check —
        # still >= 65 on the trade's side -> the same plan geometry
        # re-anchors at the live price and queues for the next
        # cycle's seats. Chain-capped at 2 re-entries per trade.
        for _ev8, _rec8 in _dz_events:
            try:
                if _ev8 != "close" or "TP1" not in str(
                        _rec8.get("reason", "")):
                    continue
                _rp8 = _rec8.get("replan") or {}
                if int(_rp8.get("chain") or 0) >= 2:
                    continue
                _d8 = binance_client.get_klines(
                    _rec8["symbol"], "1h", limit=120)
                _b8, _bd8, _ = _vb_w.lane_velocity_burst(_d8)
                if not (_b8 >= 65 and (_bd8 or "").upper()
                        == _rec8["side"]):
                    continue
                _px8 = float(_rec8.get("exit") or 0)
                _sd8 = float(_rp8.get("stop_d") or 0)
                _t18 = float(_rp8.get("tp1_d") or 0)
                if _px8 <= 0 or _sd8 <= 0 or _t18 <= 0:
                    continue
                _sgn8 = 1 if _rec8["side"] == "LONG" else -1
                _DEMO_REOPEN.append(
                    {"symbol": _rec8["symbol"],
                     "base": _rec8["base"], "side": _rec8["side"],
                     "entry": _px8,
                     "stop": _px8 - _sgn8 * _sd8,
                     "tp1": _px8 + _sgn8 * _t18,
                     "tp2": (_px8 + _sgn8 * float(_rp8["tp2_d"])
                             if _rp8.get("tp2_d") else None),
                     "score": float(_rp8.get("score") or 80),
                     "src": (_rec8.get("src")
                             if _rec8.get("src") in
                             ("strong_trigger", "duo_band",
                              "pw_waking") else "strong_trigger"),
                     "chain": int(_rp8.get("chain") or 0) + 1,
                     "fired_at": _now})
                print(f"[gen8] 🔁 momentum re-entry queued "
                      f"{_rec8['base']} {_rec8['side']} "
                      f"(burst {_b8:.0f})", flush=True)
            except Exception as _re8_exc:
                print("  gen8 reopen error:", _re8_exc, flush=True)
        _dz_opened, _dz_rot = demo_account.try_open(
            _dz, demo_account.rank_candidates(_dz_pools, _dz_form),
            _live, active=_dz_active)
        demo_account.save(_dz)
        # 📵 GEN7 demo buzzes OFF (user 2026-08-31: "remove gen7
        # notifications from my telegram notifications"). The demo
        # keeps trading and its ledger + board keep updating — only
        # the phone goes quiet. Revert: _DZ_BUZZ = True.
        _DZ_BUZZ = False

        def _dz_tg(_m):
            return tg.send(_m) if _DZ_BUZZ else (False, "muted")

        for _rr in _dz_rot:
            ok, _ = _dz_tg(
                f"🎮🔄 *DEMO $1500 GEN8* — ROTATED OUT "
                f"{_rr['base']} {_rr['side']} ({_rr['reason']}) → "
                f"{'+' if _rr['pnl'] >= 0 else ''}"
                f"${_rr['pnl']:,.2f}\n"
                f"_seat freed for a stronger live signal_ · balance "
                f"`${_dz['balance']:,.2f}`")
            n_alerts += 1 if ok else 0
        for _po in _dz_opened:
            _agr = int(_po.get("agree", 1))
            ok, _ = _dz_tg(
                f"🎮 *DEMO $1500 GEN8* — OPENED {_po['base']} "
                f"{_po['side']} "
                f"({'🤝 ' + str(_agr) + ' SYSTEMS AGREE · ' if _agr > 1 else ''}"
                f"src `{_po.get('srcs', _po['src'])}` · score "
                f"{_po['score']:.0f}"
                f"{' · 🔥 burst ' + format(_po['burst'], '.0f') if float(_po.get('burst') or 0) >= 85 else ''})\n"
                f"entry `{_po['entry']:g}` · SL `{_po['stop']:g}` · "
                f"TP1 `{_po['tp1']:g}` · notional "
                f"${_po['notional']:,.0f} "
                f"(${_po.get('margin', 0):,.0f} margin × "
                f"{_po.get('lev', '?')}x)\n"
                f"balance `${_dz['balance']:,.2f}`")
            n_alerts += 1 if ok else 0
        for _ev, _rec in _dz_events:
            if _ev == "guard":
                # 🧠🛡 strength-aware guard — position still open, the
                # brain gave a STRONG signal room instead of banking
                ok, _ = _dz_tg(
                    f"🎮🧠 *DEMO $1500 GEN8* — RIDING THROUGH THE "
                    f"FLIP {_rec['base']} {_rec['side']}\n"
                    f"{_rec['reason']}\nstop now "
                    f"`{_rec['stop']:g}` · balance "
                    f"`${_dz['balance']:,.2f}`")
                n_alerts += 1 if ok else 0
                continue
            _tag = ("💰 TP1 half-banked" if _ev == "tp1"
                    else "CLOSED")
            ok, _ = _dz_tg(
                f"🎮 *DEMO $1500 GEN8* — {_tag} {_rec['base']} "
                f"{_rec['side']} ({_rec['reason']}) → "
                f"{'+' if _rec['pnl'] >= 0 else ''}"
                f"${_rec['pnl']:,.2f}\n"
                f"balance `${_dz['balance']:,.2f}`")
            n_alerts += 1 if ok else 0
    except Exception as _dz_exc:
        print("  demo error:", _dz_exc, flush=True)

    # 💥 arm the trigger watch (user 2026-08-15): every 💎 approved
    # elite conviction card + every ⚡ STRONG watch coil not already
    # burst-firing gets a trigger at its 24-bar high/low; the 60s
    # thread below buzzes the moment one breaks.
    try:
        _arm_pool = [("💎 ELITE CONV", _p)
                     for _p in (locals().get("_dz_elite") or [])]
        _ig_keys = {(q.get("symbol"), (q.get("side") or "").upper())
                    for q in _igs}
        for _p in (r.get("strong") or []):
            _k2 = (_p.get("symbol"), (_p.get("side") or "").upper())
            if _k2 not in _ig_keys:
                _arm_pool.append(("⚡ STRONG", _p))
        _now_arm = time.time()
        _armed_n = 0
        _new_arms = []
        with _TRIG_LOCK:
            for _lbl, _p in _arm_pool[:16]:
                _sd2 = (_p.get("side") or "").upper()
                _sy2 = _p.get("symbol")
                if not _sy2 or _sd2 not in ("LONG", "SHORT") \
                        or not (_p.get("entry") and _p.get("stop")
                                and _p.get("tp1")):
                    continue
                try:
                    _dfa = binance_client.get_klines(_sy2, "1h",
                                                     limit=30)
                    _trg = (float(_dfa["high"].tail(24).max())
                            if _sd2 == "LONG"
                            else float(_dfa["low"].tail(24).min()))
                except Exception:
                    continue
                _kk2 = (_sy2, _sd2)
                _old = _TRIG_ARMED.get(_kk2) or {}
                _TRIG_ARMED[_kk2] = {
                    "symbol": _sy2,
                    "base": _p.get("base") or _sy2.replace("USDT", ""),
                    "side": _sd2, "trigger": _trg,
                    "entry": float(_p.get("entry") or 0),
                    "stop": float(_p.get("stop") or 0),
                    "tp1": float(_p.get("tp1") or 0),
                    "tp2": float(_p.get("tp2") or 0) or None,
                    "score": float(_p.get("score") or 0),
                    "src": _lbl,
                    "armed_at": _old.get("armed_at", _now_arm),
                    # arming is SILENT (user 2026-08-15 middle-ground
                    # call) — the 🔶 near-trigger warning in the 60s
                    # watch is the one early buzz; preserve the
                    # one-shot flags across cycle re-arms.
                    "near_sent": _old.get("near_sent", False),
                    "mom_sent": _old.get("mom_sent", False)}
                _armed_n += 1
                if not _old:
                    _new_arms.append(_kk2)
        # 🔥 SECOND-LEG arms (user 2026-08-17, the ACE case): recent
        # elite winners whose cards expired stay armed at their
        # consolidation high/low for SECOND_LEG_DAYS — the composite's
        # anti-chase suppression can't blind the watch to a re-
        # ignition anymore. ATR plan built at the level; live cards
        # keep priority (skip if already armed).
        _sl_cut = _now_arm - SECOND_LEG_DAYS * 86400
        _sl_n = 0
        with _TRIG_LOCK:
            for _sy3 in list(_SECOND_LEG):
                _sl = _SECOND_LEG[_sy3]
                if _sl["winner_at"] < _sl_cut:
                    _SECOND_LEG.pop(_sy3, None)
                    continue
                _k3 = (_sy3, _sl["side"])
                if _k3 in _TRIG_ARMED or _sl_n >= 12:
                    continue
                try:
                    _df3 = binance_client.get_klines(_sy3, "1h",
                                                     limit=40)
                    _h3 = _df3["high"].astype(float)
                    _l3 = _df3["low"].astype(float)
                    _c3 = _df3["close"].astype(float)
                    _tr3 = (_h3 - _l3).tail(14)
                    _atr3 = float(_tr3.mean())
                    _hi3 = float(_h3.tail(24).max())
                    _lo3 = float(_l3.tail(24).min())
                except Exception:
                    continue
                if _atr3 <= 0:
                    continue
                if _sl["side"] == "LONG":
                    _trg3 = _hi3
                    _stp3 = _trg3 - 1.5 * _atr3
                    _t13 = _trg3 + 1.5 * _atr3
                    _t23 = _trg3 + 3.0 * _atr3
                else:
                    _trg3 = _lo3
                    _stp3 = _trg3 + 1.5 * _atr3
                    _t13 = _trg3 - 1.5 * _atr3
                    _t23 = _trg3 - 3.0 * _atr3
                _old3 = _TRIG_ARMED.get(_k3) or {}
                _TRIG_ARMED[_k3] = {
                    "symbol": _sy3, "base": _sl["base"],
                    "side": _sl["side"], "trigger": _trg3,
                    "entry": _trg3, "stop": _stp3,
                    "tp1": _t13, "tp2": _t23,
                    "score": _sl.get("score", 0),
                    "src": "🔥 2ND LEG",
                    "armed_at": _old3.get("armed_at", _now_arm),
                    "near_sent": _old3.get("near_sent", False),
                    "mom_sent": _old3.get("mom_sent", False)}
                _sl_n += 1
        if _armed_n or _sl_n:
            print(f"  💥 trigger watch armed: {_armed_n} "
                  f"(+{len(_new_arms)} new, silent) · 🔥 second-leg "
                  f"arms: {_sl_n}", flush=True)
    except Exception as _tw_exc:
        print("  trigger-arm error:", _tw_exc, flush=True)
    # 💥 THE NUMBERS (user 2026-08-23: "a point where it can burst if
    # it hit that number... that is something we need to catch") —
    # publish every armed trigger level to the page, so the exact
    # burst prices are visible in advance, not just buzzed at break.
    try:
        import json as _json_al
        import os as _os_al
        with _TRIG_LOCK:
            _al_snap = [{"symbol": a.get("symbol"),
                         "base": a.get("base"),
                         "side": a.get("side"),
                         "src": str(a.get("src", "")),
                         "trigger": a.get("trigger"),
                         "stop": a.get("stop"),
                         "tp1": a.get("tp1"), "tp2": a.get("tp2"),
                         "score": a.get("score"),
                         "armed_at": a.get("armed_at")}
                        for a in _TRIG_ARMED.values()]
        _al_path = str(config.state_path(".armed_levels.json"))
        with open(_al_path + ".tmp", "w", encoding="utf-8") as _f_al:
            _json_al.dump({"ts": time.time(), "armed": _al_snap},
                          _f_al)
        _os_al.replace(_al_path + ".tmp", _al_path)
    except Exception as _al_exc:
        print("  armed-levels publish error:", _al_exc, flush=True)
    global _TRIG_STARTED
    if not _TRIG_STARTED:
        _TRIG_STARTED = True
        threading.Thread(target=_trigger_watch, daemon=True).start()
        print("  💥 trigger watch thread started (60s)", flush=True)

    # 🧭 24H BATTLE PLAN (user 2026-08-29: digests STAY, upgraded —
    # "what the situation looks like for next 24 hours... concrete
    # plan on the things happening as news... best trades... how btc
    # will behave"). Shared by the morning + evening reports.
    def _brief24():
        _bl = []
        try:
            _b1 = binance_client.get_klines("BTCUSDT", "1h", limit=30)
            _bpx = float(_b1["close"].iloc[-1])
            _bch = (_bpx / float(_b1["close"].iloc[-25]) - 1) * 100
        except Exception:
            _bpx, _bch = 0.0, 0.0
        try:
            import statistics as _st
            _alt9 = [float(p.get("pct_24h") or 0) for p in
                     (best or []) + (apex or [])
                     if p.get("pct_24h") is not None]
            _amed = _st.median(_alt9) if _alt9 else 0.0
        except Exception:
            _amed = 0.0
        _a4 = _a1d = _a1w = None
        try:
            _a4 = _sig_w.analyze(
                binance_client.get_klines("BTCUSDT", "4h", limit=300))
        except Exception:
            pass
        try:
            _a1d = _sig_w.analyze(
                binance_client.get_klines("BTCUSDT", "1d", limit=400))
        except Exception:
            pass
        try:
            _a1w = _sig_w.analyze(
                binance_client.get_klines("BTCUSDT", "1w", limit=200))
        except Exception:
            pass
        try:
            _fg9 = _sent_w.fear_greed().get("value")
        except Exception:
            _fg9 = None
        try:
            _mc9 = _mc_w.global_market().get("market_cap_change_24h")
        except Exception:
            _mc9 = None
        _nd = None
        _np = None
        try:
            _nd = _news_w.fetch_news()
            if _nd is not None and len(_nd):
                _bm = _nd["title"].str.contains(
                    r"\b(?:bitcoin|btc)\b", case=False, na=False,
                    regex=True)
                _np = {"btc": {"count": int(_bm.sum()),
                               "sentiment": (float(
                                   _nd[_bm]["sentiment"].mean())
                                   if _bm.any() else 0.0)},
                       "macro": _news_w.category_mood(
                           _nd, "Macro / Politics"),
                       "crypto": _news_w.category_mood(_nd, "Crypto")}
        except Exception:
            pass
        try:
            _o9 = btc_outlook.compute(_a4, _a1d, None, _fg9, _mc9,
                                      _bch, _amed, btc_1w=_a1w,
                                      news=_np)
            _ar9 = {"Up": "🟢▲", "Down": "🔴▼"}.get(
                _o9["direction"], "🟡◆")
            _bl.append(f"₿ *BTC NEXT 24H:* {_ar9} {_o9['takeaway']}")
            _bl.append(
                f"conf {_o9['confidence']}% · "
                f"{_o9['aligned_categories']}/"
                f"{_o9['total_categories']} categories agree · "
                f"expected range ±{_o9['expected_range_pct']:.1f}% "
                f"· BTC {_bpx:,.0f} ({_bch:+.1f}%/24h)")
            _st9 = (_o9.get("briefing") or {}).get("next_steps")
            if isinstance(_st9, (list, tuple)):
                _st9 = " ".join(str(x) for x in _st9[:2])
            if _st9:
                _bl.append(f"📋 *the plan:* {str(_st9)[:350]}")
        except Exception as _o_exc:
            print("  brief24 outlook error:", _o_exc, flush=True)
        try:
            if kf.available():
                _k9 = kf.forecast("BTCUSDT", "1h", horizon=24)
                if _k9:
                    _bl.append(
                        f"🔮 kronos on BTC: {_k9['direction']} "
                        f"{float(_k9.get('exp_move_pct') or 0):+.1f}%"
                        f"/24h (secondary voice)")
        except Exception:
            pass
        try:
            _imp = _ni_w.detect_impactful(_nd, max_count=3) \
                if _nd is not None else []
            if _imp:
                _bl.append("📰 *moving the tape right now:*")
                for _n9 in _imp:
                    _e9 = {"Bullish": "🟢", "Bearish": "🔴"}.get(
                        _n9.get("direction"), "⚪")
                    _bl.append(
                        f"{_e9} {_n9.get('source')}: "
                        f"{str(_n9.get('title'))[:110]} "
                        f"(impact {_n9.get('score')})")
        except Exception:
            pass
        return _bl

    # 📰 NARRATIVE RECORDER (user go 2026-09-04, validation-first
    # design): every hour, store the impactful headlines as per-coin
    # event flags. RECORDS ONLY — nothing reads event_flags to gate or
    # buzz. Pre-registered judgment: after ~2-3 weeks, flags join to
    # desk outcomes; the veto/boost claim must be green in both halves
    # of the window before any flag touches a buzz.
    try:
        if store.should_alert("evflag_hourly", 3600):
            _ef_df = _news_w.fetch_news()
            _ef_imp = _ni_w.detect_impactful(_ef_df, max_count=8) \
                if _ef_df is not None else []
            _ef_bases = {s.replace("USDT", "")
                         for s in getattr(config, "PERSONAL_WATCH", [])}
            try:
                _ef_bases |= {str(p.get("base") or "") for p in apex}
                _ef_bases |= {str(p.get("base") or "") for p in best}
            except Exception:
                pass
            _ef_n = 0
            for _ef in _ef_imp:
                _ef_t = str(_ef.get("title") or "")
                _ef_up = _ef_t.upper()
                _ef_syms = [b for b in _ef_bases
                            if b and len(b) >= 3 and b in _ef_up] or [None]
                for _ef_s in _ef_syms[:3]:
                    store.record_event_flag(
                        (_ef_s + "USDT") if _ef_s else None,
                        _ef.get("direction"), _ef.get("category"),
                        _ef.get("score"), _ef_t)
                    _ef_n += 1
            if _ef_n:
                print(f"[evflag] 📰 {_ef_n} event flags recorded",
                      flush=True)
    except Exception as _ef_exc:
        print("  evflag error:", _ef_exc, flush=True)

    # 📊🌅 DAILY MORNING REPORT — the 24h battle plan + best trades
    # (user 2026-07-08, upgraded 2026-08-29). Default 04:00 UTC =
    # 09:00 Pakistan; override with WORKER_DIGEST_HOUR_UTC.
    try:
        _dh_utc = int(getattr(config, "WORKER_DIGEST_HOUR_UTC", 4))
        _hr_now = datetime.now(timezone.utc).hour
        # 🔬 NIGHTLY AUDITOR (user go 2026-09-04, validated 5/5 on the
        # week's real defects — commit 9125e84): rides the same clock
        # window as the morning digest, its own 20h key so neither can
        # double-fire the other. One message: findings (or all-clear)
        # + yesterday-in-numbers + decision-ready tiers. Deterministic
        # SQL findings; Fable only phrases the headline, fail-soft.
        if (_dh_utc <= _hr_now < _dh_utc + 3
                and store.should_alert("auditor_daily", 20 * 3600)):
            try:
                import auditor as _aud
                _aud.run_daily(send=True)
                print("[auditor] daily report sent", flush=True)
            except Exception as _aud_exc:
                print("[auditor] error:", _aud_exc, flush=True)
        if (_dh_utc <= _hr_now < _dh_utc + 3
                and store.should_alert("daily_digest", 20 * 3600)):
            recs = shadow_trader.tier_records()
            lines = ["🌅 *MORNING REPORT* — the next 24 hours"]
            lines += _brief24()
            # -- best picks of the morning, ranked by validated quality ----
            _picks = []
            for p in best[:3]:
                _picks.append(("💎 BEST ZONE", p))
            for p in em_big[:2]:
                _picks.append(("🚀 EARLY-LANE (81% cell)", p))
            for p in apex[:2]:
                _picks.append(("🏆 APEX", p))
            for p in elite_early[:2]:
                _picks.append(("🌟 EARLY ELITE", p))
            _seen_pk: set = set()
            _picks = [(_l, _p) for _l, _p in _picks
                      if not (_p.get("symbol") in _seen_pk
                              or _seen_pk.add(_p.get("symbol")))][:5]
            if _picks:
                lines.append("*Best setups right now:*")
                for _lbl, p in _picks:
                    lines.append(
                        f"• {_lbl} — *{p['base']} {p['side']}* · entry "
                        f"`{p['entry']:g}` · SL `{p['stop']:g}` · TP1 "
                        f"`{p['tp1']:g}`")
            else:
                lines.append("_No fresh qualifying setups this morning — "
                             "patience is a position._")
            # -- desk record ----------------------------------------------
            lines.append("*Desk record (live, after fees):*")
            for rec in recs:
                dot = "🟢" if rec["green"] else "🧪"
                lines.append(
                    f"{dot} `{rec['tier']}` — {rec['n']} closed · "
                    f"win {rec['win_pct']:.0f}% · net {rec['net_r']:+.1f}R "
                    f"· {rec['open']} open")
            try:
                _lst = live_executor.status()
                if _lst.get("enabled"):
                    _lmode = ("🛑 HALTED" if _lst.get("halted") else
                              ("LIVE" if _lst.get("ready")
                               else "waiting for keys"))
                    lines.append(
                        f"💸 live: {_lmode} · bal ${_lst['balance']:,.2f}"
                        f" · {_lst['open']} open · {_lst['closed']} closed")
            except Exception:
                pass
            if _event_line:
                lines.append(_event_line)
            if _mood_line:
                lines.append(_mood_line)
            lines.append(f"regime: {regime}")
            ok, _dmsg = tg.send("\n".join(lines))
            print(f"  digest sent={ok}" + ("" if ok else f" ({_dmsg})"),
                  flush=True)
            n_alerts += 1 if ok else 0
    except Exception:
        pass

    # 🌆 EVENING REPORT — pre-US-session day-trade briefing (user
    # 2026-07-08). Default 13:00 UTC = 18:00 Pakistan (US opens ~18:30
    # PKT); override with WORKER_EVENING_HOUR_UTC. Day-trade lanes first.
    try:
        _eh_utc = int(getattr(config, "WORKER_EVENING_HOUR_UTC", 13))
        _hr_now2 = datetime.now(timezone.utc).hour
        if (_eh_utc <= _hr_now2 < _eh_utc + 3
                and store.should_alert("evening_digest", 20 * 3600)):
            lines = ["🌆 *EVENING REPORT* — US session ahead, "
                     "the next 24 hours"]
            lines += _brief24()
            _picks = []
            for p in best[:3]:
                _picks.append(("💎 BEST ZONE", p))
            for p in em_big[:2]:
                _picks.append(("🚀 EARLY-LANE (81% cell)", p))
            _pk_syms = {p.get("symbol") for _, p in _picks}
            for p in r.get("early_strong", []):
                if p.get("symbol") not in _pk_syms and len(_picks) < 4:
                    _picks.append(("⚡ EARLY MOVERS", p))
            for p in apex[:2]:
                _picks.append(("🏆 APEX", p))
            for p in elite_early[:1]:
                _picks.append(("🌟 EARLY ELITE", p))
            _seen_pk2: set = set()
            _picks = [(_l, _p) for _l, _p in _picks
                      if not (_p.get("symbol") in _seen_pk2
                              or _seen_pk2.add(_p.get("symbol")))][:5]
            if _picks:
                lines.append("*Best setups for the session:*")
                for _lbl, p in _picks:
                    lines.append(
                        f"• {_lbl} — *{p['base']} {p['side']}* · entry "
                        f"`{p['entry']:g}` · SL `{p['stop']:g}` · TP1 "
                        f"`{p['tp1']:g}`")
            else:
                lines.append("_No qualifying setups into the US session — "
                             "sit tight._")
            try:
                _lst = live_executor.status()
                if _lst.get("enabled"):
                    _lmode = ("🛑 HALTED" if _lst.get("halted") else
                              ("LIVE" if _lst.get("ready")
                               else "waiting for keys"))
                    lines.append(
                        f"💸 live: {_lmode} · bal ${_lst['balance']:,.2f}"
                        f" · {_lst['open']} open · {_lst['closed']} closed")
            except Exception:
                pass
            if _event_line:
                lines.append(_event_line)
            if _mood_line:
                lines.append(_mood_line)
            lines.append(f"regime: {regime}")
            ok, _dmsg = tg.send("\n".join(lines))
            print(f"  digest sent={ok}" + ("" if ok else f" ({_dmsg})"),
                  flush=True)
            n_alerts += 1 if ok else 0
    except Exception:
        pass

    # 🔴 INVERSE RISK — the red signal (user 2026-08-29 final word:
    # "red mark remove and replace with inverse risk caution"). The
    # stop-break IT'S GONE buzz is REMOVED — the exchange stop is the
    # exit and needs no announcement. Red now means: momentum died
    # and the trade is turning inverse (underwater + 1h closed back
    # through ema20 + 15m trending against). One-shot per entry,
    # caution framing — measured (backtest_greenred): exiting on this
    # signature lost money vs holding, so the SL stays the exit per
    # let-it-ride. 🏦 TP1 bank buzz rides the same watch.
    try:
        _rg_watch = []
        for _rg_stream in ("elite_confirm", "personal_watch",
                           "personal_watch_early", "conviction_v2"):
            try:
                _rg_watch += [(r, _rg_stream) for r in
                              store.recent_by_stream(_rg_stream, 8)]
            except Exception:
                pass
        _rg_now = time.time()
        for _rg, _rg_src in _rg_watch:
            _rg_ts = float(_rg.get("ts") or 0)
            if not _rg_ts or _rg_now - _rg_ts > 48 * 3600:
                continue
            _rg_sym = _rg.get("symbol")
            _rg_side = (_rg.get("side") or "").upper()
            _rg_ent = float(_rg.get("entry") or 0)
            _rg_stp = float(_rg.get("stop") or 0)
            _rg_tp1 = float(_rg.get("tp1") or 0)
            if not (_rg_sym and _rg_ent > 0 and _rg_stp > 0):
                continue
            _rg_px = float(
                binance_client.get_ticker_price(_rg_sym) or 0)
            if _rg_px <= 0:
                continue
            _rg_long = _rg_side == "LONG"
            # walk the 1h candles since the buzz — which came first,
            # TP1 or the stop? (also catches a TP1 spike between
            # worker polls)
            _rg_banked = False
            _rg_stopped = False
            try:
                _rgd = binance_client.get_klines(_rg_sym, "1h",
                                                 limit=60)
                _rg_hi = _rgd["high"].to_numpy()
                _rg_lo = _rgd["low"].to_numpy()
                _rg_idx = _rgd.index
                for _ri in range(len(_rgd)):
                    if _rg_idx[_ri].timestamp() < _rg_ts:
                        continue
                    _hit_stop = (_rg_lo[_ri] <= _rg_stp) if _rg_long \
                        else (_rg_hi[_ri] >= _rg_stp)
                    _hit_tp = (_rg_tp1 > 0 and
                               ((_rg_hi[_ri] >= _rg_tp1) if _rg_long
                                else (_rg_lo[_ri] <= _rg_tp1)))
                    if _hit_stop:
                        _rg_stopped = True
                        break
                    if _hit_tp:
                        _rg_banked = True
                        break
            except Exception:
                pass
            if _rg_banked:
                # 🏦 TP1 buzz — the plan banks 100% here.
                if store.should_alert(
                        f"tp1hit:{_rg_sym}:{_rg_side}:{int(_rg_ts)}",
                        7 * 24 * 3600):
                    _rg_b2 = _rg.get("base") or \
                        _rg_sym.replace("USDT", "")
                    ok, _ = tg.send(
                        f"🏦 *{_rg_b2} {_rg_side} — TP1 HIT* "
                        f"`{_rg_tp1:g}` — BANK 100% HERE (the plan). "
                        f"Re-enter only on a fresh 🟢 confirm or "
                        f"re-fire.")
                    n_alerts += 1 if ok else 0
                continue
            if _rg_stopped:
                continue    # stop did its job — silent by user rule
            # 🔴 INVERSE RISK — the red signal: momentum died, trade
            # turning inverse. One-shot per entry, caution framing.
            _rg_uw = (_rg_px < _rg_ent) if _rg_long \
                else (_rg_px > _rg_ent)
            if not _rg_uw:
                continue
            try:
                _rd1 = binance_client.get_klines(_rg_sym, "1h",
                                                 limit=30)
                _rc1 = _rd1["close"].to_numpy()
                _re1 = (_rd1["close"]
                        .ewm(span=20, adjust=False)
                        .mean().to_numpy())
                _lost = ((_rc1[-2] < _re1[-2]) if _rg_long
                         else (_rc1[-2] > _re1[-2]))
                if not _lost:
                    continue
                _rd15 = binance_client.get_klines(_rg_sym, "15m",
                                                  limit=120)
                _rt15, _rtd15, _ = _et_w.detect(_rd15)
                _agn = "SHORT" if _rg_long else "LONG"
                if not (_rt15 >= 65 and _rtd15 == _agn):
                    continue
                if not store.should_alert(
                        f"momdied:{_rg_sym}:{_rg_side}:"
                        f"{int(_rg_ts)}", 7 * 24 * 3600):
                    continue
                _rg_b3 = _rg.get("base") or \
                    _rg_sym.replace("USDT", "")
                ok, _ = tg.send(
                    f"🔴 *{_rg_b3} {_rg_side} — INVERSE RISK: the "
                    f"momentum has died.* Live `{_rg_px:g}` under "
                    f"the entry `{_rg_ent:g}`, the 1h closed back "
                    f"through its ema20 and the 15m trends "
                    f"{_agn.lower()} ({_rt15:.0f}).\n"
                    f"_The wind changed — your call on the early "
                    f"door. Measured honesty: cutting on this "
                    f"signature lost money vs holding; the plan "
                    f"rides to SL `{_rg_stp:g}`._")
                n_alerts += 1 if ok else 0
            except Exception:
                pass
    except Exception as _rg_exc:
        print("  🔴 red-exit error:", _rg_exc, flush=True)

    # 👁 PERSONAL WATCH (user 2026-08-29): round-the-clock eye on a
    # hand-picked list (config.PERSONAL_WATCH — ZEC, INJ, VIRTUAL).
    # One job: buzz the phone the moment a 1h pullback-confirmation
    # candle prints — the exact ENA shape the user asked to reproduce
    # (green close above prev close + ema20 on 1.2x volume), and only
    # after a real dip so there is actually a pullback to be over.
    # Additive stream — touches nothing else. 6h cooldown per coin.
    for _pw_sym in list(getattr(config, "PERSONAL_WATCH", [])):
        try:
            _pwd = binance_client.get_klines(_pw_sym, "1h", limit=160)
            if _pwd is None or len(_pwd) < 30:
                continue
            _pc = _pwd["close"].to_numpy()
            _po = _pwd["open"].to_numpy()
            _pv = _pwd["volume"].to_numpy()
            _pe = (_pwd["close"].ewm(span=20, adjust=False)
                   .mean().to_numpy())
            _pvma = float(_pv[-21:-1].mean())
            # confirm candle = last CLOSED 1h bar
            _pw_conf = (_pc[-2] > _po[-2] and _pc[-2] > _pc[-3]
                        and _pc[-2] > _pe[-2] and _pvma > 0
                        and _pv[-2] > 1.2 * _pvma)
            # ...resolving a real dip: 2+ of the 5 bars before it
            # closed red or under ema20 (no dip → nothing to confirm)
            _pw_dip = sum(
                1 for _pi in range(-7, -2)
                if _pc[_pi] < _po[_pi] or _pc[_pi] < _pe[_pi]) >= 2
            if not _pw_dip:
                continue
            _pw_px = float(_pc[-1]) if _pc[-1] > 0 else float(_pc[-2])
            _pwh = _pwd["high"].to_numpy()
            _pwl = _pwd["low"].to_numpy()
            _pw_atr = float((_pwh[-15:-1] - _pwl[-15:-1]).mean())
            # 🛡️ the ELITE structural stop, verbatim (user 2026-08-29:
            # "sl should be also based on strength like we have for
            # elite convictions — its soo good"): same smart_stop
            # engine the elite cards use (validated GIGGLE fix —
            # swing low − 0.25×true-range-ATR, 4×ATR cap, plan-stop
            # fallback). Structure decides the stop and it breathes
            # with volatility on its own; widening beyond structure
            # measured flat-or-worse (backtest_stops).
            _pw_plan = _pw_px - 1.5 * _pw_atr
            _pw_sl = float(_ss_w.structural_stop(
                _pwd, "LONG", _pw_px, _pw_plan,
                _pw_px + (_pw_px - _pw_plan)))
            _pw_r = _pw_px - _pw_sl
            _pw_base = _pw_sym.replace("USDT", "")
            # 🎯 BENCHMARK TP, strength-scaled (user 2026-08-29:
            # "TP should be according to the benchmark and race to
            # it... according to its strength" — VALIDATED same day,
            # backtest_bench on 245 confirmed entries: level-anchored
            # targets beat both 1:1 and the x1.25 stretch — bench
            # 61.2%/+0.037R, bench+strength +0.041R best-in-test,
            # green both halves; plain x1.25 was RED in the older
            # half here and is out). Target = the 24h-high benchmark,
            # clipped by strength: STRONG (hot ATR top-40% or 1h
            # burst >= 65 long) -> [1.0R, 2.5R]; quiet -> [0.75R,
            # 1.25R]. Blind ratio stretches beyond structure stay
            # banned (2R cell 22% win).
            _pw_strong = False
            _pw_tell = ""
            try:
                _tr9 = _pwh - _pwl
                _atr_now = float(_tr9[-15:-1].mean())
                _hist9 = [float(_tr9[j - 14:j].mean())
                          for j in range(max(15, len(_tr9) - 100),
                                         len(_tr9))]
                _hot9 = (len(_hist9) >= 30 and
                         sum(1 for x in _hist9 if x < _atr_now)
                         / len(_hist9) >= 0.6)
                _bs9, _bd9, _ = _vb_w.lane_velocity_burst(_pwd)
                _brst9 = (_bs9 >= 65
                          and (_bd9 or "").upper() == "LONG")
                _pw_strong = _hot9 or _brst9
                if _pw_strong:
                    _pw_tell = " + ".join(
                        [t for t, on in (("HOT ATR", _hot9),
                                         (f"burst {_bs9:.0f}",
                                          _brst9)) if on])
            except Exception:
                pass
            # 🎯 CONFIDENCE on the personal watch (user 2026-08-31,
            # VALIDATED same day on 197 resolved confirms). Computed
            # from candles via _conf_votes so it works on any coin.
            _pw_cf = _conf_votes(_pwd, "LONG")
            # 🌡🤝 conf-rebuild chips on the watch (user 2026-09-05:
            # "have the confidence score on them because in this way
            # we can measure") — heat stamps into the desk records so
            # the heat-band panel judges it; cluster shows which elite
            # streams agree with your coin right now. Fail-soft.
            try:
                _pw_heat = _atr_heat(_pwd)
            except Exception:
                _pw_heat = None
            _pw_chip = (f" · 🌡 heat {_pw_heat}"
                        if _pw_heat is not None else "")
            try:
                _pw_cl = store.live_cluster(_pw_sym, "LONG")
                if _pw_cl:
                    _pw_chip += (" · 🤝 with "
                                 + "+".join(t.replace("_", " ")
                                            for t in _pw_cl[:3]))
            except Exception:
                pass
            _pw_bench = float(_pwh[-25:-1].max())
            _pw_br = (_pw_bench - _pw_px) / _pw_r if _pw_r > 0 else 0
            _lo9, _hi9 = (1.0, 2.5) if _pw_strong else (0.75, 1.25)
            _pw_clip = min(max(_pw_br, _lo9), _hi9) \
                if _pw_br > 0 else _lo9
            _pw_tp1 = _pw_px + _pw_clip * _pw_r
            _pw_tp2 = _pw_px + max(2.0, _pw_clip + 0.5) * _pw_r
            _pw_why = (f"🎯 racing the benchmark `{_pw_bench:g}` "
                       f"(24h high) → TP1 at {_pw_clip:.2f}R · "
                       + (f"💪 STRONG ({_pw_tell})" if _pw_strong
                          else "quiet confirm — tight race"))
            # ⚡ EARLY lane (user 2026-08-29: "on the go... instead of
            # waiting 1h"): fire when the turn is already MOVING —
            # price reclaims the 1h ema20 intra-candle while the 15m
            # trend AND burst are both LONG. Honest framing baked into
            # the buzz: early entries measured ~49% vs 67.8% for the
            # confirmed shape, so this is the smaller-size heads-up
            # and 🟢 CONFIRMED stays the green light.
            if not _pw_conf and _pw_px > float(_pe[-1]):
                try:
                    _pw15 = binance_client.get_klines(
                        _pw_sym, "15m", limit=120)
                    _ts15, _td15, _ = _et_w.detect(_pw15)
                    _bs15, _bd15, _ = _vb_w.lane_velocity_burst(_pw15)
                    if (_ts15 >= 55 and _td15 == "LONG"
                            and _bs15 >= 65
                            and (_bd15 or "").upper() == "LONG"
                            and store.should_alert(
                                f"pwatch_early:{_pw_sym}", 6 * 3600)):
                        ok, _pw_err = tg.send(
                            f"⚡ *{_pw_base} WAKING NOW* — moving "
                            f"before the 1h confirm.\n"
                            f"15m trend {_ts15:.0f} LONG · burst "
                            f"{_bs15:.0f} LONG · price back above the "
                            f"1h ema20\n"
                            f"💰 entry `{_pw_px:g}` · SL `{_pw_sl:g}` "
                            f"({(_pw_sl / _pw_px - 1) * 100:+.1f}%) · "
                            f"TP1 `{_pw_tp1:g}` "
                            f"(+{(_pw_tp1 / _pw_px - 1) * 100:.1f}%) "
                            f"· TP2 `{_pw_tp2:g}`\n"
                            f"{_pw_why}\n"
                            f"🎯 conf {_pw_cf}/100"
                            f"{' 💪 EDGE ZONE' if (_pw_cf or 0) >= 65 else ' — below the 65 line'}"
                            f"{_pw_chip}\n"
                            f"⚠️ early read — smaller size; 🟢 the 1h "
                            f"confirm candle is still the green light\n"
                            f"👁 personal watch")
                        n_alerts += 1 if ok else 0
                        if not ok:
                            print("  👁 tg:", _pw_err, flush=True)
                        _pw_sig_e = {
                            "symbol": _pw_sym, "base": _pw_base,
                            "side": "LONG", "entry": _pw_px,
                            "stop": _pw_sl, "tp1": _pw_tp1,
                            "tp2": _pw_tp2,
                            "tp_r": round(float(_pw_clip), 2),
                            "conf": _pw_cf,
                            "heat": _pw_heat,
                            "t15": round(float(_ts15)),
                            "b15": round(float(_bs15))}
                        store.record_signal("personal_watch_early",
                                            _pw_sig_e)
                        # 🧪 desk tier (user 2026-08-31: "have this on
                        # decision desk as well on paper trading") —
                        # the ⚡ early lane now builds its own live
                        # record, carrying its EDGE-conf so the
                        # confidence panel can price that dimension
                        # too. Records only; the buzz is unchanged.
                        shadow_trader.open_from_signal(
                            "personal_watch_early", _pw_sig_e, _pw_px)
                        # 🎮 GEN 8 P3 feed (user 2026-09-05: "and the
                        # waking on our coins"): every ⚡ waking buzz
                        # is a demo candidate.
                        _DEMO_WAKE.append(
                            {"symbol": _pw_sym, "base": _pw_base,
                             "side": "LONG", "entry": _pw_px,
                             "stop": _pw_sl, "tp1": _pw_tp1,
                             "tp2": _pw_tp2,
                             "score": float(_pw_cf or 55),
                             "src": "pw_waking",
                             "fired_at": time.time()})
                        del _DEMO_WAKE[:-20]
                except Exception as _pw_exc:
                    print(f"  👁 early {_pw_sym}: {_pw_exc}",
                          flush=True)
            if not _pw_conf:
                continue
            # 🎯 CONF GATE at 65 (user 2026-08-31: "ship it with the
            # gate at 65") — VALIDATED same day on 197 resolved
            # confirms: conf>=65 63.9% / +0.241R, GREEN BOTH HALVES
            # (older +0.119, recent +0.331); conf<65 50.7% /
            # -0.035R (older +0.004, recent -0.067 — flat-to-red).
            # Sub-65 confirms stay silent. Revert: delete this block.
            if _pw_cf is not None and _pw_cf < 65:
                print(f"  👁 {_pw_sym} confirm muted — conf "
                      f"{_pw_cf} < 65", flush=True)
                continue
            if not store.should_alert(f"pwatch:{_pw_sym}", 6 * 3600):
                continue
            _pw_vx = _pv[-2] / _pvma if _pvma > 0 else 0.0
            ok, _pw_err = tg.send(
                f"🟢 *{_pw_base} JUST CONFIRMED* — the pullback is "
                f"over.\n"
                f"1h confirmation candle: green · above ema20 · "
                f"vol {_pw_vx:.1f}x\n"
                f"💰 `{_pw_px:g}` · SL `{_pw_sl:g}` "
                f"({(_pw_sl / _pw_px - 1) * 100:+.1f}%) · TP1 "
                f"`{_pw_tp1:g}` (+{(_pw_tp1 / _pw_px - 1) * 100:.1f}%) "
                f"· TP2 `{_pw_tp2:g}`\n"
                f"{_pw_why}\n"
                f"🎯 conf {_pw_cf}/100{_pw_chip}\n"
                f"👁 personal watch")
            n_alerts += 1 if ok else 0
            if not ok:
                print("  👁 tg:", _pw_err, flush=True)
            _pw_sig = {
                "symbol": _pw_sym, "base": _pw_base, "side": "LONG",
                "entry": _pw_px, "stop": _pw_sl,
                "tp1": _pw_tp1, "tp2": _pw_tp2,
                "tp_r": round(float(_pw_clip), 2),
                "conf": _pw_cf,
                "heat": _pw_heat,
                "vol_x": round(float(_pw_vx), 2)}
            store.record_signal("personal_watch", _pw_sig)
            # 🧪 desk tier (user 2026-08-31): the 🟢 confirm builds
            # its own live record on the Decision Desk, carrying its
            # EDGE-conf. This is the stream whose backtest says
            # 63.9%/+0.241R at conf>=65 — now it gets to prove that
            # forward with real forward prices. Records only.
            shadow_trader.open_from_signal("personal_watch",
                                           _pw_sig, _pw_px)
        except Exception as _pw_exc:
            print(f"  👁 watch {_pw_sym}: {_pw_exc}", flush=True)

    store.record_cycle(regime, len(sst1), len(takenow), n_alerts)
    print(f"[{stamp}] regime={regime} · 🌊TREND={len(r.get('trend', []))} · "
          f"APEX={len(apex)} · EARLY_ELITE={len(elite_early)} · "
          f"TN_HOT={len(tn_hot)} · EM🚀={len(em_big)} · "
          f"SST1≥{MIN_CONV:.0f}={len(sst1)}(stored) · "
          f"alerts_sent={n_alerts} · "
          f"shadow +{n_shadow_open}/-{n_shadow_closed}", flush=True)


def main() -> None:
    tg_status = ("ON" if tg.enabled()
                 else "OFF — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")
    print("=" * 64)
    print("  24/7 SIGNAL WORKER — alert-only")
    print(f"  interval={INTERVAL // 60}min · cooldown={COOLDOWN // 60}min · "
          f"SST1 min conv={MIN_CONV:.0f}")
    print(f"  Telegram: {tg_status}")
    print(f"  DB: {store.stats().get('db')}")
    print("=" * 64, flush=True)
    if tg.enabled():
        tg.send("🟢 *24/7 worker online* — watching for ✅🔥 TAKE NOW HOT and "
                "💠 SST1 conv≥70. I ping you only for the best.", silent=True)
    while True:
        try:
            cycle()
        except Exception as exc:
            print("cycle error:", exc, flush=True)
            traceback.print_exc()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

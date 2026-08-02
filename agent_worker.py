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
import time
import traceback
from datetime import datetime, timezone

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import best_board
import binance_client
import config
import fast_confirm
import ignition
import kronos_forecast as kf
import liq_flush
import live_executor
import lunarcrush
import one_trade
import polymarket_events
import true_signal
import scan_core
import shadow_trader
import surge_radar
import telegram_notify as tg
import worker_store as store

INTERVAL = max(1, int(getattr(config, "WORKER_INTERVAL_MIN", 5))) * 60
# 🔮 per-symbol Kronos forecast cache — the worker process is long-lived
# so this persists across cycles. 24h-horizon forecasts move slowly;
# 2h TTL + a per-cycle cap keeps CPU/RAM bounded on the deploy.
_KR_CACHE: dict = {}
KR_TTL = 2 * 3600
KR_MAX_PER_CYCLE = 8
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
    """🔮 verdict line for alert messages, from the worker's forecast
    cache (user 2026-08-03: 'kronos should run on early elite too' —
    the best-minting stream shows the top layer's read in the buzz)."""
    try:
        _hit = _KR_CACHE.get(p.get("symbol"))
        if not _hit or time.time() - _hit["t"] > KR_TTL:
            return ""
        s = _hit["s"]
        d = s.get("direction")
        if d not in ("UP", "DOWN"):
            return ""
        agree = ((d == "UP" and p.get("side") == "LONG")
                 or (d == "DOWN" and p.get("side") == "SHORT"))
        return (f"\n🔮 kronos {d} "
                f"{float(s.get('exp_move_pct') or 0):+.1f}%/24h — "
                f"{'AGREES (validated +0.34R edge)' if agree else 'CONFLICTS — caution'}")
    except Exception:
        return ""


def _fmt_elite_early(p) -> str:
    return (f"🌟 *EARLY ELITE* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · {p.get('lanes', 0)} lanes)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}{_kr_note(p)}\n"
            f"_ELITE MAX/HIGH + 2+ lanes + TAKE NOW 🔥 HOT — early "
            f"high-conviction entry_")


def _fmt_fresh(p) -> str:
    return (f"🌱 *FRESH MOVER* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_first signal in 72h + TAKE NOW 🔥 HOT — validated 74% · "
            f"1.5R_")


def cycle() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    r = scan_core.scan_all(scan_n=60, min_conv=MIN_CONV)
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
    for p in apex:
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
                if p.get("_conf") is not None and "\n" in _msg:
                    _msg = _msg.replace(
                        "\n", f" · 🎯 conf {p['_conf']}/100\n", 1)
                ok, msg = tg.send(_msg)
                n_alerts += 1 if ok else 0
                if not ok:
                    print("  tg:", msg, flush=True)

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
    # chasing). 🌊 TREND RIDER stays removed (2026-07-13). The lean
    # proven-only gating stays shelved until the keyword
    # "Lets deploy The new system".
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
    _push([p for p in _ign if _in_zone(p)], "ignition", _fmt_ignition,
          min_conf=0)
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
    _push([p for p in _f30 if _in_zone(p)], "fast30", _fmt_fast30,
          min_conf=0)
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
    # 📡 buzzes DISABLED pending backtest verdict (user 2026-07-26:
    # "don't deploy first, test") — desk tier keeps proving silently.
    # Re-enable by restoring the _push line below once validated.
    # _push([p for p in _srg if _in_zone(p)], "surge", _fmt_surge,
    #       min_conf=0)
    _push([p for p in best if _in_zone(p)], "best", _fmt_best,
          tier="best_board")
    _push(apex, "apex", _fmt_apex, min_conf=0, tier="apex")
    _push(elite_early, "elite_early", _fmt_elite_early, min_conf=0,
          tier="elite_early")
    _push(fresh_m, "fresh", _fmt_fresh, min_conf=0, tier="fresh")
    _push(tn_rest, "takenow", _fmt_takenow, min_conf=0,
          tier="takenow_hot")
    _push([p for p in em_big if _in_zone(p)], "em", _fmt_prime,
          min_conf=0, tier="early_lane")
    _em_rest = [p for p in r.get("early_strong", [])
                if not p.get("early_lanes")]
    _push([p for p in _em_rest if _in_zone(p)], "emrest",
          _fmt_early_rest, min_conf=0, tier="early_movers")

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
        _push([_one], "one", _fmt_one, min_conf=0)

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
                    + list(em_big)):
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

    # 🔮 KRONOS APPROVED desk tier (user 2026-08-03: "can the 86% be
    # treated separately?") — every elite-stream signal where Kronos
    # agrees, REGARDLESS of the other 🎯 gates. The live forward
    # record of the backtest's agree bucket (86%/+0.34R, n=36) at its
    # natural breadth. Desk-only: no buzz, no votes.
    _kr_appr = []
    if _kr_ok:
        _ka_seen: set = set()
        for _kp in (list(apex) + list(elite_early) + list(tn_hot)):
            _kk = (_kp.get("symbol"), _kp.get("side"))
            if _kk in _ka_seen or not _kk[0]:
                continue
            _ka_seen.add(_kk)
            _kv2 = _kr_get(_kk[0], _kk[1])
            if not _kv2:
                continue
            if ((_kv2.get("direction") == "UP" and _kk[1] == "LONG")
                    or (_kv2.get("direction") == "DOWN"
                        and _kk[1] == "SHORT")):
                _kp2 = dict(_kp)
                _kp2["kr_dir"] = _kv2.get("direction")
                _kp2["kr_exp"] = _kv2.get("exp_move_pct")
                _kr_appr.append(_kp2)
        for p in _kr_appr:
            store.record_signal("kr_approved", p)

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
    _push(_ts_rows, "ts", _fmt_ts, min_conf=0)
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
            _pb = _pb_mod.scan(
                binance_client.get_top_symbols(40)["symbol"].tolist(),
                _kr_pb, max_checks=30)
        except Exception as _pb_exc:
            _pb = []
            print("  preburst error:", _pb_exc, flush=True)
        for p in _pb:
            store.record_signal("preburst", p)
        _push(list(_pb), "preburst", _fmt_preburst, min_conf=0)

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
        # 🩸 LIQ FLUSH RETIRED (2026-07-28, its own pre-registered rule:
        # still negative past ~50 closed — final record -22.6R/110).
        # Signals stay recorded above for the archive; the desk stops
        # taking them. Re-add here only if a NEW validation earns it.
        _tiers = (("top_conviction", _topc),
                  ("best_board", best),
                  ("apex", apex), ("takenow_hot", tn_hot),
                  ("elite_early", elite_early),
                  ("fresh", fresh_m), ("early_movers",
                                       r.get("early_strong", [])),
                  ("early_lane", em_big),
                  ("ignition", _ign),
                  ("fast30", _f30),
                  ("surge", _srg),
                  ("one_trade", [_one] if _one else []),
                  ("true_signal", _ts_rows),
                  ("preburst", _pb),
                  ("kr_approved", _kr_appr),
                  ("trend_rider", r.get("trend", [])))
        for _tname, _sigs in _tiers:
            for p in _sigs:
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

    # 📊🌅 DAILY MORNING REPORT — desk status + the 4-5 best qualifying
    # setups of the morning (user 2026-07-08). Default 04:00 UTC = 09:00
    # Pakistan; override with WORKER_DIGEST_HOUR_UTC.
    try:
        _dh_utc = int(getattr(config, "WORKER_DIGEST_HOUR_UTC", 4))
        _hr_now = datetime.now(timezone.utc).hour
        if (_dh_utc <= _hr_now < _dh_utc + 3
                and store.should_alert("daily_digest", 20 * 3600)):
            recs = shadow_trader.tier_records()
            lines = ["🌅 *MORNING REPORT*"]
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
            lines = ["🌆 *EVENING REPORT* — US session ahead"]
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

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

import binance_client
import config
import lunarcrush
import polymarket_events
import scan_core
import shadow_trader
import telegram_notify as tg
import worker_store as store

INTERVAL = max(1, int(getattr(config, "WORKER_INTERVAL_MIN", 5))) * 60
COOLDOWN = max(1, int(getattr(config, "WORKER_ALERT_COOLDOWN_MIN", 360))) * 60
MIN_CONV = float(getattr(config, "WORKER_SST1_MIN_CONV", 70))
LB_MIN = float(getattr(config, "WORKER_LEADERBOARD_MIN_SCORE", 85))


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


def _fmt_apex(p) -> str:
    edges = " · ".join(p.get("edges", []))
    return (f"🏆🔥 *APEX ×{p.get('apex', 0)}* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f})\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_best of the best — {edges} all agree_")


def _fmt_elite_early(p) -> str:
    return (f"🌟 *EARLY ELITE* — {p['base']} {p['side']} "
            f"({p['tier']} {p['score']:.0f} · {p.get('lanes', 0)} lanes)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` · "
            f"TP1 `{p['tp1']:g}`{_tp2(p)}\n"
            f"_ELITE MAX/HIGH + 2+ lanes + TAKE NOW 🔥 HOT — early "
            f"high-conviction entry_")


def _fmt_trend(p) -> str:
    return (f"🌊 *TREND RIDER* — {p['base']} LONG "
            f"(breakout +{p['score']:.1f}%)\n"
            f"entry `{p['entry']:g}` · SL `{p['stop']:g}` (2.5×ATR-d) · "
            f"ride the trail\n"
            f"_the validated money core: 3yr +0.15-0.32R/trade after fees, "
            f"hold days-to-weeks, winners 2.6× losers_")


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

    def _push(items, key_prefix, fmt):
        nonlocal n_alerts
        for p in items:
            if store.should_alert(f"{key_prefix}:{p['symbol']}:{p['side']}",
                                  COOLDOWN):
                ok, msg = tg.send(fmt(p))
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
    # Alert policy (user 2026-07-08): keep the existing five streams AS IS,
    # ADD 🌊 TREND RIDER + reports. The lean proven-only gating is shelved
    # until the keyword "Lets deploy The new system".
    _push(r.get("trend", []), "trend", _fmt_trend)
    _push(apex, "apex", _fmt_apex)
    _push(elite_early, "elite_early", _fmt_elite_early)
    _push(fresh_m, "fresh", _fmt_fresh)
    _push(tn_rest, "takenow", _fmt_takenow)
    # ⭐ PRIME ENTRIES (user 2026-07-11): the early-lane stream, pushed only
    # while still 🟢 IN ZONE (<=25% toward TP1) and alive at push time —
    # mirrors the ⭐ PRIME board. Late/dead ones stay board-only, no buzz.
    _prime = []
    for p in em_big:
        try:
            _lv = binance_client.get_ticker_price(p["symbol"])
            _e, _t1 = float(p["entry"]), float(p["tp1"])
            _st = float(p["stop"])
            if not _lv or _t1 == _e:
                raise ValueError
            _f = ((_lv - _e) / (_t1 - _e) if p["side"] == "LONG"
                  else (_e - _lv) / (_e - _t1))
            _dd = _lv <= _st if p["side"] == "LONG" else _lv >= _st
            if not _dd and _f <= 0.25:
                p["_prog"] = _f
                _prime.append(p)
        except Exception:
            _prime.append(p)   # price hiccup — alert fires at birth anyway
    _push(_prime, "em", _fmt_prime)
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
        _tiers = (("apex", apex), ("takenow_hot", tn_hot),
                  ("elite_early", elite_early),
                  ("fresh", fresh_m), ("early_movers",
                                       r.get("early_strong", [])),
                  ("early_lane", em_big),
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

    # 🟡🔴 TREND HEALTH pings (user: "caution if the money bet stops
    # surviving"). 🔴 = a trend shadow trade just closed (trail/stop hit).
    # 🟡 = an open trend trade is losing AND within 25% of its stop.
    try:
        for t in _sh_closed:
            if t.get("tier") != "trend_rider":
                continue
            _pr = float(t.get("pnl_r") or 0)
            ok, _ = tg.send(
                f"🔴 *TREND EXIT* — {t['symbol'].replace('USDT','')} closed "
                f"({t.get('reason')}) at `{t.get('exit'):g}` · "
                f"{_pr:+.2f}R after fees. The trail decided — as designed.")
            n_alerts += 1 if ok else 0
    except Exception:
        pass
    try:
        for t in store.shadow_open_trades():
            if t["tier"] != "trend_rider":
                continue
            px = _pxs.get(t["symbol"])
            if not px:
                continue
            entry, stop0 = float(t["entry"]), float(t["stop0"])
            rng = entry - stop0
            if rng > 0 and px < entry and (px - stop0) / rng < 0.25:
                if store.should_alert(f"tr_caution:{t['symbol']}",
                                      12 * 3600):
                    ok, _ = tg.send(
                        f"🟡 *TREND CAUTION* — {t['symbol'].replace('USDT','')} "
                        f"LONG is {((px/entry)-1)*100:+.1f}% and near its "
                        f"stop `{stop0:g}`. Plan says: let the stop decide "
                        f"— no adds.")
                    n_alerts += 1 if ok else 0
    except Exception:
        pass

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
            for p in r.get("trend", [])[:3]:
                _picks.append(("🌊 TREND (money core)", p))
            for p in em_big[:2]:
                _picks.append(("🚀 EARLY-LANE (81% cell)", p))
            for p in apex[:2]:
                _picks.append(("🏆 APEX", p))
            for p in elite_early[:2]:
                _picks.append(("🌟 EARLY ELITE", p))
            _picks = _picks[:5]
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
            _opn = [t for t in store.shadow_open_trades()
                    if t["tier"] == "trend_rider"]
            if _opn:
                lines.append("🌊 open trend rides: " + ", ".join(
                    t["symbol"].replace("USDT", "") for t in _opn))
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
            for p in em_big[:2]:
                _picks.append(("🚀 EARLY-LANE (81% cell)", p))
            _pk_syms = {p.get("symbol") for _, p in _picks}
            for p in r.get("early_strong", []):
                if p.get("symbol") not in _pk_syms and len(_picks) < 3:
                    _picks.append(("⚡ EARLY MOVERS", p))
            for p in apex[:2]:
                _picks.append(("🏆 APEX", p))
            for p in elite_early[:1]:
                _picks.append(("🌟 EARLY ELITE", p))
            for p in r.get("trend", [])[:1]:
                _picks.append(("🌊 TREND (money core)", p))
            _picks = _picks[:5]
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
            _opn = [t for t in store.shadow_open_trades()
                    if t["tier"] == "trend_rider"]
            if _opn:
                lines.append("🌊 open trend rides: " + ", ".join(
                    t["symbol"].replace("USDT", "") for t in _opn))
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

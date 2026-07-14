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
import live_executor
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
    _best_keys = {(p.get("symbol"), p.get("side")) for p in best}

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

    def _not_best(items):
        return [p for p in items
                if (p.get("symbol"), p.get("side")) not in _best_keys]

    # Alert policy (user 2026-07-08 + 2026-07-11): one buzz per setup,
    # richest label wins — 💎 BEST first, then the locked streams for
    # whatever didn't make the zone. The lean proven-only gating stays
    # shelved until the keyword "Lets deploy The new system".
    # 🌊 TREND RIDER pushes removed entirely (user 2026-07-13) — board +
    # desk shadow record continue silently; a trend-sourced 💎 pick can
    # still buzz as BEST (that's the validated spot-driven cell voting).
    _push([p for p in best if _in_zone(p)], "best", _fmt_best)
    _push(_not_best(apex), "apex", _fmt_apex)
    _push(_not_best(elite_early), "elite_early", _fmt_elite_early)
    _push(_not_best(fresh_m), "fresh", _fmt_fresh)
    _push(_not_best(tn_rest), "takenow", _fmt_takenow)
    # ⭐ PRIME (2026-07-11): early-lane stream, in-zone only — covers any
    # early-lane pick that fell off the 💎 top list.
    _push([p for p in _not_best(em_big) if _in_zone(p)], "em", _fmt_prime)
    # ⚡ EARLY MOVERS full stream (user 2026-07-13: "notify me for early
    # movers!"): the plain STRONG+HOT rest was board-only since
    # 2026-07-05 — now that it's a 🟢 green tier the live executor
    # trades, every fire buzzes too. In-zone gated, richest label wins.
    _em_rest = [p for p in _not_best(r.get("early_strong", []))
                if not p.get("early_lanes")]
    _push([p for p in _em_rest if _in_zone(p)], "emrest", _fmt_early_rest)
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
        _tiers = (("best_board", best),
                  ("apex", apex), ("takenow_hot", tn_hot),
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

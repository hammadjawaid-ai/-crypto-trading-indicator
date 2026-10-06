"""⭐⚡ GO REVIVED board on the Paper Trader page (user 2026-10-06: "build go
revived board on the paper trading under the elite star same like we have for
elite star with openable trades"). Cards = revived GO stamps of the last 24h
(star_go / elite_go with a DEAD 1h verdict), plan from the fire, live progress,
chips (family, FAST/LATE, minutes after the fire, bell status), 📥 Open through
paper_bot at the live price. Judge on top = the new records-only desk tier
go_revived, opened at the GO price for every revived GO that rings (stars +
approved elite) — the forward record of exactly what the Open button does."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new)


# ── worker: tp2 on the GO stamp + the go_revived desk tier ──────────────
W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
W = rep(W,
        '                            "bell": _bell9})\n'
        '                        if _ew["go"] == "FAST" and _ew.get("star"):\n',
        '                            "tp2": _ew.get("tp2"),\n'
        '                            "bell": _bell9})\n'
        '                        if (_ew.get("oneh") == "DEAD"\n'
        '                                and (_ew.get("star") or _ew.get("appr"))):\n'
        "                            # 📥 go_revived desk tier (user 2026-10-06, the\n"
        "                            # GO REVIVED board): the forward record of\n"
        "                            # ENTERING at the revived GO — opened at the\n"
        "                            # GO price for every revived GO that rings.\n"
        "                            # Records only; the board quotes it.\n"
        "                            try:\n"
        "                                _rv_sig = {\n"
        '                                    "symbol": _ew["symbol"],\n'
        '                                    "base": _ew["base"],\n'
        '                                    "side": _ew["side"],\n'
        '                                    "entry": _ew_px, "stop": _ew["stop"],\n'
        '                                    "tp1": _ew["tp1"], "tp2": _ew.get("tp2"),\n'
        '                                    "tier": _ew["go"],\n'
        '                                    "star": bool(_ew.get("star")),\n'
        '                                    "fire_entry": _e0}\n'
        '                                store.record_signal("go_revived", _rv_sig)\n'
        "                                shadow_trader.open_from_signal(\n"
        '                                    "go_revived", _rv_sig, _ew_px)\n'
        "                            except Exception as _rv_exc:\n"
        '                                print("  go_revived tier error:", _rv_exc,\n'
        "                                      flush=True)\n"
        '                        if _ew["go"] == "FAST" and _ew.get("star"):\n',
        "GO stamp tp2 + go_revived tier")

# ── app: the board ──────────────────────────────────────────────────────
A = open(ROOT + "app.py", encoding="utf-8").read()
BOARD = '''def _render_revived_board(pb_state, live_prices=None) -> None:
    """⭐⚡ GO REVIVED — openable now (user 2026-10-06: "build go revived
    board on the paper trading under the elite star same like we have for
    elite star with openable trades"). Every revived GO of the last 24h —
    a star or approved elite fire graded DEAD at the hour that then ignited
    to +25% of its path — as a card: the fire's plan, where price sits now
    on the path, how long after the fire it ignited, whether the phone got
    the bell, and a 📥 Open button that takes it into the Paper Trader at
    the live price with the plan's stop / TP1 / TP2. Judge on top: the
    go_revived desk tier (entered at the GO price, the same thing the
    button does). Read-only on the worker DB; fail-soft."""
    st.markdown("#### ⭐⚡ GO REVIVED — openable now")
    st.caption(
        "A fire the hour graded DEAD that ignited anyway: on the desk, DEAD "
        "then ignited ran 71% / +0.39R over 55 stars and 73% / +0.55R over 52 "
        "elite fires (09 Sep → 28 Sep, measured from the FIRE price). Entering "
        "at the GO itself measured +0.10R on the star chase tier — the ledger "
        "line below is that entry, forward. Each card is a revived GO from the "
        "last 24 hours; 📥 Open takes it at the live price with the plan.")
    try:
        import sqlite3 as _sq_rb
        _now_rb = time.time()
        _since = _now_rb - 24 * 3600
        _crb = _sq_rb.connect(f"file:{_ws_c.DB_PATH}?mode=ro", uri=True)
        try:
            _gos = _crb.execute(
                "SELECT ts, symbol, base, side, entry, stop, tp1, tp2, tier, "
                "score, extra FROM signals WHERE stream IN ('star_go', "
                "'elite_go') AND ts>=? ORDER BY ts DESC", (_since,)).fetchall()
            _led = _crb.execute(
                "SELECT COUNT(*), SUM(CASE WHEN pnl_r>0 THEN 1 ELSE 0 END), "
                "COALESCE(SUM(pnl_r),0), "
                "SUM(CASE WHEN closed_at>=? THEN 1 ELSE 0 END), "
                "COALESCE(SUM(CASE WHEN closed_at>=? THEN pnl_r ELSE 0 END),0) "
                "FROM shadow_trades WHERE tier='go_revived' AND status='CLOSED' "
                "AND abs(entry-stop0)/entry>=0.005",
                (_now_rb - 14 * 86400, _now_rb - 14 * 86400)).fetchone()
            _open_desk = _crb.execute(
                "SELECT symbol, side FROM shadow_trades WHERE "
                "tier='go_revived' AND status='OPEN'").fetchall()
        finally:
            _crb.close()
    except Exception as _rb_exc:
        st.caption(f"⭐⚡ board unavailable right now: {_rb_exc}")
        return
    _n, _w, _net, _n14, _net14 = (int(_led[0] or 0), int(_led[1] or 0),
                                  float(_led[2] or 0), int(_led[3] or 0),
                                  float(_led[4] or 0))
    if _n:
        _cc = "#2ed47a" if _net > 0 else "#ff5c5c"
        st.markdown(
            f"**forward ledger (entry at the revived GO):** {_n} closed · win "
            f"{_w / _n * 100:.0f}% · <b style='color:{_cc}'>{_net:+.1f}R</b> "
            f"· last 14 days {_n14} closed {_net14:+.1f}R · "
            f"{len(_open_desk)} open on the desk", unsafe_allow_html=True)
    else:
        st.caption("forward ledger (entry at the revived GO): no closes yet — "
                   "the first revived GO opens it")
    _seen, _cards = set(), []
    for _r in _gos:
        try:
            _ex = json.loads(_r[10] or "{}")
        except Exception:
            _ex = {}
        if str(_ex.get("oneh") or "").upper() != "DEAD":
            continue                      # only the revived class
        _k = (_r[1], (_r[3] or "").upper())
        if _k in _seen:
            continue
        _seen.add(_k)
        _cards.append((_r, _ex))
    if not _cards:
        st.caption("· no revived GO in the last 24 hours — the next DEAD fire "
                   "that ignites appears here")
        return
    _held = ({p.get("symbol") for p in (pb_state.get("open") or [])}
             if pb_state else set())
    try:
        binance_client.prime_prices([r[1] for r, _ in _cards])
    except Exception:
        pass
    for _i, (_r, _ex) in enumerate(_cards[:12]):
        try:
            _ts, _sym, _b, _sd, _e, _stp, _t1, _t2, _tier, _mins, _extra = _r
            _e, _stp, _t1 = float(_e), float(_stp), float(_t1)
            _t2f = float(_t2) if _t2 else None
            _sd = (_sd or "").upper()
            _lng = _sd == "LONG"
            _live = None
            try:
                _live = float((live_prices or {}).get(_sym) or
                              binance_client.get_ticker_price(_sym) or 0) or None
            except Exception:
                _live = None
            _prog = None
            if _live and _t1 != _e:
                _prog = ((_live - _e) / (_t1 - _e) if _lng
                         else (_e - _live) / (_e - _t1))
            _stopped = bool(_live) and ((_live <= _stp) if _lng
                                        else (_live >= _stp))
            if _stopped:
                _status, _scol = "🔴 stopped", "#ff5c5c"
            elif _prog is None:
                _status, _scol = "price n/a", "#8b93a7"
            elif _prog >= 1:
                _status, _scol = f"🏆 past TP1 ({_prog * 100:.0f}%)", "#ffd700"
            elif _prog >= 0.25:
                _status, _scol = f"🟡 holding the ignition ({_prog * 100:.0f}% to TP1)", "#ffd54a"
            elif _prog >= 0:
                _status, _scol = f"🟠 fell back ({_prog * 100:.0f}% to TP1)", "#ffb347"
            else:
                _status, _scol = f"🔻 under the fire entry ({_prog * 100:.0f}%)", "#ff8c69"
            _chips = ["⭐ star" if _ex.get("star") else "💎 elite",
                      f"⭐⚡ GO {_tier or ''}".strip(),
                      f"ignited {float(_mins or 0):.0f} min after the fire",
                      "⏱ 1H DEAD"]
            _bell = str(_ex.get("bell") or "")
            if _bell.startswith("sent"):
                _chips.append("🔔 bell ✓")
            elif _bell:
                _chips.append(f"🔕 no bell: {_bell}")
            _pkt = time.strftime("%H:%M", time.gmtime(float(_ts) + 5 * 3600))
            _ago = (_now_rb - float(_ts)) / 3600
            _sc = "#2ed47a" if _lng else "#ff5c5c"
            _c1, _c2 = st.columns([5, 1])
            _c1.markdown(
                f"<div style='background:rgba(120,200,255,0.06);border:1px solid "
                f"rgba(120,200,255,0.30);border-radius:10px;padding:8px 13px;"
                f"margin:4px 0'>⭐⚡ <b>{_b}</b> <span style='color:{_sc};"
                f"font-weight:800'>{_sd}</span> · GO at {_pkt} PKT "
                f"({_ago:.1f}h ago) · <span style='color:{_scol}'>{_status}</span>"
                f"<br><span style='color:#8b93a7;font-size:0.8rem'>fire entry "
                f"{_e:g} · SL {_stp:g} · TP1 {_t1:g}"
                + (f" · TP2 {_t2f:g}" if _t2f else "")
                + (f" · live {_live:g}" if _live else "")
                + " · " + " · ".join(_chips)
                + "</span></div>", unsafe_allow_html=True)
            _openable = (pb_state is not None and _live and not _stopped
                         and (_prog is None or _prog < 1))
            if _sym in _held:
                _c2.caption("✓ open")
            elif not _openable:
                _c2.caption("—")
            elif _c2.button("📥 Open", key=f"revived_open_{_sym}_{_i}",
                            use_container_width=True):
                try:
                    _alert = {
                        "symbol": _sym, "base": _b, "side": _sd,
                        "entry_low": _live, "stop": _stp, "target": _t1,
                        "target_2": _t2f, "chase_tp2_eligible": False,
                        "confidence": 70, "strength_factor": 0.7,
                        "_unified_source": "go_revived"}
                    _pos = paper_bot.open_position(pb_state, _alert, _live)
                    paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                    if _pos:
                        st.success(f"Opened {_sd} {_b} (⭐⚡ GO REVIVED) at {_live:g}")
                        st.rerun()
                    else:
                        st.warning("Not opened — Paper Trader rejected.")
                except Exception as _op_exc:
                    st.error(f"Open failed: {_op_exc}")
        except Exception:
            continue


'''
A = rep(A, "def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):\n",
        BOARD + "def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):\n",
        "board def before the brain-memory renderer")
A = rep(A,
        "            _render_star_board(pb_state, live_prices)\n"
        "        except Exception as _sb_exc2:\n"
        '            st.caption(f"⭐ board error: {_sb_exc2}")\n',
        "            _render_star_board(pb_state, live_prices)\n"
        "        except Exception as _sb_exc2:\n"
        '            st.caption(f"⭐ board error: {_sb_exc2}")\n'
        "        try:   # ⭐⚡ the revived GO board sits right under the star board\n"
        "            _render_revived_board(pb_state, live_prices)\n"
        "        except Exception as _rb_exc2:\n"
        '            st.caption(f"⭐⚡ revived board error: {_rb_exc2}")\n',
        "board call under the star board")
A = rep(A,
        '                   "conv_prime": "💎🥇 ELITE × PRIME — conviction fire + 🥇 "\n'
        '                                 "PRIME on the coin (60%/+0.28R Sep desk, "\n'
        '                                 "every band recorded, proving)",\n',
        '                   "conv_prime": "💎🥇 ELITE × PRIME — conviction fire + 🥇 "\n'
        '                                 "PRIME on the coin (60%/+0.28R Sep desk, "\n'
        '                                 "every band recorded, proving)",\n'
        '                   "go_revived": "⭐⚡ GO REVIVED — entry at the revived GO "\n'
        '                                 "(DEAD at 1h, then ignited; stars + approved "\n'
        '                                 "elite; records only, the board\'s judge)",\n',
        "app tier name")

U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "conv_prime": "conv_prime",\n',
        '    "conv_prime": "conv_prime",\n    "go_revived": "go_revived",\n', "auditor map")

for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: GO REVIVED board + go_revived desk tier + names")

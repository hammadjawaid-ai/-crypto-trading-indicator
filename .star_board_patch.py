"""💎⭐ ELITE STAR — openable board on the Paper Trader page (user 2026-10-05: "an
elite star board on paper trading for my view ... openable trades on it").
Module-level renderer inserted before _render_brain_memory and called at the top
of the brain-memory area (before the DECISION DESK header). Read-only on the
worker DB; 📥 Open writes the trade into the Paper Trader exactly like the PRIME
cards do (paper_bot.open_position + save_state + rerun). Anchors must match once."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


A = open(ROOT + "app.py", encoding="utf-8").read()

BOARD = '''def _render_star_board(pb_state, live_prices=None) -> None:
    """💎⭐ ELITE STAR — openable now (user 2026-10-05: "an elite star board
    on paper trading for my view ... openable trades on it"). Every ⭐ fire
    of the last 24h as a card: the plan, conf / heat, the live price and
    how far it has travelled, the ⏱ 1H verdict and ⭐⚡ GO stamps once the
    worker has graded the fire, a 🏆 A-GRADE chip when the seat + conf 65
    rule also held, and a 📥 Open button that puts the trade into the
    Paper Trader at the live price with the plan's stop / TP1 / TP2.
    Forward ledger on top. Read-only on the worker DB; fail-soft."""
    st.markdown("#### 💎⭐ ELITE STAR — openable now")
    st.caption(
        "The measured elite winner profile (🚀 approved · HIGH · calm burst "
        "· TP1 within 1.2R). Each card is a ⭐ fire from the last 24 hours "
        "with its plan and live progress; 📥 Open takes it into the Paper "
        "Trader at the live price with the plan's stop and targets. Clock "
        "law: enter at the buzz, any hour; longs weakest 01-05 PKT, the "
        "22:00 PKT hour has been the killer.")
    try:
        import sqlite3 as _sq_sb
        _now_sb = time.time()
        _since = _now_sb - 24 * 3600
        _csb = _sq_sb.connect(f"file:{_ws_c.DB_PATH}?mode=ro", uri=True)
        try:
            _fires = _csb.execute(
                "SELECT ts, symbol, base, side, entry, stop, tp1, tp2, extra "
                "FROM signals WHERE stream='elite_star' AND ts>=? "
                "ORDER BY ts DESC", (_since,)).fetchall()
            _verd = _csb.execute(
                "SELECT ts, symbol, side, tier FROM signals WHERE "
                "stream='elite_1h' AND ts>=? ORDER BY ts", (_since,)).fetchall()
            _go = _csb.execute(
                "SELECT ts, symbol, side, tier FROM signals WHERE "
                "stream='star_go' AND ts>=? ORDER BY ts", (_since,)).fetchall()
            _agr = _csb.execute(
                "SELECT ts, symbol, side FROM signals WHERE "
                "stream='elite_agrade' AND ts>=?", (_since,)).fetchall()
            _led = _csb.execute(
                "SELECT COUNT(*), SUM(CASE WHEN pnl_r>0 THEN 1 ELSE 0 END), "
                "COALESCE(SUM(pnl_r),0), "
                "SUM(CASE WHEN closed_at>=? THEN 1 ELSE 0 END), "
                "COALESCE(SUM(CASE WHEN closed_at>=? THEN pnl_r ELSE 0 END),0) "
                "FROM shadow_trades WHERE tier='elite_star' AND status='CLOSED' "
                "AND abs(entry-stop0)/entry>=0.005",
                (_now_sb - 14 * 86400, _now_sb - 14 * 86400)).fetchone()
            _open_desk = _csb.execute(
                "SELECT symbol, side FROM shadow_trades WHERE "
                "tier='elite_star' AND status='OPEN'").fetchall()
        finally:
            _csb.close()
    except Exception as _sb_exc:
        st.caption(f"⭐ board unavailable right now: {_sb_exc}")
        return
    _n, _w, _net, _n14, _net14 = (int(_led[0] or 0), int(_led[1] or 0),
                                  float(_led[2] or 0), int(_led[3] or 0),
                                  float(_led[4] or 0))
    _cc = "#2ed47a" if _net > 0 else "#ff5c5c"
    if _n:
        st.markdown(
            f"**forward ledger (the judge):** {_n} closed · win "
            f"{_w / _n * 100:.0f}% · <b style='color:{_cc}'>{_net:+.1f}R</b> "
            f"· last 14 days {_n14} closed {_net14:+.1f}R · "
            f"{len(_open_desk)} ⭐ open on the desk", unsafe_allow_html=True)
    _seen, _cards = set(), []
    for _r in _fires:
        _k = (_r[1], (_r[3] or "").upper())
        if _k in _seen:
            continue
        _seen.add(_k)
        _cards.append(_r)
    if not _cards:
        st.caption("· no ⭐ fire in the last 24 hours — the worker buzzes "
                   "the next one and it appears here")
        return
    _held = ({p.get("symbol") for p in (pb_state.get("open") or [])}
             if pb_state else set())
    try:
        binance_client.prime_prices([r[1] for r in _cards])
    except Exception:
        pass
    for _i, _r in enumerate(_cards[:12]):
        try:
            _ts, _sym, _b, _sd, _e, _stp, _t1, _t2, _extra = _r
            _ex = json.loads(_extra or "{}")
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
            elif _prog > 0.25:
                _status, _scol = f"🟡 en route ({_prog * 100:.0f}% to TP1)", "#ffd54a"
            elif _prog >= 0:
                _status, _scol = f"🟢 in zone ({_prog * 100:.0f}% to TP1)", "#2ed47a"
            else:
                _status, _scol = (f"🟢 below entry ({_prog * 100:.0f}%) — "
                                  f"halfway to the stop comes back 50/50",
                                  "#2ed47a")
            _vt = [v[3] for v in _verd
                   if v[1] == _sym and (v[2] or "").upper() == _sd and v[0] >= _ts]
            _gt = [g[3] for g in _go
                   if g[1] == _sym and (g[2] or "").upper() == _sd and g[0] >= _ts]
            _isag = any(a[1] == _sym and (a[2] or "").upper() == _sd
                        and abs(a[0] - _ts) <= 2 * 3600 for a in _agr)
            _chips = []
            if _vt:
                _chips.append("⏱ 1H " + str(_vt[-1]))
            if _gt:
                _chips.append("⭐⚡ GO " + str(_gt[-1]))
            if _isag:
                _chips.append("🏆 A-GRADE")
            if _ex.get("conf") is not None:
                _chips.append(f"🎯 conf {_ex.get('conf')}")
            if _ex.get("heat") is not None:
                _chips.append(f"🌡 heat {_ex.get('heat')}")
            _pkt = time.strftime("%H:%M", time.gmtime(float(_ts) + 5 * 3600))
            _ago = (_now_sb - float(_ts)) / 3600
            _sc = "#2ed47a" if _lng else "#ff5c5c"
            _c1, _c2 = st.columns([5, 1])
            _c1.markdown(
                f"<div style='background:rgba(255,215,0,0.06);border:1px solid "
                f"rgba(255,215,0,0.30);border-radius:10px;padding:8px 13px;"
                f"margin:4px 0'>⭐ <b>{_b}</b> <span style='color:{_sc};"
                f"font-weight:800'>{_sd}</span> · fired {_pkt} PKT "
                f"({_ago:.1f}h ago) · <span style='color:{_scol}'>{_status}</span>"
                f"<br><span style='color:#8b93a7;font-size:0.8rem'>entry "
                f"{_e:g} · SL {_stp:g} · TP1 {_t1:g}"
                + (f" · TP2 {_t2f:g}" if _t2f else "")
                + (f" · live {_live:g}" if _live else "")
                + (" · " + " · ".join(_chips) if _chips else "")
                + "</span></div>", unsafe_allow_html=True)
            _openable = (pb_state is not None and _live and not _stopped
                         and (_prog is None or _prog < 1))
            if _sym in _held:
                _c2.caption("✓ open")
            elif not _openable:
                _c2.caption("—")
            elif _c2.button("📥 Open", key=f"star_open_{_sym}_{_i}",
                            use_container_width=True):
                try:
                    _alert = {
                        "symbol": _sym, "base": _b, "side": _sd,
                        "entry_low": _live, "stop": _stp, "target": _t1,
                        "target_2": _t2f, "chase_tp2_eligible": False,
                        "confidence": int(float(_ex.get("conf") or 0) or 70),
                        "strength_factor": 0.7,
                        "_unified_source": "elite_star"}
                    _pos = paper_bot.open_position(pb_state, _alert, _live)
                    paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                    if _pos:
                        st.success(f"Opened {_sd} {_b} (💎⭐ ELITE STAR) at {_live:g}")
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
        '    st.markdown("### ✳️ DECISION DESK — live forward proof")\n',
        '    if not best_zone_only:   # 💎⭐ the openable star board leads the desk area\n'
        '        try:\n'
        '            _render_star_board(pb_state, live_prices)\n'
        '        except Exception as _sb_exc2:\n'
        '            st.caption(f"⭐ board error: {_sb_exc2}")\n'
        '    st.markdown("### ✳️ DECISION DESK — live forward proof")\n',
        "board call before the desk header")
with open(ROOT + "app.py", "w", encoding="utf-8", newline="") as f:
    f.write(A)
print("patched app.py: ELITE STAR openable board")

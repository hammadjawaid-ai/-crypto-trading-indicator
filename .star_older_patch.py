"""2026-10-28 (user): (1) ⭐ star cards read the LIVE price only, so a fire that printed TP1
and came back said "in zone (7% to TP1)" (NIGHT) — the 15m candles since the fire now decide:
TP1 printed → 🏆 TP1 HIT, stop printed → 🔴, whatever price does afterwards. (2) 🕰 OLDER,
STILL RUNNING: under the recent cards, every ⭐ fire 24h–7d old whose plan has printed neither
TP1 nor the stop, with the measured read (alive at 24h → 56% TP1 first; above entry at 24h
70% / +0.38R, below 47% / −0.18R; with a GO 61–63%, no GO 48%). Page only; worker, bells and
desk untouched."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — nothing written")
    return src.replace(old, new)


A = open(ROOT + "app.py", encoding="utf-8").read()

HELPERS = '''def _path_since_frame(df, side, ts, entry, stop, tp1):
    """Pure path read on an OHLC frame indexed by candle open time: which of TP1 / the stop
    printed FIRST after the fire. -> (result, hit_ts, max_prog). result 'TP1' when a candle's
    high (long) / low (short) reached TP1 before any candle reached the stop; 'SL' when the stop
    printed first (a candle that spans both counts as the stop — the desk's rule); None while
    neither has printed. hit_ts = that candle's open (UTC s). max_prog = the furthest the path
    got, in TP1-path units (1.0 = TP1). Candles opening before the fire's own bar are ignored."""
    if df is None or not len(df):
        return (None, None, None)
    import pandas as _pd_ps
    idx = _pd_ps.DatetimeIndex(_pd_ps.to_datetime(df.index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    sec = idx.asi8 / 1e9
    keep = sec >= float(ts) - 900.0
    if not keep.any():
        return (None, None, None)
    d = df[keep]
    sec = sec[keep]
    lng = (side or "").upper() == "LONG"
    hi = d["high"].astype(float).to_numpy()
    lo = d["low"].astype(float).to_numpy()
    entry, stop, tp1 = float(entry), float(stop), float(tp1)
    tp_hit = (hi >= tp1) if lng else (lo <= tp1)
    sl_hit = (lo <= stop) if lng else (hi >= stop)
    ktp = int(tp_hit.argmax()) if tp_hit.any() else None
    ksl = int(sl_hit.argmax()) if sl_hit.any() else None
    span = (tp1 - entry) if lng else (entry - tp1)
    max_prog = None
    if span:
        best = (hi.max() - entry) if lng else (entry - lo.min())
        max_prog = float(best / span)
    if ksl is not None and (ktp is None or ksl <= ktp):
        return ("SL", float(sec[ksl]), max_prog)
    if ktp is not None:
        return ("TP1", float(sec[ktp]), max_prog)
    return (None, None, max_prog)


@st.cache_data(ttl=120, show_spinner=False)
def _star_path_since(sym: str, side: str, ts: float, entry: float, stop: float, tp1: float):
    """🏁 What the 15m candles did since a ⭐ fire (user 2026-10-28: "night and others hit
    TP1 but the cards show they haven't" — the card read the live price only). One cached
    kline read per fire (120s, like the other page reads); fail-soft -> (None, None, None)."""
    try:
        age_h = max(0.0, (time.time() - float(ts)) / 3600.0)
        lim = int(min(672, age_h * 4 + 6))
        if lim < 3:
            return (None, None, None)
        df = binance_client.get_klines(sym, "15m", limit=lim)
        return _path_since_frame(df, side, ts, entry, stop, tp1)
    except Exception:
        return (None, None, None)


def _render_star_older(pb_state, live_prices=None) -> None:
    """🕰 OLDER ⭐ FIRES STILL RUNNING (user 2026-10-28: "ONDO ... fired 2 days before and
    haven't reached TP or SL ... can we see the earlier fires below the recent fires"): every
    star fire 24h–7d old, not already on a recent card, whose plan has printed neither TP1 nor
    the stop on the 15m candles — newest first, with where price sits now, the GO / 1H / gate
    stamps and the desk seat. The read behind the list (499 star fires 9 Sep → 25 Oct): alive at
    24h → TP1 first 56% / +0.04R; above entry at the 24h mark 70% / +0.38R, below 47% / −0.18R;
    with a GO FAST or LATE 61–63%, no GO 48%; alive at 48h 47% / −0.13R. Read-only; fail-soft."""
    try:
        import sqlite3 as _sq_so
        _now = time.time()
        _c = _sq_so.connect(f"file:{_ws_c.DB_PATH}?mode=ro", uri=True)
        try:
            _old = _c.execute(
                "SELECT ts, symbol, base, side, entry, stop, tp1, tp2, extra FROM signals "
                "WHERE stream='elite_star' AND ts>=? AND ts<? ORDER BY ts DESC",
                (_now - 7 * 86400, _now - 24 * 3600)).fetchall()
            _recent = _c.execute(
                "SELECT symbol, side FROM signals WHERE stream='elite_star' AND ts>=?",
                (_now - 24 * 3600,)).fetchall()
            _verd = _c.execute(
                "SELECT ts, symbol, side, tier FROM signals WHERE stream='elite_1h' AND ts>=? ORDER BY ts",
                (_now - 7 * 86400,)).fetchall()
            _go = _c.execute(
                "SELECT ts, symbol, side, tier FROM signals WHERE stream='star_go' AND ts>=? ORDER BY ts",
                (_now - 7 * 86400,)).fetchall()
            _desk = _c.execute(
                "SELECT symbol, side, opened_at, status, exit_reason, pnl_r, tp1_hit FROM shadow_trades "
                "WHERE tier='elite_star' AND opened_at>=?", (_now - 7 * 86400 - 1800,)).fetchall()
        finally:
            _c.close()
    except Exception:
        return
    if not _old:
        return
    _skip = {(r[0], (r[1] or "").upper()) for r in _recent}
    _seen, _rows, _done_tp, _done_sl = set(), [], 0, 0
    try:
        binance_client.prime_prices(list(dict.fromkeys(r[1] for r in _old))[:40])
    except Exception:
        pass
    for _r in _old:
        try:
            _ts, _sym, _b, _sd, _e, _stp, _t1, _t2, _extra = _r
            _sd = (_sd or "").upper()
            _k = (_sym, _sd)
            if _k in _seen or _k in _skip:
                continue
            _seen.add(_k)
            _e, _stp, _t1 = float(_e), float(_stp), float(_t1)
            _lng = _sd == "LONG"
            _pres, _pts, _pmax = _star_path_since(_sym, _sd, float(_ts), _e, _stp, _t1)
            if _pres == "TP1":
                _done_tp += 1
                continue
            if _pres == "SL":
                _done_sl += 1
                continue
            _live = None
            try:
                _live = float((live_prices or {}).get(_sym) or
                              binance_client.get_ticker_price(_sym) or 0) or None
            except Exception:
                _live = None
            _prog = None
            if _live and _t1 != _e:
                _prog = ((_live - _e) / (_t1 - _e) if _lng else (_e - _live) / (_e - _t1))
            _ex = json.loads(_extra or "{}")
            _vt = [v[3] for v in _verd if v[1] == _sym and (v[2] or "").upper() == _sd and v[0] >= _ts]
            _gt = [g[3] for g in _go if g[1] == _sym and (g[2] or "").upper() == _sd and g[0] >= _ts]
            _dk = [d for d in _desk if d[0] == _sym and (d[1] or "").upper() == _sd
                   and abs(float(d[2] or 0) - float(_ts)) <= 1800]
            _rows.append((_ts, _b, _sd, _e, _stp, _t1, _live, _prog, _pmax,
                          _vt[-1] if _vt else None, _gt, str(_ex.get("gate") or ""),
                          _dk[0] if _dk else None))
        except Exception:
            continue
    st.markdown("##### 🕰 older ⭐ fires still running — 24h to 7d old, neither TP1 nor the stop printed yet")
    st.caption(
        "Measured 9 Sep → 25 Oct on 499 star fires: a star still alive at 24h reaches TP1 first 56% of the "
        "time (+0.04R); above its entry at the 24h mark 70% / +0.38R, below it 47% / −0.18R; with a GO FAST "
        "or LATE 61–63%, with no GO 48%; still alive at 48h 47% / −0.13R. The sign of the P&L is the read."
        + (f" Older fires already resolved: {_done_tp} printed TP1 · {_done_sl} stopped."
           if (_done_tp or _done_sl) else ""))
    if not _rows:
        st.caption("· none right now — every older ⭐ fire has printed TP1 or its stop")
        return
    for (_ts, _b, _sd, _e, _stp, _t1, _live, _prog, _pmax, _v1, _gt, _gs, _d) in _rows[:15]:
        _age = (_now - float(_ts)) / 3600
        _pkt = time.strftime("%d %b %H:%M", time.gmtime(float(_ts) + 5 * 3600))
        _sc = "#2ed47a" if _sd == "LONG" else "#ff5c5c"
        if _prog is None:
            _pl, _pc = "price n/a", "#8b93a7"
        elif _prog >= 0:
            _pl, _pc = f"🟢 above entry · {_prog * 100:.0f}% to TP1", "#2ed47a"
        else:
            _pl, _pc = f"🔴 below entry ({_prog * 100:.0f}%)", "#ff5c5c"
        _tags = []
        _tags.append("⭐⚡ GO " + "/".join(dict.fromkeys(str(g) for g in _gt)) if _gt else "no GO yet")
        if _v1:
            _tags.append("⏱ 1H " + str(_v1))
        if _gs:
            _tags.append("🔔 rang" if (_gs.endswith("pass") or _gs == "off") else "🔕 muted")
        if _d:
            _tags.append("desk " + ("OPEN" if str(_d[3]).upper() == "OPEN"
                                    else f"closed {_d[4] or '—'} {float(_d[5] or 0):+.2f}R"))
        if _pmax is not None:
            _tags.append(f"best {_pmax * 100:.0f}% of the way")
        st.markdown(
            f"<div style='background:rgba(255,215,0,0.035);border:1px solid rgba(255,215,0,0.18);"
            f"border-radius:8px;padding:5px 11px;margin:3px 0;font-size:0.82rem'>⭐ <b>{_b}</b> "
            f"<span style='color:{_sc};font-weight:800'>{_sd}</span> · fired {_pkt} PKT ({_age:.0f}h ago) · "
            f"<span style='color:{_pc}'>{_pl}</span><br><span style='color:#8b93a7;font-size:0.78rem'>"
            f"entry {_e:g} · SL {_stp:g} · TP1 {_t1:g}" + (f" · live {_live:g}" if _live else "")
            + " · " + " · ".join(_tags) + "</span></div>", unsafe_allow_html=True)


'''
A = rep(A, "def _render_star_board(pb_state, live_prices=None) -> None:\n",
        HELPERS + "def _render_star_board(pb_state, live_prices=None) -> None:\n", "helpers before the star board")

# Block A — the path check on every recent star card
A = rep(A,
        '            else:\n'
        '                _status, _scol = (f"🟢 below entry ({_prog * 100:.0f}%) — "\n'
        '                                  f"halfway to the stop comes back 50/50",\n'
        '                                  "#2ed47a")\n'
        '            _vt = [v[3] for v in _verd\n'
        '                   if v[1] == _sym and (v[2] or "").upper() == _sd and v[0] >= _ts]\n'
        '            _gt = [(g[3], g[4]) for g in _go\n',
        '            else:\n'
        '                _status, _scol = (f"🟢 below entry ({_prog * 100:.0f}%) — "\n'
        '                                  f"halfway to the stop comes back 50/50",\n'
        '                                  "#2ed47a")\n'
        '            # 🏁 path check (user 2026-10-28: "night and others hit TP1 but the\n'
        '            # cards show they haven\'t") — the status above reads the LIVE price\n'
        '            # only, so a fire that printed TP1 and came back read "in zone". The\n'
        '            # 15m candles since the fire decide: TP1 printed → 🏆, the stop\n'
        '            # printed → 🔴, whatever price does afterwards. Neither → the live\n'
        '            # read stands, with the best point reached when it is well past it.\n'
        '            try:\n'
        '                _pres, _pts, _pmax = _star_path_since(_sym, _sd, float(_ts), _e, _stp, _t1)\n'
        '            except Exception:\n'
        '                _pres, _pts, _pmax = None, None, None\n'
        '            if _pres == "TP1":\n'
        '                _hp = time.strftime("%H:%M", time.gmtime(float(_pts or _ts) + 5 * 3600))\n'
        '                _status = (f"🏆 TP1 HIT — printed {_hp} PKT on the candles"\n'
        '                           + (f" · live now {_prog * 100:.0f}% of the way" if _prog is not None else ""))\n'
        '                _scol = "#ffd700"\n'
        '                _prog = max(float(_prog or 0.0), 1.0)      # no 📥 Open after TP1\n'
        '            elif _pres == "SL" and not _stopped:\n'
        '                _hp = time.strftime("%H:%M", time.gmtime(float(_pts or _ts) + 5 * 3600))\n'
        '                _status = (f"🔴 stop printed {_hp} PKT on the candles"\n'
        '                           + (f" · live now {_prog * 100:.0f}% of the way" if _prog is not None else ""))\n'
        '                _scol, _stopped = "#ff5c5c", True\n'
        '            elif (_pmax is not None and _prog is not None and _pmax < 1\n'
        '                  and _pmax > _prog + 0.10):\n'
        '                _status += f" · reached {_pmax * 100:.0f}% at best"\n'
        '            _vt = [v[3] for v in _verd\n'
        '                   if v[1] == _sym and (v[2] or "").upper() == _sd and v[0] >= _ts]\n'
        '            _gt = [(g[3], g[4]) for g in _go\n', "path block on the card")

# the call: the older list right under the recent cards
import re
m = re.search(r"\n([ \t]+)_render_star_board\(pb_state, live_prices\)\n", A)
if not m:
    raise SystemExit("star board call site not found")
ind = m.group(1)
A = rep(A, f"\n{ind}_render_star_board(pb_state, live_prices)\n",
        f"\n{ind}_render_star_board(pb_state, live_prices)\n{ind}_render_star_older(pb_state, live_prices)   # 🕰 2026-10-28\n", "call site")
with open(ROOT + "app.py", "w", encoding="utf-8", newline="") as f:
    f.write(A)

# guard: the star board compare learns the sanctioned path block
G = open(ROOT + ".go_live_test.py", encoding="utf-8").read()
G = rep(G,
        "def _norm_sb(x):\n    return _strip_bank_chip(_strip_gate_chip((x or \"\"))).replace(_EGO_INS, \"\").replace(_CLOCK_INS, \"\").replace(_TP1_INS, _TP1_WAS)\n",
        "def _strip_path_block(x):\n"
        "    # 2026-10-28: the 🏁 candle-path status block on the star card (user order: NIGHT printed TP1, card said 7%)\n"
        "    i = (x or \"\").find(\"            # 🏁 path check (user 2026-10-28\")\n"
        "    j = (x or \"\").find(\"            _vt = [v[3] for v in _verd\\n\", i)\n"
        "    return x if (i < 0 or j < 0) else x[:i] + x[j:]\n"
        "\n"
        "\n"
        "def _norm_sb(x):\n    return _strip_path_block(_strip_bank_chip(_strip_gate_chip((x or \"\")))).replace(_EGO_INS, \"\").replace(_CLOCK_INS, \"\").replace(_TP1_INS, _TP1_WAS)\n",
        "go_live stripper")
with open(ROOT + ".go_live_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(G)
print("patched: app.py (path helper + cached read + older renderer + card block + call) · .go_live_test.py stripper")

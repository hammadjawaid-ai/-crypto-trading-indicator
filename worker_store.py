"""SQLite durable storage for the 24/7 worker.

One file on the host (WORKER_DB_PATH, default .worker.db). Survives restarts.
On Railway/Render attach a volume for long-term history; without one it only
resets on a redeploy (worst case: a few duplicate alerts after a deploy —
harmless). Stores every scanned best-signal (the raw material for later
pattern/behaviour analysis), the alert dedup ledger, and per-cycle summaries.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import config


def _default_db() -> str:
    explicit = (os.environ.get("WORKER_DB_PATH", "") or "").strip()
    if explicit:
        return explicit
    sd = (getattr(config, "STATE_DIR", "") or "").strip()
    if sd:
        return str(Path(sd) / "worker.db")
    return str(Path(__file__).with_name(".worker.db"))


DB_PATH = _default_db()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, stream TEXT, symbol TEXT, base TEXT, side TEXT,
  tier TEXT, score REAL, conviction REAL, hot INTEGER, atr_pct REAL,
  entry REAL, stop REAL, tp1 REAL, tp2 REAL, extra TEXT
);
CREATE TABLE IF NOT EXISTS alerts_sent (
  alert_id TEXT PRIMARY KEY, last_ts REAL, count INTEGER
);
CREATE TABLE IF NOT EXISTS cycles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, regime TEXT, n_sst1 INTEGER, n_takenow INTEGER, n_alerts INTEGER
);
CREATE TABLE IF NOT EXISTS shadow_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tier TEXT, symbol TEXT, side TEXT,
  entry REAL, stop REAL, stop0 REAL, tp1 REAL, tp2 REAL,
  peak REAL, be_set INTEGER DEFAULT 0, tp1_hit INTEGER DEFAULT 0,
  opened_at REAL, status TEXT DEFAULT 'OPEN',
  exit_px REAL, exit_reason TEXT, closed_at REAL, pnl_r REAL
);
CREATE TABLE IF NOT EXISTS event_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, symbol TEXT, direction TEXT, category TEXT,
  impact REAL, title TEXT
);
"""


def _open() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.executescript(_SCHEMA)
    return c


def record_signal(stream: str, p: dict, ts: float | None = None) -> None:
    ts = time.time() if ts is None else ts
    c = _open()
    try:
        c.execute(
            "INSERT INTO signals (ts,stream,symbol,base,side,tier,score,"
            "conviction,hot,atr_pct,entry,stop,tp1,tp2,extra) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts, stream, p.get("symbol"), p.get("base"), p.get("side"),
             p.get("tier"), p.get("score"), p.get("conviction"),
             1 if p.get("hot") else 0, p.get("atr_pct"),
             p.get("entry"), p.get("stop"), p.get("tp1"), p.get("tp2"),
             json.dumps(p, default=str)))
        c.commit()
    finally:
        c.close()


def should_alert(alert_id: str, cooldown_sec: float) -> bool:
    """True if this alert_id hasn't fired within cooldown_sec — and records
    it as fired now. False (skip) if it's still within the cooldown window."""
    now = time.time()
    c = _open()
    try:
        row = c.execute(
            "SELECT last_ts FROM alerts_sent WHERE alert_id=?",
            (alert_id,)).fetchone()
        if row is not None:
            if (now - float(row[0])) < cooldown_sec:
                return False
            c.execute(
                "UPDATE alerts_sent SET last_ts=?, count=count+1 "
                "WHERE alert_id=?", (now, alert_id))
        else:
            c.execute(
                "INSERT INTO alerts_sent (alert_id,last_ts,count) "
                "VALUES (?,?,1)", (alert_id, now))
        c.commit()
        return True
    finally:
        c.close()


def record_cycle(regime: str, n_sst1: int, n_takenow: int,
                 n_alerts: int, ts: float | None = None) -> None:
    ts = time.time() if ts is None else ts
    c = _open()
    try:
        c.execute(
            "INSERT INTO cycles (ts,regime,n_sst1,n_takenow,n_alerts) "
            "VALUES (?,?,?,?,?)", (ts, regime, n_sst1, n_takenow, n_alerts))
        c.commit()
    finally:
        c.close()


def stats() -> dict:
    c = _open()
    try:
        return {
            "signals": c.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
            "alerts": c.execute(
                "SELECT COUNT(*) FROM alerts_sent").fetchone()[0],
            "cycles": c.execute("SELECT COUNT(*) FROM cycles").fetchone()[0],
            "db": DB_PATH,
        }
    finally:
        c.close()


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    c = _open()
    try:
        c.row_factory = sqlite3.Row
        cur = c.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        c.close()


def recent_signals(limit: int = 40) -> list[dict]:
    return _rows(
        "SELECT ts,stream,symbol,base,side,tier,score,conviction,hot,atr_pct,"
        "entry,stop,tp1,tp2,extra FROM signals ORDER BY id DESC LIMIT ?",
        (limit,))


def recent_by_stream(stream: str, limit: int = 12) -> list[dict]:
    # `symbol` MUST be selected — the app's Open button builds the paper
    # trade from r["symbol"]; without it open_position rejects (sym=None)
    # and no brain card (APEX/FRESH/TAKE NOW/EARLY MOVERS) can be opened.
    return _rows(
        "SELECT ts,stream,symbol,base,side,tier,score,conviction,hot,atr_pct,"
        "entry,stop,tp1,tp2,extra FROM signals WHERE stream=? "
        "ORDER BY id DESC LIMIT ?", (stream, limit))


def recent_cycles(limit: int = 25) -> list[dict]:
    return _rows(
        "SELECT ts,regime,n_sst1,n_takenow,n_alerts FROM cycles "
        "ORDER BY id DESC LIMIT ?", (limit,))


def recent_alerts(limit: int = 25) -> list[dict]:
    return _rows(
        "SELECT alert_id,last_ts,count FROM alerts_sent "
        "ORDER BY last_ts DESC LIMIT ?", (limit,))


def last_cycle() -> dict | None:
    rows = recent_cycles(1)
    return rows[0] if rows else None


def shadow_has_open(tier: str, symbol: str) -> bool:
    c = _open()
    try:
        row = c.execute(
            "SELECT COUNT(*) FROM shadow_trades WHERE tier=? AND symbol=? "
            "AND status='OPEN'", (tier, symbol)).fetchone()
        return bool(row and row[0] > 0)
    finally:
        c.close()


def shadow_open(tier: str, symbol: str, side: str, entry: float,
                stop: float, tp1: float, tp2: float,
                conf: float | None = None,
                heat: float | None = None) -> None:
    """2026-08-28 (user: "the confidence on telegram... I want to
    know their win rates"): every shadow trade now carries the 🎯
    confidence score at open, so win rates slice by band directly.
    2026-09-05 (user: "have the confidence score on them because in
    this way we can measure"): 🌡 heat (continuous ATR percentile —
    the one validated candle input) stamps alongside conf, so the
    heat-band panel can judge it the same way conf was judged."""
    c = _open()
    try:
        for _ddl in ("ALTER TABLE shadow_trades ADD COLUMN conf REAL",
                     "ALTER TABLE shadow_trades ADD COLUMN heat REAL"):
            try:
                c.execute(_ddl)
                c.commit()
            except Exception:
                pass                   # column already exists
        c.execute(
            "INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,"
            "tp1,tp2,peak,opened_at,conf,heat) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tier, symbol, side, entry, stop, stop, tp1, tp2, entry,
             time.time(), conf, heat))
        c.commit()
    finally:
        c.close()


def heat_bands() -> list[dict]:
    """🌡 Win rate by HEAT BAND, all tiers pooled — the reader that
    judges the ATR-percentile chip on live outcomes (2026-09-05).
    Bands: <40 / 40-59 / 60-79 / 80+. Read-only."""
    c = _open()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(shadow_trades)")}
        if "heat" not in cols:
            return []
        rows = c.execute(
            "SELECT heat, pnl_r FROM shadow_trades WHERE status != 'OPEN' "
            "AND heat IS NOT NULL AND pnl_r IS NOT NULL").fetchall()
    except Exception:
        return []
    finally:
        c.close()

    def _band(x):
        return ("<40" if x < 40 else "40-59" if x < 60
                else "60-79" if x < 80 else "80+")
    g: dict = {}
    for ht, r in rows:
        b = g.setdefault(_band(float(ht)), {"band": _band(float(ht)),
                                            "n": 0, "wins": 0,
                                            "net_r": 0.0})
        b["n"] += 1
        b["wins"] += 1 if r > 0 else 0
        b["net_r"] += float(r)
    order = {"<40": 0, "40-59": 1, "60-79": 2, "80+": 3}
    out = sorted(g.values(), key=lambda b: order.get(b["band"], 9))
    for b in out:
        b["win_pct"] = round(b["wins"] / b["n"] * 100.0, 1) if b["n"] else 0.0
        b["net_r"] = round(b["net_r"], 2)
    return out


def shadow_open_trades() -> list[dict]:
    return _rows("SELECT * FROM shadow_trades WHERE status='OPEN'")


def shadow_update(tid: int, stop: float, peak: float, be_set: int,
                  tp1_hit: int) -> None:
    c = _open()
    try:
        c.execute(
            "UPDATE shadow_trades SET stop=?, peak=?, be_set=?, tp1_hit=? "
            "WHERE id=?", (stop, peak, be_set, tp1_hit, tid))
        c.commit()
    finally:
        c.close()


def shadow_close(tid: int, exit_px: float, reason: str,
                 pnl_r: float) -> None:
    c = _open()
    try:
        c.execute(
            "UPDATE shadow_trades SET status='CLOSED', exit_px=?, "
            "exit_reason=?, closed_at=?, pnl_r=? WHERE id=?",
            (exit_px, reason, time.time(), pnl_r, tid))
        c.commit()
    finally:
        c.close()


def shadow_summary() -> list[dict]:
    return _rows(
        "SELECT tier, "
        "SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) AS n, "
        "SUM(CASE WHEN status='CLOSED' AND pnl_r>0 THEN 1 ELSE 0 END) "
        "AS wins, "
        "SUM(CASE WHEN status='CLOSED' THEN pnl_r ELSE 0 END) AS net_r, "
        "SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open_n "
        "FROM shadow_trades GROUP BY tier ORDER BY net_r DESC")


def conf_bands(days: float = 0.0) -> list[dict]:
    """🎯 Win rate + net R by CONFIDENCE BAND, per desk tier.

    The reader for the conf stamped on every shadow trade since
    2026-08-28 (user 2026-08-31: "build the reader panel on paper
    trading decision desk so we have the backlog of this data").
    Reads only — never writes, never gates anything.

    Returns one row per (tier, band) with n / wins / win_pct / net_r,
    plus a synthetic tier "ALL" pooling every tier. Bands: "<65",
    "65-84", "85+". Trades whose conf was never stamped are skipped
    (nothing before 2026-08-28 has one). `days` > 0 limits to trades
    CLOSED in that window.
    """
    c = _open()
    try:
        cols = {r[1] for r in c.execute(
            "PRAGMA table_info(shadow_trades)")}
        if "conf" not in cols:
            return []
        sql = ("SELECT tier, conf, pnl_r FROM shadow_trades "
               "WHERE status != 'OPEN' AND conf IS NOT NULL "
               "AND pnl_r IS NOT NULL")
        args: tuple = ()
        if days and days > 0:
            sql += " AND closed_at >= ?"
            args = (time.time() - days * 86400,)
        rows = c.execute(sql, args).fetchall()
    except Exception:
        return []
    finally:
        c.close()

    def _band(cf: float) -> str:
        # Cut points chosen to answer live questions directly (user
        # 2026-08-31: "elite conviction with confidence score of 55
        # and above vs 40 and above — measure this somewhere"). The
        # old <65 bucket lumped 40-54 and 55-64 together and could
        # never settle that; these boundaries separate them.
        if cf < 40:
            return "<40"
        if cf < 55:
            return "40-54"
        if cf < 65:
            return "55-64"
        return "65-84" if cf < 85 else "85+"

    agg: dict = {}
    for tier, cf, pnl in rows:
        for key in ((tier or "?"), "ALL"):
            b = agg.setdefault((key, _band(float(cf))),
                               {"tier": key, "band": _band(float(cf)),
                                "n": 0, "wins": 0, "net_r": 0.0})
            b["n"] += 1
            b["wins"] += 1 if float(pnl) > 0 else 0
            b["net_r"] += float(pnl)
    out = []
    for v in agg.values():
        v["win_pct"] = (v["wins"] / v["n"] * 100.0) if v["n"] else 0.0
        v["exp_r"] = (v["net_r"] / v["n"]) if v["n"] else 0.0
        out.append(v)
    order = {"<40": 0, "40-54": 1, "55-64": 2, "65-84": 3, "85+": 4}
    out.sort(key=lambda r: (r["tier"] != "ALL", r["tier"],
                            order.get(r["band"], 9)))
    return out


def conf_open_count() -> int:
    """How many conf-stamped trades are still OPEN (not yet counted)."""
    c = _open()
    try:
        cols = {r[1] for r in c.execute(
            "PRAGMA table_info(shadow_trades)")}
        if "conf" not in cols:
            return 0
        return int(c.execute(
            "SELECT COUNT(*) FROM shadow_trades "
            "WHERE status = 'OPEN' AND conf IS NOT NULL"
        ).fetchone()[0])
    except Exception:
        return 0
    finally:
        c.close()


# 🤝 the elite-family streams whose AGREEMENT the user trades on
# (2026-09-03: "apex one trade best of the best or maybe elite all
# buzzed within 5 mins... these trades were proven very very effective")
CONFLUENCE_TIERS = ("apex", "best_board", "one_trade", "elite_conv",
                    "elite_confirm", "elite_early", "takenow_hot")


def confluence_bands(window_min: float = 30.0) -> list[dict]:
    """🤝 Win rate by CROSS-STREAM CONFLUENCE, from the live ledger.

    For every CLOSED elite-family shadow trade, counts how many
    DISTINCT elite-family tiers opened the same (symbol, side) within
    ±window_min of it (itself included), then buckets: solo / 2
    streams / 3+ swarm. Reads only — measures the user's observed
    "multiple buzzes at once = the effective trades" construct before
    anything ever gates on it. Per-trade basis: a 3-tier cluster
    contributes each of its closed trades to the 3+ row (that IS the
    'take the buzz' experience).
    """
    c = _open()
    try:
        marks = ",".join("?" for _ in CONFLUENCE_TIERS)
        allr = [dict(zip(("tier", "symbol", "side", "t"), r))
                for r in c.execute(
                    f"SELECT tier, symbol, side, opened_at "
                    f"FROM shadow_trades WHERE tier IN ({marks}) "
                    f"AND opened_at IS NOT NULL", CONFLUENCE_TIERS)]
        closed = [dict(zip(("tier", "symbol", "side", "t", "pnl"), r))
                  for r in c.execute(
                      f"SELECT tier, symbol, side, opened_at, pnl_r "
                      f"FROM shadow_trades WHERE tier IN ({marks}) "
                      f"AND status != 'OPEN' AND pnl_r IS NOT NULL "
                      f"AND opened_at IS NOT NULL", CONFLUENCE_TIERS)]
    except Exception:
        return []
    finally:
        c.close()
    by_key: dict = {}
    for r in allr:
        by_key.setdefault((r["symbol"], r["side"]), []).append(r)
    win = window_min * 60.0
    bands: dict = {}
    for r in closed:
        peers = {p["tier"] for p in by_key.get((r["symbol"], r["side"]), [])
                 if abs(p["t"] - r["t"]) <= win}
        k = len(peers)
        band = "1 solo" if k <= 1 else ("2 streams" if k == 2 else "3+ swarm")
        b = bands.setdefault(band, {"band": band, "n": 0, "wins": 0,
                                    "net_r": 0.0})
        b["n"] += 1
        b["wins"] += 1 if r["pnl"] > 0 else 0
        b["net_r"] += float(r["pnl"])
    order = {"1 solo": 0, "2 streams": 1, "3+ swarm": 2}
    out = sorted(bands.values(), key=lambda b: order.get(b["band"], 9))
    for b in out:
        b["win_pct"] = round(b["wins"] / b["n"] * 100.0, 1) if b["n"] else 0.0
        b["net_r"] = round(b["net_r"], 2)
    return out


def confluence_conf_bands(window_min: float = 30.0) -> dict:
    """🤝×🎯 The user's exact question (2026-09-03): "when apex + best
    + one trade + elite fire within the same 30 minutes — what
    confidence score made them the winners?"

    Returns {"conf": [...], "elite": [...]}:
      conf  — closed conf-stamped elite-family trades, grouped by
              cluster bucket (solo / 2 streams / 3+ swarm) x conf band.
      elite — the elite MAX/HIGH slice: closed elite trades joined to
              their signal record (symbol+side within ±10 min) for the
              MAX/HIGH label and the bracket score, grouped by bucket x
              tier and bucket x score band.
    Read-only; conf stamps exist since 2026-08-28 only.
    """
    c = _open()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(shadow_trades)")}
        has_conf = "conf" in cols
        marks = ",".join("?" for _ in CONFLUENCE_TIERS)
        allr = [dict(zip(("tier", "symbol", "side", "t"), r))
                for r in c.execute(
                    f"SELECT tier, symbol, side, opened_at "
                    f"FROM shadow_trades WHERE tier IN ({marks}) "
                    f"AND opened_at IS NOT NULL", CONFLUENCE_TIERS)]
        sel_conf = "conf" if has_conf else "NULL"
        closed = [dict(zip(("tier", "symbol", "side", "t", "pnl", "conf"),
                           r))
                  for r in c.execute(
                      f"SELECT tier, symbol, side, opened_at, pnl_r, "
                      f"{sel_conf} FROM shadow_trades "
                      f"WHERE tier IN ({marks}) AND status != 'OPEN' "
                      f"AND pnl_r IS NOT NULL AND opened_at IS NOT NULL",
                      CONFLUENCE_TIERS)]
        esigs = [dict(zip(("ts", "symbol", "side", "etier", "score"), r))
                 for r in c.execute(
                     "SELECT ts, symbol, side, tier, score FROM signals "
                     "WHERE tier IN ('MAX','HIGH') AND ts IS NOT NULL")]
    except Exception:
        return {"conf": [], "elite": []}
    finally:
        c.close()

    by_key: dict = {}
    for r in allr:
        by_key.setdefault((r["symbol"], r["side"]), []).append(r)
    esig_key: dict = {}
    for s in esigs:
        esig_key.setdefault((s["symbol"], s["side"]), []).append(s)
    win = window_min * 60.0

    def _bucket(r):
        peers = {p["tier"] for p in by_key.get((r["symbol"], r["side"]), [])
                 if abs(p["t"] - r["t"]) <= win}
        k = len(peers)
        return "1 solo" if k <= 1 else ("2 streams" if k == 2
                                        else "3+ swarm")

    def _cband(cf):
        if cf < 40:
            return "<40"
        if cf < 55:
            return "40-54"
        if cf < 65:
            return "55-64"
        return "65-84" if cf < 85 else "85+"

    conf_g: dict = {}
    elite_g: dict = {}
    for r in closed:
        bk = _bucket(r)
        if r["conf"] is not None:
            key = (bk, _cband(float(r["conf"])))
            g = conf_g.setdefault(key, {"bucket": bk, "band": key[1],
                                        "n": 0, "wins": 0, "net_r": 0.0})
            g["n"] += 1
            g["wins"] += 1 if r["pnl"] > 0 else 0
            g["net_r"] += float(r["pnl"])
        # elite MAX/HIGH slice: nearest MAX/HIGH signal within ±10 min
        if r["tier"] in ("elite_conv", "elite_confirm"):
            cands = [s for s in esig_key.get((r["symbol"], r["side"]), [])
                     if abs(s["ts"] - r["t"]) <= 600]
            if cands:
                s = min(cands, key=lambda x: abs(x["ts"] - r["t"]))
                sc = float(s["score"] or 0)
                sb = ("90+" if sc >= 90 else
                      "85-89" if sc >= 85 else
                      "80-84" if sc >= 80 else "<80")
                for lab in (f"{s['etier']}", f"score {sb}"):
                    key = (bk, lab)
                    g = elite_g.setdefault(key, {"bucket": bk, "band": lab,
                                                 "n": 0, "wins": 0,
                                                 "net_r": 0.0})
                    g["n"] += 1
                    g["wins"] += 1 if r["pnl"] > 0 else 0
                    g["net_r"] += float(r["pnl"])

    border = {"1 solo": 0, "2 streams": 1, "3+ swarm": 2}
    corder = {"<40": 0, "40-54": 1, "55-64": 2, "65-84": 3, "85+": 4}

    def _fin(groups, bandorder=None):
        out = sorted(groups.values(),
                     key=lambda g: (border.get(g["bucket"], 9),
                                    (bandorder or {}).get(g["band"], 9),
                                    g["band"]))
        for g in out:
            g["win_pct"] = (round(g["wins"] / g["n"] * 100.0, 1)
                            if g["n"] else 0.0)
            g["net_r"] = round(g["net_r"], 2)
        return out

    return {"conf": _fin(conf_g, corder), "elite": _fin(elite_g)}


def duo_pair_bands(window_min: float = 30.0) -> list[dict]:
    """🤝 WHICH pairs win (user 2026-09-03: "apex + best or one trade
    can we test?") — closed trades in EXACTLY-2-stream clusters,
    grouped by the pair itself, overall and at conf >= 85 (the buzz
    cell). Read-only."""
    c = _open()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(shadow_trades)")}
        sel_conf = "conf" if "conf" in cols else "NULL"
        marks = ",".join("?" for _ in CONFLUENCE_TIERS)
        allr = [dict(zip(("tier", "symbol", "side", "t"), r))
                for r in c.execute(
                    f"SELECT tier, symbol, side, opened_at "
                    f"FROM shadow_trades WHERE tier IN ({marks}) "
                    f"AND opened_at IS NOT NULL", CONFLUENCE_TIERS)]
        closed = [dict(zip(("tier", "symbol", "side", "t", "pnl", "conf"),
                           r))
                  for r in c.execute(
                      f"SELECT tier, symbol, side, opened_at, pnl_r, "
                      f"{sel_conf} FROM shadow_trades "
                      f"WHERE tier IN ({marks}) AND status != 'OPEN' "
                      f"AND pnl_r IS NOT NULL AND opened_at IS NOT NULL",
                      CONFLUENCE_TIERS)]
    except Exception:
        return []
    finally:
        c.close()
    by_key: dict = {}
    for r in allr:
        by_key.setdefault((r["symbol"], r["side"]), []).append(r)
    win = window_min * 60.0
    groups: dict = {}
    for r in closed:
        peers = {p["tier"] for p in by_key.get((r["symbol"], r["side"]), [])
                 if abs(p["t"] - r["t"]) <= win}
        if len(peers) != 2:
            continue
        pair = " + ".join(sorted(peers))
        hi = (r["conf"] is not None and float(r["conf"]) >= 85)
        for lab in ([pair] + ([f"{pair} @85+"] if hi else [])):
            g = groups.setdefault(lab, {"pair": lab, "n": 0, "wins": 0,
                                        "net_r": 0.0})
            g["n"] += 1
            g["wins"] += 1 if r["pnl"] > 0 else 0
            g["net_r"] += float(r["pnl"])
    out = sorted(groups.values(), key=lambda g: (-g["n"], g["pair"]))
    for g in out:
        g["win_pct"] = round(g["wins"] / g["n"] * 100.0, 1) if g["n"] else 0.0
        g["net_r"] = round(g["net_r"], 2)
    return out


def live_cluster(symbol: str, side: str,
                 window_sec: float = 1800.0) -> list[str]:
    """🤝 Which OTHER elite-family streams opened this (symbol, side)
    within the trailing window — the cluster-count confidence display
    (2026-09-04 conf rebuild, display-only, gates nothing)."""
    cutoff = time.time() - window_sec
    c = _open()
    try:
        marks = ",".join("?" for _ in CONFLUENCE_TIERS)
        return sorted({r[0] for r in c.execute(
            f"SELECT DISTINCT tier FROM shadow_trades "
            f"WHERE tier IN ({marks}) AND symbol=? AND side=? "
            f"AND opened_at >= ?",
            (*CONFLUENCE_TIERS, symbol, (side or "").upper(), cutoff))})
    except Exception:
        return []
    finally:
        c.close()


def record_event_flag(symbol, direction, category, impact, title) -> None:
    """📰 Narrative-layer recorder (2026-09-04): stores impactful news
    flags per coin. RECORDS ONLY — nothing reads this to gate or buzz;
    after the pre-registered ~2-3 week window the flags get joined to
    desk outcomes and judged."""
    c = _open()
    try:
        c.execute(
            "INSERT INTO event_flags (ts,symbol,direction,category,"
            "impact,title) VALUES (?,?,?,?,?,?)",
            (time.time(), symbol, direction, category,
             float(impact or 0), str(title or "")[:200]))
        c.commit()
    finally:
        c.close()


def event_flag_count(days: float = 1.0) -> int:
    c = _open()
    try:
        return int(c.execute(
            "SELECT COUNT(*) FROM event_flags WHERE ts >= ?",
            (time.time() - days * 86400,)).fetchone()[0])
    except Exception:
        return 0
    finally:
        c.close()


def golden_cells(min_n: int = 25, min_win: float = 55.0) -> list[dict]:
    """🎯 SNIPER v2 fuel (user 2026-09-06: "its main goal is to get
    the trades that hits the most in tp... the highest win rate").

    Mines the LIVE ledger — every closed shadow trade — for the cells
    that actually hit: (tier x cluster-bucket) win rate and net R,
    computed the same way the confluence panel proved out (kingpair
    51%/+0.54R, apextn 52%/+0.35R, trig_strong 68% solo...). A cell
    qualifies as GOLDEN when win >= min_win, n >= min_n and net R > 0.
    The meta-board fires ONLY signals landing in golden cells, so its
    gate自 updates itself as the ledger grows. Read-only."""
    c = _open()
    try:
        allr = [dict(zip(("tier", "symbol", "side", "t"), r))
                for r in c.execute(
                    "SELECT tier, symbol, side, opened_at FROM "
                    "shadow_trades WHERE opened_at IS NOT NULL")]
        closed = [dict(zip(("tier", "symbol", "side", "t", "pnl"), r))
                  for r in c.execute(
                      "SELECT tier, symbol, side, opened_at, pnl_r "
                      "FROM shadow_trades WHERE status != 'OPEN' "
                      "AND pnl_r IS NOT NULL "
                      "AND opened_at IS NOT NULL")]
    except Exception:
        return []
    finally:
        c.close()
    by_key: dict = {}
    for r in allr:
        if r["tier"] in CONFLUENCE_TIERS:
            by_key.setdefault((r["symbol"], r["side"]), []).append(r)

    def _bucket(r):
        peers = {p["tier"] for p in by_key.get((r["symbol"], r["side"]),
                                               [])
                 if abs(p["t"] - r["t"]) <= 1800}
        k = len(peers)
        return "solo" if k <= 1 else ("duo" if k == 2 else "crowd")

    g: dict = {}
    for r in closed:
        key = (r["tier"], _bucket(r))
        b = g.setdefault(key, {"tier": key[0], "bucket": key[1],
                               "n": 0, "wins": 0, "net_r": 0.0})
        b["n"] += 1
        b["wins"] += 1 if r["pnl"] > 0 else 0
        b["net_r"] += float(r["pnl"])
    out = []
    for b in g.values():
        if b["n"] >= min_n and b["net_r"] > 0:
            wp = b["wins"] / b["n"] * 100.0
            if wp >= min_win:
                b["win_pct"] = round(wp, 1)
                b["net_r"] = round(b["net_r"], 2)
                out.append(b)
    out.sort(key=lambda x: -x["win_pct"])
    return out


def fresh_duo_clusters(window_sec: float = 1800.0) -> list[dict]:
    """🤝 (symbol, side) where EXACTLY TWO elite-family streams opened
    desk trades within the trailing window. The measured winner cell
    (2026-09-03 confluence panel): 2 streams + conf 85+ ran 50% /
    +0.218R while the 3+ swarm ran 31% / -0.167R — exactly-two is the
    construct, a third voice downgrades it."""
    cutoff = time.time() - window_sec
    c = _open()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(shadow_trades)")}
        sel_conf = "conf" if "conf" in cols else "NULL"
        marks = ",".join("?" for _ in CONFLUENCE_TIERS)
        rows = [dict(zip(("tier", "symbol", "side", "t", "conf", "entry",
                          "stop", "tp1", "tp2"), r))
                for r in c.execute(
                    f"SELECT tier, symbol, side, opened_at, {sel_conf}, "
                    f"entry, stop, tp1, tp2 FROM shadow_trades "
                    f"WHERE tier IN ({marks}) AND opened_at >= ?",
                    (*CONFLUENCE_TIERS, cutoff))]
    except Exception:
        return []
    finally:
        c.close()
    by_key: dict = {}
    for r in rows:
        by_key.setdefault((r["symbol"], r["side"]), []).append(r)
    out = []
    for (sym, side), rs in by_key.items():
        tiers = sorted({r["tier"] for r in rs})
        if len(tiers) != 2:
            continue
        fresh = max(rs, key=lambda r: r["t"])
        confs = [float(r["conf"]) for r in rs if r["conf"] is not None]
        out.append({"symbol": sym, "side": side, "tiers": tiers,
                    "conf": max(confs) if confs else None,
                    "entry": fresh["entry"], "stop": fresh["stop"],
                    "tp1": fresh["tp1"], "tp2": fresh["tp2"]})
    return out


def shadow_purge_tier(tier: str) -> None:
    """Remove a tier's shadow trades entirely (user cut, e.g. sst1)."""
    c = _open()
    try:
        c.execute("DELETE FROM shadow_trades WHERE tier=?", (tier,))
        c.commit()
    finally:
        c.close()


def shadow_closed_all(limit: int = 6000) -> list[dict]:
    """Every closed shadow trade (chronological) — feeds the 💸 SLOT
    REPLAY that bridges desk records to real-account constraints."""
    return _rows(
        "SELECT tier,symbol,side,opened_at,closed_at,pnl_r "
        "FROM shadow_trades WHERE status='CLOSED' "
        "ORDER BY opened_at LIMIT ?", (limit,))


def shadow_recent_net(tier: str, days: float = 14.0) -> dict:
    """{n, net_r} of CLOSED trades for one tier in the last `days` —
    the recency leg of the green-light gate (a tier bleeding recently
    must not keep its voice on lifetime glory)."""
    cutoff = time.time() - days * 86400
    c = _open()
    try:
        row = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_r),0) FROM shadow_trades "
            "WHERE tier=? AND status='CLOSED' AND closed_at>=?",
            (tier, cutoff)).fetchone()
        return {"n": int(row[0] or 0), "net_r": float(row[1] or 0.0)}
    finally:
        c.close()


def shadow_recent(limit: int = 30) -> list[dict]:
    return _rows(
        "SELECT * FROM shadow_trades WHERE status='CLOSED' "
        "ORDER BY closed_at DESC LIMIT ?", (limit,))


def seen_between(stream: str, symbol: str, side: str,
                 ts_from: float, ts_to: float) -> bool:
    """True if this (stream, symbol, side) was recorded in [ts_from, ts_to).
    Used for 🌱 freshness: a setup is a FIRST FIRE when it has no record in
    the trailing window (excluding the current sighting streak)."""
    c = _open()
    try:
        row = c.execute(
            "SELECT COUNT(*) FROM signals WHERE stream=? AND symbol=? "
            "AND side=? AND ts>=? AND ts<?",
            (stream, symbol, side, ts_from, ts_to)).fetchone()
        return bool(row and row[0] > 0)
    finally:
        c.close()

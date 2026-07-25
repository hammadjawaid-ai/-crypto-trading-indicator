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
                stop: float, tp1: float, tp2: float) -> None:
    c = _open()
    try:
        c.execute(
            "INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,"
            "tp1,tp2,peak,opened_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tier, symbol, side, entry, stop, stop, tp1, tp2, entry,
             time.time()))
        c.commit()
    finally:
        c.close()


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

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

DB_PATH = os.environ.get(
    "WORKER_DB_PATH", str(Path(__file__).with_name(".worker.db")))

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
        "SELECT ts,stream,base,side,tier,score,conviction,hot,atr_pct,"
        "entry,stop,tp1,tp2 FROM signals ORDER BY id DESC LIMIT ?", (limit,))


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

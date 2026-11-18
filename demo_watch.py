"""🕐 The demo's watcher: a pass every 5 minutes over one-minute candles (user 2026-11-18: "closing when tp is hit
is slow on the demo trading can we fasten that for accuracy" · "switch it to 5-10 mints").

The worker's cycle takes 17–20 minutes and used to be the only moment the demo looked at price, so a TP1 or a stop
was booked up to a cycle late, and a wick between two cycles was never seen at all (the MVLL star of 17 Nov: the
demo banked TP1 although a one-minute wick had taken the stop). This thread wakes every PERIOD_S seconds, and when
the demo holds a seat it reads the one-minute candles that closed since the seat was last looked at and replays
them through demo_account.walk(), which uses the same exit rules as the cycle (stop, TP1 in full, the near-TP
bank): the bad side of each minute first, then the good side, then the close.

Both writers of the demo book hold demo_account's lock from load to save; when the cycle is inside its own demo
block the watcher skips that minute. Candles come from Binance spot (the server cannot reach the futures host; the
tokenized names trade on spot). Any error skips the minute and is printed; nothing here can stop the worker.
Started once from agent_worker.cycle(). Off: demo_watch.ON = False.
"""
from __future__ import annotations

import threading
import time

ON = True
# every 5 minutes (user 2026-11-18, on seeing the first build at 60 s: "no switch it to 5-10 mints"). Each pass
# still replays the ONE-MINUTE candles closed since the last one, so a close keeps its exact level and minute.
PERIOD_S = 300.0
_started = [False]
LAST: dict = {"ts": 0.0, "seats": 0, "events": 0, "error": ""}      # for the worker's log / a status line


def klines_1m(symbol: str, start_ts: float) -> list:
    """[(open_ts, high, low, close)] one-minute candles from start_ts, oldest first (the last may be forming)."""
    import binance_client as bc
    raw = bc._get("/api/v3/klines", {"symbol": symbol, "interval": "1m",
                                     "startTime": int(max(0.0, float(start_ts)) * 1000), "limit": 500},
                  max_attempts=2)
    return [(int(x[0]) // 1000, float(x[2]), float(x[3]), float(x[4])) for x in (raw or [])]


def tick(now=None, klines_fn=None) -> list:
    """One pass. Returns the events of demo_account.walk ([] when there is nothing to do or the book is busy)."""
    import demo_account as da
    if not ON or not da.lock(timeout=2.0):
        return []
    try:
        st = da.load()
        n = len(st.get("open") or [])
        LAST.update(ts=time.time(), seats=n, events=0, error="")
        if not n:
            return []
        before = [(p.get("symbol"), p.get("walk_ts")) for p in st["open"]]
        ev = da.walk(st, klines_fn or klines_1m, now)
        if ev or before != [(p.get("symbol"), p.get("walk_ts")) for p in st.get("open") or []]:
            da.save(st)
        LAST["events"] = len(ev)
        return ev
    finally:
        da.unlock()


def _loop() -> None:
    while True:
        try:
            for kind, rec in tick():
                try:
                    print(f"[demo-watch] {kind} {rec.get('base')} {rec.get('side')} · {rec.get('reason')} · "
                          f"{float(rec.get('pnl') or 0):+.2f}$", flush=True)
                except Exception:
                    pass
        except Exception as exc:
            LAST["error"] = str(exc)[:200]
            print("  demo watch error:", exc, flush=True)
        time.sleep(PERIOD_S)


def start() -> bool:
    """Start the watcher thread once per process. True when this call started it."""
    if _started[0] or not ON:
        return False
    _started[0] = True
    threading.Thread(target=_loop, name="demo-watch", daemon=True).start()
    return True

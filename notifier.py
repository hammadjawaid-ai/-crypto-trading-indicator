"""Desktop alert notifier — a standalone background watcher for the Crypto
Trading Indicator.

Leave this running in its own console window and it fires REAL Windows
desktop notifications whenever a new high-confidence setup or volume surge
appears — no browser, no dashboard tab needed.

    .venv\\Scripts\\python.exe notifier.py            # 4h, every 5 minutes
    .venv\\Scripts\\python.exe notifier.py 1h 3       # 1h, every 3 minutes

or just double-click  notifier.bat.

It re-uses the dashboard's own signal engine (signals.py + alerts.py), so
the calls match the Market Scanner. To stay light it skips only the social
feed; technicals and derivatives are fully included. Stop it with Ctrl+C.

Local machine only — this is a background process, so it cannot run on the
Streamlit Cloud deploy.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

import alerts
import binance_client
import config
import derivatives
import signals

try:
    from winotify import Notification, audio
except ImportError:
    print("The 'winotify' package is required for desktop notifications.\n"
          "Install it once with:\n"
          "    .venv\\Scripts\\python.exe -m pip install winotify")
    sys.exit(1)

APP_ID = "Crypto Trading Indicator"
STATE_FILE = Path(__file__).with_name(".notifier_seen.json")

# Defaults — overridable on the command line:  notifier.py [timeframe] [minutes]
TIMEFRAME = "4h"
INTERVAL_MIN = 5
TOP_N = config.TOP_N
MODE = "futures"


def _notify(title: str, message: str) -> None:
    """Fire one Windows desktop notification — never let it kill the loop."""
    try:
        toast = Notification(app_id=APP_ID, title=title, msg=message)
        try:
            toast.set_audio(audio.Default, loop=False)
        except Exception:
            pass
        toast.show()
    except Exception as exc:
        print(f"  (notification failed: {exc})")


def _scan(symbols: list[str]) -> pd.DataFrame:
    """Scan symbols with the dashboard's signal engine — no Streamlit."""
    try:
        funding = derivatives.all_funding_rates()
    except Exception:
        funding = {}

    def one(sym: str):
        try:
            df = binance_client.get_klines(sym, TIMEFRAME)
            rate = funding.get(sym)
            deriv = {"funding": rate} if rate is not None else None
            res = signals.analyze(df, deriv, None, MODE)
            res["symbol"] = sym
            return res
        except Exception:
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for res in pool.map(one, symbols):
            if res:
                rows.append(res)
    return pd.DataFrame(rows)


def _load_seen() -> set[str]:
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set[str]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(sorted(seen)))
    except Exception:
        pass


def _current_alerts(data: dict) -> dict[str, dict]:
    """Map every live alert to a stable id -> {kind, payload}."""
    out: dict[str, dict] = {}
    for s in data["setups"]:
        out[f"{s['symbol']}:{s['side']}"] = {"kind": "setup", "a": s}
    for s in data["surges"]:
        out[f"vol:{s['symbol']}"] = {"kind": "surge", "a": s}
    return out


def run() -> None:
    print("=" * 64)
    print("  Crypto Indicator - desktop alert notifier")
    print(f"  Timeframe {TIMEFRAME} - scanning every {INTERVAL_MIN} min - "
          f"top {TOP_N} coins")
    print("  Leave this window open. Stop with Ctrl+C.")
    print("=" * 64)

    seen = _load_seen()
    first_run = (not STATE_FILE.exists()) or (not seen)

    while True:
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            tickers = binance_client.get_top_symbols(TOP_N)
            scan = _scan(list(tickers["symbol"]))
            if not scan.empty:
                merged = scan.merge(
                    tickers[["symbol", "priceChangePercent", "quoteVolume"]],
                    on="symbol", how="left")
            else:
                merged = scan
            data = alerts.build_alerts(merged, TIMEFRAME)
            current = _current_alerts(data)
            new_ids = [i for i in current if i not in seen]
            print(f"[{stamp}] {len(data['setups'])} setup(s), "
                  f"{len(data['surges'])} surge(s) - {len(new_ids)} new")

            if first_run:
                _notify(
                    "Crypto Indicator — watching the market",
                    f"{len(data['setups'])} setup(s) and "
                    f"{len(data['surges'])} surge(s) live on {TIMEFRAME}. "
                    f"You'll be alerted when a new one appears.")
                first_run = False
            else:
                for alert_id in new_ids:
                    item = current[alert_id]
                    a = item["a"]
                    if item["kind"] == "setup":
                        word = "BULLISH" if a["side"] == "LONG" else "BEARISH"
                        _notify(
                            f"{a['base']} — {word} setup",
                            f"{a['confidence']}% confidence · R:R "
                            f"{a['rr']:.1f} · {TIMEFRAME} timeframe")
                    else:
                        _notify(
                            f"{a['base']} — volume surge",
                            f"Volume {a['vol_ratio']:.1f}x its average · "
                            f"{TIMEFRAME} timeframe")
                    print(f"           -> alerted: {alert_id}")

            # Store exactly the current set, so a coin that drops off and
            # later returns will alert again.
            seen = set(current)
            _save_seen(seen)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[{stamp}] scan error: {exc} — retrying next cycle")

        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        TIMEFRAME = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            INTERVAL_MIN = max(1, int(sys.argv[2]))
        except ValueError:
            pass
    try:
        run()
    except KeyboardInterrupt:
        print("\nNotifier stopped — no more desktop alerts.")

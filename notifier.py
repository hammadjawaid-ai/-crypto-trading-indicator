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
import forecast as fc_mod
import signals

try:
    from winotify import Notification, audio
except ImportError:
    print("The 'winotify' package is required for desktop notifications.\n"
          "Install it once with:\n"
          "    .venv\\Scripts\\python.exe -m pip install winotify")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None    # phone push disabled if requests isn't installed

APP_ID = "Crypto Trading Indicator"
STATE_FILE = Path(__file__).with_name(".notifier_seen.json")

# Defaults — overridable on the command line:  notifier.py [timeframe] [minutes]
TIMEFRAME = "4h"
INTERVAL_MIN = 5
TOP_N = config.TOP_N
MODE = "futures"


def _notify_phone(title: str, message: str,
                  priority: str = "default") -> None:
    """Push one alert to the user's phone via ntfy.sh — free, no signup.

    Only fires if NTFY_TOPIC is set in .env / Streamlit secrets. Failures
    never kill the loop. Priority is one of: min, low, default, high,
    urgent — PREMIUM setups use 'high' so they ring through Do Not Disturb
    on most phones."""
    topic = (config.NTFY_TOPIC or "").strip()
    if not topic or requests is None:
        return
    try:
        url = f"https://ntfy.sh/{topic}"
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": "chart_with_upwards_trend",
        }
        requests.post(url, data=message.encode("utf-8"),
                      headers=headers, timeout=5)
    except Exception as exc:
        print(f"  (phone push failed: {exc})")


def _notify(title: str, message: str, *, premium: bool = False) -> None:
    """Fire one Windows desktop notification AND a phone push if configured.

    `premium` flips both channels into high-priority mode and prefixes the
    title with the 🏆 trophy so PREMIUM-tier setups stand out at a glance.
    """
    if premium:
        title = f"🏆 PREMIUM — {title}"
    try:
        toast = Notification(app_id=APP_ID, title=title, msg=message)
        try:
            toast.set_audio(audio.Default, loop=False)
        except Exception:
            pass
        toast.show()
    except Exception as exc:
        print(f"  (notification failed: {exc})")
    _notify_phone(title, message,
                  priority="high" if premium else "default")


# --- PREMIUM-tier detection ------------------------------------------------
# Cache the per-coin per-tf analyze results within a single scan so the
# 15m + 1h + 4h forecast runs at most once per symbol per loop iteration.
_PREMIUM_TFS = ("15m", "1h", "4h")


def _is_premium(symbol: str, side: str, scanner_conf: int,
                cache: dict) -> bool:
    """A setup is PREMIUM when scanner conf >= 80 AND the multi-horizon
    forecast aligns 3/3 in the same direction as the setup. Same
    definition the Paper Trader dashboard uses for the 🏆 PREMIUM badge."""
    if scanner_conf < 80:
        return False
    if symbol in cache:
        fc = cache[symbol]
    else:
        per_tf: dict[str, dict] = {}
        for tf in _PREMIUM_TFS:
            try:
                df = binance_client.get_klines(symbol, tf)
                per_tf[tf] = signals.analyze(df, None, None, MODE)
            except Exception:
                return False
        try:
            fc = fc_mod.predict_one(per_tf, None, None)
        except Exception:
            return False
        cache[symbol] = fc
    if not fc.get("aligned"):
        return False
    word = fc.get("outlook_word")
    return ((side == "LONG" and word == "Bullish")
            or (side == "SHORT" and word == "Bearish"))


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
    if (config.NTFY_TOPIC or "").strip():
        print(f"  Phone push: ntfy.sh topic = "
              f"{config.NTFY_TOPIC[:3]}...{config.NTFY_TOPIC[-3:]} "
              f"(install ntfy app, subscribe to the full topic)")
    else:
        print("  Phone push: DISABLED (set NTFY_TOPIC in .env to enable)")
    print("  PREMIUM tier (conf>=80 + forecast 3/3) marked with trophy + "
          "high-priority phone push.")
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
                # Premium-forecast cache scoped to this iteration only.
                _fc_cache: dict = {}
                for alert_id in new_ids:
                    item = current[alert_id]
                    a = item["a"]
                    if item["kind"] == "setup":
                        word = "BULLISH" if a["side"] == "LONG" else "BEARISH"
                        # Check the PREMIUM tier (conf >= 80 + forecast 3/3).
                        premium = _is_premium(
                            a["symbol"], a["side"],
                            int(a.get("confidence") or 0), _fc_cache)
                        _notify(
                            f"{a['base']} — {word} setup",
                            f"{a['confidence']}% confidence · R:R "
                            f"{a['rr']:.1f} · {TIMEFRAME} timeframe",
                            premium=premium)
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

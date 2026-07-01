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

import config
import scan_core
import telegram_notify as tg
import worker_store as store

INTERVAL = max(1, int(getattr(config, "WORKER_INTERVAL_MIN", 5))) * 60
COOLDOWN = max(1, int(getattr(config, "WORKER_ALERT_COOLDOWN_MIN", 360))) * 60
MIN_CONV = float(getattr(config, "WORKER_SST1_MIN_CONV", 70))


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


def cycle() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    r = scan_core.scan_all(scan_n=60, min_conv=MIN_CONV)
    sst1, takenow = r["sst1"], r["takenow"]
    regime = (r.get("regime") or {}).get("regime", "?")

    # Store every best-signal this cycle (history for pattern analysis).
    for p in sst1:
        store.record_signal("sst1", p)
    for p in takenow:
        store.record_signal("takenow", p)

    # Alert — TAKE NOW 🔥 first (most urgent), then SST1. Cooldown-deduped.
    n_alerts = 0
    for p in takenow:
        if store.should_alert(f"takenow:{p['symbol']}:{p['side']}", COOLDOWN):
            ok, msg = tg.send(_fmt_takenow(p))
            n_alerts += 1 if ok else 0
            if not ok:
                print("  tg:", msg, flush=True)
    for p in sst1:
        if store.should_alert(f"sst1:{p['symbol']}:{p['side']}", COOLDOWN):
            ok, msg = tg.send(_fmt_sst1(p))
            n_alerts += 1 if ok else 0
            if not ok:
                print("  tg:", msg, flush=True)

    store.record_cycle(regime, len(sst1), len(takenow), n_alerts)
    print(f"[{stamp}] regime={regime} · SST1≥{MIN_CONV:.0f}={len(sst1)} · "
          f"TAKE_NOW+HOT={len(takenow)} · alerts_sent={n_alerts}", flush=True)


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

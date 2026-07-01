"""Always-on entrypoint — the WHOLE app 24/7 with a background brain.

Runs on Render/Railway as ONE always-on web service:
  1. a background BRAIN thread that scans + notifies + remembers around the
     clock, INDEPENDENT of any browser session (this is what makes the app
     alive even when nobody's looking), and
  2. the full Streamlit app as the web UI on $PORT.

They share the host disk (set STATE_DIR to the mounted volume) so state is
live memory that survives redeploys. Start command:  python launch.py

The brain thread never calls Streamlit APIs — it only scans, writes to the
store, and pushes Telegram — so it's safe to run outside a script context.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback


def _brain() -> None:
    # Let Streamlit bind the port first so the service passes its health
    # check quickly; the brain's first scan is heavy (~30-60s).
    time.sleep(15)
    import agent_worker
    try:
        import telegram_notify as tg
        if tg.enabled():
            tg.send("🟢 *App online 24/7* — the brain is scanning in the "
                    "background. Alerts: ✅🔥 TAKE NOW HOT · 💠 SST1 conv≥70 · "
                    "🏆 leaderboard.", silent=True)
    except Exception:
        pass
    print("[brain] 24/7 loop started "
          f"(every {agent_worker.INTERVAL // 60} min)", flush=True)
    while True:
        try:
            agent_worker.cycle()
        except Exception as exc:
            print("[brain] cycle error:", exc, flush=True)
            traceback.print_exc()
        time.sleep(agent_worker.INTERVAL)


def main() -> None:
    threading.Thread(target=_brain, daemon=True).start()
    port = os.environ.get("PORT", "8501")
    cmd = [sys.executable, "-m", "streamlit", "run", "app.py",
           "--server.port", port,
           "--server.address", "0.0.0.0",
           "--server.headless", "true",
           "--server.enableCORS", "false",
           "--server.enableXsrfProtection", "false",
           "--browser.gatherUsageStats", "false"]
    print("[launch] starting Streamlit UI on port", port, flush=True)
    import subprocess
    subprocess.run(cmd)


if __name__ == "__main__":
    main()

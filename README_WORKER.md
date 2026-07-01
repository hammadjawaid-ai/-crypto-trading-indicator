# 24/7 Signal Worker — setup (Telegram alerts, always-on)

This runs your signal engine **24/7 in the cloud**, independent of your laptop
or any open browser. It scans on a timer, **stores every best-signal**, and
pushes only the cream to your phone via Telegram:

- ✅🔥 **TAKE NOW HOT** — an ELITE MAX/HIGH setup that pulled back, confirmed,
  and is firing with elevated ATR (the validated higher-edge entry).
- 💠 **SST1 conv ≥ 70** — the proven ~72% tier.

It also serves a **live web dashboard** at your own public URL — open it in any
browser, on any device, 24/7, to see the latest setups, the alerts it pushed,
and the scan history. Telegram is the buzz; the page is your window.

It is **alert-only** — it does **not** place any trades. Nothing touches your
Bybit money.

---

## Step 1 — Create a Telegram bot (2 min)
1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, pick a name and a username. BotFather replies with a
   **token** like `123456789:AAH...` — copy it. That's `TELEGRAM_BOT_TOKEN`.

## Step 2 — Get your chat ID (1 min)
1. Open a chat with your new bot and send it any message (e.g. "hi").
2. In Telegram, open a chat with **@userinfobot** and send `/start` — it
   replies with your numeric **Id**. That's `TELEGRAM_CHAT_ID`.
   *(Alternative: visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a
   browser after messaging your bot, and read `chat.id`.)*

## Step 3 — Deploy the service (Render, ~$7/mo, easiest)
1. Push this repo to GitHub (already done).
2. On **render.com** → **New +** → **Blueprint** → select this repo. Render
   reads `render.yaml` and creates a **Web Service** (one always-on service
   that runs the scan loop **and** serves the dashboard).
3. In the service's **Environment**, set the two secrets:
   ```
   TELEGRAM_BOT_TOKEN = 123456789:AAH...
   TELEGRAM_CHAT_ID   = 987654321
   ```
   (If your scan uses any API keys — e.g. `LUNARCRUSH_API_KEY` — add them too.
   None are required for the core SST1 / TAKE NOW streams.)
4. **Create** → it builds and starts. Render gives you a public URL like
   `https://crypto-signal-worker.onrender.com` — **that's your dashboard.**
   The `render.yaml` mounts a 1 GB disk at `/var/data` so history survives
   redeploys.

### Railway alternative
New Project → Deploy from GitHub → it detects the **Procfile**
(`worker: python agent_worker.py`). Add the same env vars under **Variables**.
Add a Volume if you want persistent history.

## Step 4 — Verify it's live
- **Open your Render URL in a browser** (e.g.
  `https://crypto-signal-worker.onrender.com`) — you'll see the dashboard:
  last-scan time, regime, latest best setups, alerts pushed, and scan history.
  It auto-refreshes every 60s. Bookmark it on your phone's home screen and it
  works like an app.
- Within a minute you should also get a Telegram message: **"🟢 24/7 worker
  online"**. That confirms the phone-push pipe.
- In Render **Logs** you'll see a line each cycle, e.g.
  `regime=BEAR · SST1≥70=1 · TAKE_NOW+HOT=0 · alerts_sent=0`.
- Real alerts arrive only when something clears the bar — by design that's
  selective (often <1/day for SST1). Quiet ≠ broken.

---

## Tuning (optional env vars)
| Var | Default | Meaning |
|---|---|---|
| `WORKER_INTERVAL_MIN` | 5 | minutes between scans |
| `WORKER_ALERT_COOLDOWN_MIN` | 360 | don't re-alert the same setup within this window |
| `WORKER_SST1_MIN_CONV` | 70 | SST1 conviction bar to alert |
| `WORKER_DB_PATH` | `/var/data/worker.db` | where the SQLite history lives |

## What it stores (for later pattern/behaviour analysis)
`worker.db` (SQLite) keeps a `signals` row for every best-signal each cycle,
an `alerts_sent` dedup ledger, and a `cycles` summary. That's the raw history
we'll mine later to study which setups actually worked.

## Honest limits
- **Alert-only** for now — proving the alerts live is Phase 1. Auto-execution
  on Bybit (with hard rails) is a separate, later switch-on once the alerts
  are shown to be as good live as they backtested.
- Telegram push needs the worker running (it is, 24/7) — but if the host
  itself is down, no alerts. Render/Railway restart workers automatically on
  crash, and the loop also catches its own errors and retries next cycle.

# Your whole app, running 24/7 (Render) — setup

This puts your **entire app on an always-on server** with a **background brain**
that scans, alerts, and remembers **around the clock** — even when no browser
is open. The webpage becomes a live window into something already running, not
a thing that only computes when you open it.

**One Render web service runs two things together (`launch.py`):**
1. **The brain** — a background thread that scans every few minutes,
   independent of any browser, stores everything, and pushes only the best to
   your phone via Telegram:
   - ✅🔥 **TAKE NOW HOT** — ELITE MAX/HIGH, pulled back + confirmed + firing.
   - 💠 **SST1 conv ≥ 70** — the proven ~72% tier.
   - 🏆 **Leaderboard** — the highest-conviction ELITE MAX/HIGH picks (early
     heads-up).
2. **The full Streamlit app** — the exact app you know, served at your own
   public URL, always awake.

State lives on the server's **disk** (`STATE_DIR=/var/data`) so your history
and positions are **live memory that survives redeploys**. Still **alert-only**
— no trades are placed.

---

## Step 1 — Create a Telegram bot (2 min)
1. Open **@BotFather** in Telegram → send `/newbot` → pick a name + a username
   ending in `bot`.
2. Copy the **token** it gives you → that's `TELEGRAM_BOT_TOKEN`.
3. Open your new bot, press **Start**, send it "hi".

## Step 2 — Get your Chat ID (1 min)
- Open **@userinfobot** → it replies with your numeric **Id** →
  that's `TELEGRAM_CHAT_ID`.
- (Browser alternative: after messaging your bot, open
  `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and read `chat.id`.)

## Step 3 — Deploy the whole app on Render
1. On **render.com** → **New +** → **Blueprint** → select this repo. Render
   reads `render.yaml` and creates a **Web Service** running `python launch.py`
   (full app + brain), with a 1 GB disk for live memory.
2. Set the secret env vars in the service's **Environment**:
   ```
   TELEGRAM_BOT_TOKEN = 123456789:AAH...
   TELEGRAM_CHAT_ID   = 987654321
   ```
   Optional (fail-soft if absent): `ANTHROPIC_API_KEY`, `LUNARCRUSH_API_KEY`,
   and your Bybit keys if/when you go live.
3. **Create.** Render builds and starts it, and gives you a public URL like
   `https://crypto-indicator-24-7.onrender.com` — **that URL is your app.**

> **Plan:** the blueprint uses **standard** (2 GB RAM) because the full app +
> scanning needs headroom. You can try **starter** to save money, but if it
> restarts under load, bump it back to standard.

## Step 4 — Verify
- **Open your Render URL** — it's your full dashboard, always awake. Bookmark
  it to your phone's home screen and it behaves like a native app.
- **Phone:** within ~1 min you get a Telegram **"🟢 App online 24/7"** message.
- **Logs** (Render dashboard) show a brain line each cycle, e.g.
  `regime=BEAR · SST1≥70=1 · TAKE_NOW+HOT=0 · LB≥85=1 · alerts_sent=0`.
- Alerts are **selective** — often nothing for a while, then a real one. Quiet
  is the system working, not broken.

---

## Tuning (optional env vars)
| Var | Default | Meaning |
|---|---|---|
| `WORKER_INTERVAL_MIN` | 5 | minutes between brain scans |
| `WORKER_ALERT_COOLDOWN_MIN` | 360 | don't re-alert the same setup within this window |
| `WORKER_SST1_MIN_CONV` | 70 | SST1 conviction bar to alert |
| `WORKER_LEADERBOARD_MIN_SCORE` | 85 | leaderboard score bar to alert |
| `STATE_DIR` | `/var/data` | durable disk for DB + state (live memory) |

## What this is (and isn't) — honest
- ✅ **Phase A (this):** whole app always awake + 24/7 brain (scanning, alerts,
  memory on disk). The browser is now a window into a live system.
- ⏳ **Phase B (next):** move the boards + paper-position stop/target checks
  into the brain so the app shows continuously-maintained state instantly and
  trades are managed even with the browser closed.
- ⏳ **Phase C:** outcome memory — track which signals actually hit TP vs SL so
  the agent learns what's working and surfaces the positive patterns.
- **Alert-only** throughout — auto-execution on Bybit stays a separate, later,
  rails-guarded switch-on once the alerts are proven live.

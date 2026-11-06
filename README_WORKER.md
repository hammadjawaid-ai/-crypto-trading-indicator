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

## 📡 CHANNEL DESK (2026-11-05) — outside Telegram signal channels, measured forward

`channel_desk.py` reads posts from outside signal channels (Crypto Andrew VIP → demo **v2**, Crypto Cycle VIP → demo
**v3**), parses each signal (coin · side · entry · targets · stop · leverage), runs it in that channel's own $1,000 demo
book at the channel's own rule (2% margin × stated leverage, 50% off at TP1 → stop to entry, 25% at TP2, rest TP3 / 48h),
judges it on the 15m candle path (liquidation first, then the stop, then the targets) and rings a 📡 bell with our stamp
and the 🚦 light (⚪ UNRATED until 60 forward trades resolved, then 🟢 TAKE / 🟡 / 🔴 SKIP). Own state file
`.channel_desk.json` on STATE_DIR; never touches GEN 18 or any desk tier. Switch: `channel_desk.TG_CHANNEL_DESK`.

Reader — pick ONE, set in Render's environment (never paste values into chat):

| mode | env | how |
|---|---|---|
| user session (recommended) | `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` | my.telegram.org → API development tools → app → id + hash. Then on your PC (VPN on): `research_meta\.venv\Scripts\python.exe research_meta\tg_pull.py --session` → logs in with your phone + code once and prints the `TG_SESSION` string. Reads any channel your account is in, admin or not. |
| bot relay group | `CHANNEL_RELAY_CHAT_ID` | a private group with the bot inside; forward the channel's posts into it. The forward header names the source channel. |
| drop file | — | `<STATE_DIR>/.channel_inbox.jsonl`, one JSON per line `{channel, id, ts, text, reply_text}` (tests / manual). |

Without any of these the worker logs `channel desk reader OFF` and the books stay empty. Guard test: `.channel_desk_test.py`.

## 🧹 LEDGER HYGIENE (2026-11-05 / floor raised 2026-11-06) — thin-stop seats voided

Before the 17 Sep open guard (`shadow_trader.open_from_signal`, commit a2c949a) the desk seated
trades whose stop sat <0.1% from entry. `pnl_r` divides by that near-zero risk, so a routine move
booked as −717R (XTZ LONG, 9 Sep) and landed on five tiers at once. The 4 Nov ledger held 120 such
rows, −3,961R of accounting noise; apex's desk light read −0.10R per trade when its clean record is
+0.10R (one_trade, fast30, ignition_strong, conviction_v2 flipped the same way).

- 2026-11-06 (user: "this should deploy first"): the floor is **0.3%** (`worker_store.MIN_RISK_FRAC`),
  not 0.1%. The 0.1–0.3% band had the same defect pointing up — 434 rows, +645R, mean +1.5R, single
  rows of +65R on best_board / early_movers / early_lane and +47R on apex; fees alone cost ≥0.4R on
  such a stop, so it is not a tradeable plan. 554 rows VOID in all (−3,316R). The desk's open guard
  reads the same constant, so the desk no longer seats a plan whose stop is closer than 0.3%.
- On the worker's FIRST CYCLE (`agent_worker.cycle()`, flag `_HYGIENE_DONE` — Render's launch.py loops
  cycle() and never enters main(); the 45ce814 deploy restarted without sweeping, fixed the same day)
  `worker_store.shadow_void_degenerate()` marks those rows `status='VOID'` (idempotent; the log line says
  how many moved). Nothing is deleted — reverse with
  `UPDATE shadow_trades SET status='CLOSED' WHERE status='VOID'`.
- Every record reader filters `status='CLOSED'` (the six `!= 'OPEN'` readers in worker_store were
  switched), so VOID rows sit in no summary, band, recency gate or page table.
- Clean records at the 0.3% floor (4 Nov backup): apex −0.10R → +0.085R (3,830), one_trade −0.36 → +0.14,
  fast30 −0.09 → +0.12, ignition_strong −1.04 → +0.19, conviction_v2 −0.53 → +0.26; kr_strong +248R → +109R,
  elite_conv +408R → +324R, best_board +155R → +112R (their thin-stop winners were noise too).
- The Decision Desk prints a 🧹 caption naming the voided count and R.
- Guard: `.desk_hygiene_test.py` (runs the sweep on a copy of `.state_backup_1104/worker.db`).

## 💯↩️ CONVICTION v2 REVERSED (2026-11-06) — the mirror experiment, records only

User: "reverse the signals with it — if it says tp it should be considered as sl and sl should be
considered as tp — only for this one, nothing else." Every 💯 CONVICTION v2 fire is now ALSO seated the
other way on the desk, tier `conviction_v2_rev` (`shadow_trader.mirror_signal`): the opposite side at the
same live price, the plan's TP1 as the stop, the plan's stop as TP1, TP2 dropped, the normal desk ladder
after that. conf / heat carry over from the original fire. No bell, no demo seat; the original
`conviction_v2` ledger is untouched. Nothing else is mirrored.

Why the card read −458R: two zero-risk rows (−721R) — the hygiene sweep above. Clean, v2 is +0.26R per
trade at the 0.3% floor (36% win). Replay of the 886 clean closed v2 trades on the 15m candle path
(`research_meta/conv_rev_study.py`, 25 Aug → 4 Nov): mirror with the desk ladder 61% / +0.20R (867; both
halves +0.10 / +0.30, every month positive), the plain mirror without the ladder −0.01R (the mirror's R is
the trail after the fire fails, not the flip itself), mirror of LONG fires +0.31R (618) vs mirror of SHORT
fires −0.07R (249), clipped ±5R mean +0.08R (tail-carried). The same ruler scores the ORIGINAL at only
+0.07R against the ledger's +0.28R — the desk judges on cycle prices and is ~0.2R kinder than bars — so
the two forward desk records are the only fair comparison. Guard: `.conv_rev_test.py` (22 checks).

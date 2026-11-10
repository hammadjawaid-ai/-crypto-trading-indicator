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

## 🔁 TAKE NOW RESTORE (2026-11-06) — the silent streams brought back

From 4 Oct 17:14 PKT the kline cache served a shorter request from the tail of a longer cached frame
(f06f526, page speed). entry_timing's TAKE_NOW confirm needs the forming candle to close strictly beyond the
plan entry, and the plan entry is the scanner frame's last close — served the same frame they were equal, so
TAKE_NOW fell from ~40/day to ~2/week and every stream that needs it went silent: ✅🔥 TAKE NOW HOT,
🏆 TOP CONVICTION, 🚀 EARLY LANE, ⚡ EARLY MOVERS, 🌱 FRESH, 🌟 EARLY ELITE (and 💎 BEST starved).
Fix: `binance_client.get_klines(..., fresh=True)` takes its own snapshot (the exact-key 120 s cache still
applies); only `entry_timing.entry_signal` uses it — the behaviour every one of those records was measured on.
Everything else keeps the reuse. Guard: `.takenow_restore_test.py`. Same commit: the 🏆💎 APEX V2 GATED 1H
verdict reply was an `elif` chained to `if TG_RULES:` and never ran; it is now its own branch ahead of it.

## ⭐ STAR BELL RE-SET (2026-11-07) — one bell, one verb, one size

User: "it gets confusing to take a trade or not … we have gated and ungated elite star notifications."
- The 13–17 PKT ungated exception is OFF (`STAR_UNGATED_1317 = False`): one gate in every window. Gated 13–17
  stars 50% / −0.15R (22) vs muted 65% / +0.25R (37) — thin and contradictory; the window is decided at 60 fires.
- Header: `⭐ ELITE STAR — COIN SIDE · TAKE · full|half|small · HH:MM PKT`. The size word is the 🕐 clock cell's
  light (🟢 full · 🟡 half · 🔴 small), so the header and the clock line never disagree; a 👑 ONE TRADE beside
  the fire halves it (gated stars 53% / +0.16R with one vs +0.43R without).
- A partner line names a ✅🔥 TAKE NOW HOT / 💥 STRONG TRIGGER / 🥇 PRIME fire within 2h of the star
  (`worker_store.streams_between`): gated stars with TAKE NOW HOT 84% / +0.82R (25), with a strong trigger
  81% / +0.62R (27), 9 Sep → 4 Nov, thin.
- Off the fire card: the window-record and stamp lines (they duplicated the clock cell) and the GO-timing line
  (a future-state stat; it stays on the GO bells). Kept: plan, 🎯 bank zone, chips, the rule, the next line, Kronos.
- The standalone ⭐⚡/💎⚡ GO REVIVED bell rings only for fires the phone rang. Entered at the GO it measured
  54% / −0.07R FAST, 55% / −0.03R LATE (6 Oct → 4 Nov); a hold read for a seat you do not have is noise.
  Revivals of un-rung fires keep their board card and the go_revived ledger. 💎⚡ GO LIVE (TG_GO_LIVE) untouched.
- Guard: `.star_bell_test.py` (22 checks); `.clock_cells_test.py` updated to the new law.

## 🔔 BELL RE-SET, part 2 (2026-11-07) — concise cards, ⭐ pair bells, the page

User: "lets build it and deploy … concise and straight to the point … we are muting the 90% bank notification".
- Every card is short: ⭐ star fire ≤ 7 lines (header with TAKE + size · the read's ticks · the clock cell ·
  plan with the 🎯 bank chip · with-line partners/conf/heat · next · Kronos), ⏱ verdict 2 lines, GO 3 lines,
  💎 CONVICTION REVIVAL 4 lines, pair cards 4 lines, 🏆💎 APEX V2 GATED 4 lines + 2-line verdict, 💥🥇 PRIME ×
  STRONG TRIGGER 4 lines, ⚡🔮 KR-STRONG PREMIUM 3 lines, 🏦 TP1 HIT 2 lines, 💎🏆 A-GRADE banner 2 lines, the
  🔮 Kronos line one glance (`🔮 ✅ UP +2.1%`). Records moved to the page.
- ⭐🤝 three new pair bells, each its own card + records-only desk tier seated at the second fire:
  ⭐💥 STAR × STRONG TRIGGER (`star_trig`, 71% / +0.18R entered over 77, both halves), ⭐✅🔥 STAR × TAKE NOW
  HOT (`star_takenow`, 65% / +0.39R over 31, Sep only — thin), ⭐🏆² STAR × APEX V2 (`star_apexv2`, 83% /
  +0.75R over 12 — thin). Switches TG_STAR_TRIG / TG_STAR_TAKENOW / TG_STAR_APEXV2; partner window 2h either
  side of the star (`_pair_partner_ts`, `worker_store.last_between`); ⭐🥇 STAR × PRIME unchanged in rule,
  concise in text.
- ⭐⚡ GO REVIVED standalone bell GONE for stars: a star's DEAD-then-GO is a reply under its own fire bell
  (un-rung stars: board + ledger only). 💎 CONVICTION REVIVAL kept as its own concise card (entered at the GO
  46% / −0.14R FAST, 58% / +0.06R LATE — printed on it). 💎⚡ GO LIVE muted (TG_GO_LIVE; entered ≈ 0R).
- 🎯 90%-of-TP1 ping muted (TG_NEAR90); 🏦 TP1 HIT stays.
- Paper Trader page: hidden boards (records continue) — ELITE CONFIRMED ENTRY, SENTRY, 💯 CONVICTION, PRESSING,
  PRE-BURST, OI LOAD, ARRIVAL T1, 🏆 APEX, 🌱 FRESH, ⚡ EARLY MOVERS (`PT_HIDDEN` in app.py); Decision Desk ACTIVE
  on by default, the bench behind a toggle; new ⭐🤝 STAR PAIRS openable board (four streams); tier labels for
  the three new tiers; Demo header says THE FIVE with the roster history in an expander.
- Guards: `.bells2_test.py` (49), `.star_bell_test.py` (22), `.prime_pair_test.py`, `.agrade_test.py`,
  `.clock_cells_test.py` updated to the new law.

## 🎮 GEN 19 — THE FIVE, GATED (2026-11-07) — the demo book rebuilt on the ≥69% cells

User: "we are going with anything that have the win rate over 69% or above for the timings and you deploy that …
first stream gated elite star, second star x prime, third star x strong trigger, fourth conviction revival, last apex v2 x
elite star … leverage math you are the best so treat it accordingly … fresh account again from 2000 dollars".
- Fresh $2,000 book: `demo_account.cutover_fresh_book` closes the GEN 18 seats at the live price into their archived
  ledger (`demo_gen18_<date>.json` beside the state file), then `load()` starts GEN 19. `cutover_gen18` stays as an alias.
- The roster (`CLASS_W`, in his order): ⭐ ELITE STAR gated on its ≥69% cells · ⭐🥇 STAR × PRIME · ⭐💥 STAR × STRONG
  TRIGGER · 💎 CONVICTION REVIVAL (LATE only, half) · ⭐🏆² STAR × APEX V2. STRONG TRIGGER and PRIME × STRONG TRIGGER
  left the money (bells, tiers, boards go on). Pairs seat at the second fire from the pairing pass (`_DEMO_ST`, `_DEMO_SV2`).
- ⭐ STAR BOOK (`STAR_BOOK` / `star_seat`, clean desk 9 Sep → 4 Nov, held from the fire, the desk ladder; `.gen19_cells`
  in the scratch): LONG 05–09 69% / +0.44R (26) full · 09–13 75% / +0.58R (20) full; 13–17 (27%), 17–21 (62%), 21–01
  (64%) out. SHORT 05–09 71% / +0.33R (17) full · 13–17 73% / +0.21R (11) half · 17–21 79% / +0.60R (33) full, DOUBLE when
  BTC's day ≤ 0 (88% / +0.81R on 26), half when up (43% / −0.17R on 7) · 21–01 77% / +0.51R (13) half; 09–13 out; shorts
  outside heat 40–79 half (78% / +0.50R inside vs 66% / +0.30R). Longs carry no heat rule. The book as one stream: 74% /
  +0.48R (120), halves +0.54 / +0.43, Sep +0.54 · Oct +0.47 · Nov −0.18 (4), 2.2 fires a day. ONE TRADE beside a star
  does not hurt inside these cells — no size-down. The star feed now carries `heat` and `btc_day` for the sizing.
- Leverage math: 10x everywhere. The gated book's widest stop is 6.96%; 10x liquidates near 9.5% (never before a stop),
  15x would liquidate 12% of these trades at its 6.3% line. Conviction is expressed in SEATS: full $100 margin ($1,000
  notional, ~$47 risk at the 4.7% median stop = 2.3% of the bank), half $50, double $200; heat cap 35% unchanged.
- Exit = the desk ladder (`LADDER_SRC`, `TRAIL_R = 1.2`, `LADDER_HOLD_H = 48`): stop → entry at +1R, stop → TP1 when
  TP1 prints (no bank), after TP1 the stop trails the peak by 1.2R, TP2 closes, 48h cuts at live. The cells were measured
  with exactly this; the fade bank (`NEAR_TP_SRC`) and the TP1 bank are off for the five. The ⭐➕ add-on is off
  (`ADDON_SRC`): the whole seat is taken at the fire (the hour-entry add measured ≈ −0.06R in the meta-label lab).
- Page: header `🎮 DEMO $2,000 — GEN 19 · THE FIVE, GATED`, the roster history expander (GEN 17 → 19). Demo bells
  carry the tag `🎮 *DEMO $2,000 GEN19*` and the seat size on the open card.
- Guard: `.demo_gen19_test.py` (book cells, sizing, the ladder on both sides, TP2, 48h, no add-on, cut-over, wiring).
  `.demo_gen18_test.py` is history now (it asserts GEN 18).
- 🎮 GEN 19.1 (user 2026-11-08: "add 17-21 take full longs and 21-01 halves longs"): LONG 17–21 full (62% / +0.38R
  over 48, halves +0.51 / +0.31) and LONG 21–01 half (64% / +0.38R over 39, halves +0.79 / −0.20) join the star book;
  both sit under his 69% line, his call. The book and balance carry on (no cut-over).

## ⭐⚡ GO FAST / LATE reply — the 🕐 clock read and the class line are back, concise (2026-11-07)

User: "for go fast and late we should add the information inside the signal on telegram … concise but dont let go of it".
- `rung_stats.go_text` is five lines: header · plan · ignited/held/entered · 🕐 clock · class. The 🕐 line
  (`clock_cells.go_clock_short`) = the FIRE's window cell for this GO class (⭐⚡ ELITE GO cells for a star, 💎⚡ GO LIVE
  cells for a conviction fire, the revived cells when the hour read DEAD; desk cell, replay fallback, else thin) + where
  the GO is landing with the entered-at-the-bell call (🟢 entry has paid / 🟡 hold only / 🔴 entry lost). The class line
  = `GO_CLASS_SHORT` (the 14 → 28 Sep replay cell: ✅ LONG · FAST 79% / +0.21R per GO entry (77); ⚠️ SHORT; ⚠️ LATE).
- Guard: `.bells2_test.py` (51) checks the five lines.

## 🕐 WINDOW STAMPS ON EVERY BELL (2026-11-08) — `tg_cells.py`

User: "time stamps on every signal and buzz on telegram … green for anything 68% and plus, yellow 60–68, red below
60 … for every stream it should have this inside the information of the signal … we are not changing it to bold
ones that is for later but keep record".
- One module, one rule: `tg_cells.light(win)` = 🟢 ≥ 68% · 🟡 60–68% · 🔴 < 60%; `tg_cells.stamp(stream, key, ts)`
  prints `🕐 🟢 09–13 longs 75% / +0.58R (20) · ⭐ gated stars held from the fire · 9 Sep → 4 Nov` — the fire's 4h PKT
  window, the side (or GO tier, or "both sides" for pooled tables), that stream's own cell, "thin" under 10, "no record"
  when the cell is empty. Tables = the clean desk 9 Sep → 4 Nov (`.tg_timeframes` in the scratch): gated ⭐ star,
  ⏱ LIVE / DEAD stars, the four ⭐🤝 pairs entered at the second fire, 💎🥇 ELITE × PRIME, 🔥🥇 SECOND LEG × PRIME,
  💥🥇 PRIME + strong trigger, 🏆² APEX V2 (every fire), 💎 revival entered at the GO by FAST / LATE, ⭐ revival.
- Where it rides: the ⭐ star card (replaces the old clock line; the header's size word reads the same light),
  the ⏱ verdict reply (LIVE / DEAD cell for stars), the GO reply's 🕐 line (fire cell + landing cell now on the
  68 / 60 lights, "entry pays" when entered ≥ +0.10R else "hold only"), 💎 CONVICTION REVIVAL (its GO class in this
  window), every pair card (`PAIR_STAMP`), 💥🥇 PRIME × STRONG TRIGGER, 🏆💎 APEX V2 GATED and its ⏱🏆 verdict,
  the 🏦 TP1 HIT ping (`stamp_src`, when the fire's stream has a table). Not stamped: 📰 news, 👁 coin watch,
  🎮 demo bells, 📊 scoreboard (no record to print), 💎🏆 A-GRADE (rides the star card; no clean close since 9 Sep).
- A label, never a gate; the roster is unchanged. Guard: `.tg_cells_test.py` (56); `.bells2_test.py` updated (51).

## 🏦 B-STOCKS BACK (2026-11-10) — universe + phone on every stream, money gate still closed

User: "bring B stocks and stock back to the system on elite conviction and rest of the streams should also pick them
up like stars, apex, prime etc". History: 06 Aug let in everywhere → 15 Aug removed ("lost money") → 17 Aug phone on,
then muted the same day and the universe went crypto-only at the source.
- Universe (`binance_client.get_top_symbols`): the top-n CRYPTO by 24h volume, then every name in
  `config.TOKENIZED_STOCKS` with ≥ `BSTOCK_MIN_QV` ($2M) of 24h quote volume appended alongside — coins keep their n
  seats, thin tokenized listings are not scanned. Live shape at the switch: 100 crypto + 19 tokenized (NVDAB, SNDKB,
  SPCXB, SOXLB, CRCLB, MUB, GOOGLB, SKHYB, MSTRB, KORUB, INTCB, QQQB, SOXSB, TQQQB, TSLAB, SNXXB, AMDB, BEB, BMNRB).
  Every caller (scan_all / elite / PRIME / APEX / fast30 / ignition / takenow / moonshot / pre-burst / OI load / the
  page) sees the same list. `config.BSTOCK_IN_UNIVERSE = False` = the crypto-only universe again.
- Phone: `config.BSTOCK_BUZZ = True` → the worker's shared `_bstock_quiet()` returns False, so every bell (💎 elite
  conviction, ⭐ star, 🏆 APEX / APEX V2, 🥇 PRIME and the pairs, 💥 triggers, 🦅 eagle, 👑 one trade, …) rings for
  tokenized names exactly like crypto. Desk tiers, boards and Kronos reads follow automatically (they were only
  starved upstream).
- Set: 13 tickers listed since August added (TQQQB, SOXSB, MRVLB, LITEB, BEB, MRNAB, CRWVB, COHRB, BMNRB, AVGOB,
  SMCIB, BABAB, TSMB) — they had leaked into the crypto ranking untagged. Exact names, never a B-suffix rule (ARB /
  BNB / SHIB / TRB / CKB / DGB are crypto).
- MONEY gate unchanged: `BSTOCK_VALIDATED = False` → no demo / GEN 19 seat for a tokenized name until he says so.
- Honest asterisk stands: every validated edge was measured on crypto; tokenized fires are extrapolation the desk
  records must prove. Guard: `.bstock_restore_test.py` (24).

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
- MONEY gate: opened the same day on his word ("this will be added to the demo trading picking as well") —
  `BSTOCK_VALIDATED = True`, so tokenized names take demo / GEN 19 seats under the same cells as any coin (the
  cells were measured on crypto; the tokenized desk record is the proof). False = no demo seat again.
- Honest asterisk stands: every validated edge was measured on crypto; tokenized fires are extrapolation the desk
  records must prove. Guard: `.bstock_restore_test.py` (24).

## 🏦 TOKENIZED DESK RECORDS, SEPARATELY (2026-11-10)

User: "yes have these for tokenized desk records separately as well" (after the same-day restore and the demo gate).
- `worker_store.shadow_tokenized(symbols, since)`: the desk record of tokenized names only, per tier (all-time,
  since the restore, open) and per stock (since the restore). Clean closes only (VOID thin-stop rows excluded); it
  reads the (symbol, opened_at) index, never the whole ledger. `config.BSTOCK_RESTORED_TS` = 10 Nov 2026 00:00 PKT.
- Phone: every bell that fires on a tokenized name carries one more line (`tg_cells.tok_note`): that stream's own
  record on tokenized names since 10 Nov ("no closes yet" / "n closed, … thin" under 10 / "w% / R (n)"), and the
  reminder that the 🕐 cell above it is crypto-measured. Rides the ⭐ star card, ⏱ verdict, GO replies, 💎 revival,
  the pair cards, 💥🥇, 🏆💎 APEX V2 + verdict, the 🏦 TP1 ping. A coin's card is unchanged. Cached 30 min.
- Page: 🏦 TOKENIZED DESK under the Decision Desk — a headline (closed / win / net R / open since 10 Nov) and an
  expander with each stream's tokenized record since the restore, its all-time tokenized record, the same tier's
  crypto record beside it, and the per-stock line. 10-min cache.
- Guard: `.bstock_restore_test.py` (38), `.tg_cells_test.py` (56).

## 🏦 SPLIT RECORDS (2026-11-11) — a stream's record is crypto-only

User: "for every stream for tokenized stocks we should have the results separately, they should not impact the current
results for the streams ... keep them a split".
- A tokenized seat is recorded under its own desk tier, `tok:` + the stream's tier (`tok:elite_star`, `tok:prime`, ...):
  `worker_store.desk_tier`, applied in `shadow_trader.open_from_signal`. Switch `config.BSTOCK_SPLIT_TIERS`.
- Existing tokenized rows (open seats included) are relabelled once per worker start by
  `worker_store.shadow_split_tokenized` (called in `cycle()` beside the hygiene sweep; idempotent). Reverse:
  `UPDATE shadow_trades SET tier = substr(tier, 5) WHERE tier LIKE 'tok:%'`.
- Every reader keyed by a stream tier is crypto-only with no change: the Decision Desk rows and lights, the bells'
  forward records (`rung_stats`), the window clock, the board ledgers, the demo's form read. The all-tier readers
  (`shadow_summary`, conf / heat bands, confluence, recent closes, edge miner) skip `tok:*` tiers.
- The tokenized record sits beside it: 🏦 TOKENIZED DESK on the page and the 🏦 line on a tokenized bell, both keyed by
  the stream (`shadow_tokenized` strips the prefix). `shadow_summary(include_tok=True)` lists the tok tiers.
- Not split: the demo account is one book (its closed-trade list shows the coin); the signals table and the boards
  still show tokenized fires as signals. Guard: `.bstock_restore_test.py` (54).

## 🎯 GEN 19.2 — the accuracy exit on ⭐ star seats (2026-11-13)

User: "yes switch gated star to the 88% exit and deploy".
- A demo ⭐ star seat banks HALF at +0.3R (entry + 0.3 x the initial risk), moves the stop to entry on the rest, and
  the rest runs the desk ladder (`demo_account.SCALE_OUT_SRC = {"elite_star"}`, `SCALE_OUT_R = 0.3`). Once per seat.
  The pairs and the conviction revival keep the plain ladder. Revert: `SCALE_OUT_SRC = set()`.
- Measured by the 10 Nov audit on a real-order ruler (resting stop + resting limit, stop first inside a bar), 225 gated
  stars 9 Sep -> 4 Nov: 88% of trades end positive / +0.16R a trade (halves +0.20 / +0.12R) against the plain ladder's
  66% / +0.32R. Accuracy bought with profit; a loss is still a full 1R.
- The ⭐ star bell prints the level: `exit: half off at <price> (+0.3R) → stop to entry · gated ⭐ 88% / +0.16R (225)`.
- The demo's closed list shows two records for such a trade (the banked half, then the rest), so the page's
  record-level win rate reads lower than the 88% trade-level figure.
- Guard: `.demo_gen19_test.py` (long and short scale-out, once only, rest stops at entry, rest runs the ladder,
  pairs untouched).

## ⚠️ AGAINST THE MARKET mark on LONG bells (2026-11-13)

User: "yes marked against the market that is better on telegram notifications".
- The worker reads BTC's last completed daily close against its 50-day average every cycle
  (`tg_cells.set_btc_regime`). A LONG fire bell sent while BTC sits below it carries one line:
  `⚠️ AGAINST THE MARKET — BTC x% under its 50-day average · longs in this state …`.
- Rides the ⭐ star card, 💎 CONVICTION REVIVAL, every pair card, 💥🥇 PRIME × STRONG TRIGGER and 🏆💎 APEX V2 GATED.
  Shorts are never marked (the mirror did not hold). Replies and the TP1 ping are not marked.
- A mark, never a mute. No read or a read older than 36h prints nothing.
- Measured: longs in that state 37% / −0.10R (4,047, Jul → 4 Nov) and 34% / −0.28R (1,332, 5 → 12 Nov); shorts in the
  second window 57% / +0.18R (887). Guard: `.tg_cells_test.py` (63).

## 🚦 GATEKEEPER line on every fire bell (2026-11-13)

User: "build the gatekeeper and make it inside the streams, like not muted but just a line so I know things".
- One line per fire bell, `🚦 GATE → FULL|HALF|SMALL · market side · stream trust · burst`, from `tg_cells.gate`:
  1. market side: BTC's last daily close vs its 50-day average (long below it = against, short below it = with);
  2. stream trust: the audit's verdict per stream, by side where measured (`GATE_TRUST`);
  3. burst: other coins that rang a fire bell on this side in the last 2h (`worker_store.bell_burst`; muted stars do
     not count); three or more = one market move;
  4. size: full with no warning, half with one, small with two or more.
- Rides the ⭐ star card (its header size word is now the gatekeeper's), 💎 CONVICTION REVIVAL, every pair card,
  💥🥇 PRIME × STRONG TRIGGER, 🏆💎 APEX V2 GATED. It replaces the plain ⚠️ line. Nothing is muted.
- One switch: `tg_cells.GATEKEEPER = False` puts the plain ⚠️ against-the-market line back.
- Guard: `.tg_cells_test.py` (75), `.bells2_test.py` (51).

## 📈 LONG TERM INVESTMENT section (2026-11-14)

User: "deploy this as separate section on our deployed website and its separate section on the left long term
investment as headline" · "it should be updated as the market unfolds" · "have the portfolio and colors to buy
strong buy hold as per our plans".
- A page of its own on the left menu. `app.py` draws it before the shared header and every scanner or news load,
  then stops: opening it costs eleven cached daily-candle requests (ten names + BTC, five-minute cache).
- The plan is FROZEN in `longterm_data/plan.json` at the 13 Nov 2026 close: per name four buy rungs (today, then
  the dips reached in about 75% / 50% / 30% of six-month periods by volatility), a stop one step lower (the 15%
  dip), take-profits at 1.5x / 2x / 3x, and the add-up landmarks. Re-anchor only by re-running
  `research_meta/portfolio_1114/freeze_plan.py` after `build_data.py`.
- Live: prices from the app's own candle feed (the three stocks through their tokenized tickers, which trade
  around the clock). `longterm.walk` replays the daily candles since the plan date: a rung fills when a low
  touches it, the stop sells everything and ends the plan, a take-profit sells its share when a high touches it.
- Plan signal (a plan state, never a forecast): STRONG BUY = price at or under buy 3; BUY = at or under the first
  buy level (2% tolerance); HOLD = above the buy levels, under take-profit 1; TAKE PROFIT = at or above a
  take-profit; STOP HIT = the stop was reached.
- "My portfolio": up to three names, an amount and a rung split, saved in `.longterm_portfolio.json` on the state
  disk; shows what the plan has bought and sold so far, the average buy price, worth now and every order's status.
- The research workbook (charts, odds, builder, method) ships as a snapshot, `longterm_data/workbook.html` and
  `.pdf`, shown behind a toggle with a PDF download. It refreshes only when rebuilt and pushed.
- Files: `longterm.py` (logic, no Streamlit), `longterm_page.py` (page). Guard: `.longterm_test.py` (36).
  Local preview without the scanner: `streamlit run research_meta/portfolio_1114/lt_preview.py`.
- **Daily rebuild (2026-11-14, user: "yes add the daily automatic rebuild on the render").** The workbook's build is
  now `longterm_build.py` (the same computation the local script used, moved verbatim: its output matched the old
  data exactly). `agent_worker.cycle()` calls `longterm_build.maybe_rebuild()` every cycle; it returns at once and,
  when today's copy is due, builds in its own thread into `<STATE_DIR>/longterm/workbook.html`.
  - Due: once per UTC day, 20 minutes after the 00:00 close; never in the first 15 minutes after a start; a failed
    try waits 2 hours. Status in `<STATE_DIR>/longterm/build.json`. `LONGTERM_REBUILD=0` in the environment turns it off.
  - Every source is fail-soft: a feed that is down serves its last good copy; the stocks fall back to the committed
    10-year seed (`longterm_data/seed/`) and, once that is more than four days old, are extended with the weekday
    candles of their tokenized tickers. An incomplete build raises and the previous workbook stays.
  - The rebuilt copy carries a banner: its buy levels restart from the latest close, while the tracked plan on the
    page stays fixed; the news notes and quarterly figures are dated 14 Nov 2026 and are not refreshed. The page
    shows the rebuilt copy when there is one, else the repo snapshot. The PDF and the published artifact are not
    rebuilt by the server.
  - Guard: `.longterm_test.py` (50).
- **Three tranches, up to four names, charts and triggers (2026-11-14, user: "we are buying in 3 trenches not 4" ·
  "can hold upto 4 instead of 3" · "show when its the time to buy the dip on the charts next buy zone … if the price
  hold above when to buy on that level as well … do the calculations and show the returns and when to sell").**
  - The plan now has THREE buys per name: today, then the dips reached in about two in three and one in three
    six-month periods (`longterm_build.RUNG_P = [2/3, 1/3]`); the stop stays at the 15% dip. `plan.json` was re-frozen
    from the same 13 Nov close. Presets: equal thirds / 20-30-50 / 50-25-25. STRONG BUY = at or under the LAST buy.
  - "My portfolio" holds up to four names (`longterm.MAX_PICKS`), each with: a Plotly chart (buy zones shaded, stop,
    three sell levels, the live "add above" levels), plain next steps (next buy zone, the trigger if price rises, when
    to sell, the stop), and a returns table (each sell level and the stop, with what is held now and if every buy
    fills first), plus what the whole portfolio would be worth in three cases.
  - "Holds above" trigger (`longterm.addup_events`): two daily closes in a row over the 50-day or 200-day average
    after a close at or under it, or a first close over the highest close of the last 90 days. With the page's switch
    on (default), a trigger buys the lowest unfilled tranche at that close; the board shows ADD: HELD ABOVE on that
    day. Stocks count trading days: the US seed history, then tokenized weekday candles. The page states the evidence:
    for the coins this did not beat buying on an ordinary day.
  - The workbook follows: three tranches everywhere, builder for up to four names, isolated stops now use explicit
    `dip50` / `dip75` fields. `longterm_build.BUILD_VER = 2` makes the server rebuild at once and the page ignore
    an older-shaped copy. Guard: `.longterm_test.py` (70).
- **Adds if price goes up, and real fills (2026-11-14, user: "if the price goes up when to add more capital, please
  add those to the charts as well" · "I have bought the following … I have filled the orders").**
  - Going up: `longterm.add_plan` pairs the nearest live landmark above the price with the LOWEST unfilled tranche's
    money, the next landmark with the tranche above it. The chart numbers them ("Add 1 above 88.92 · 200-day ·
    $1,000"), the next steps spell them out, and the returns table has a third column for that path
    (`outcomes()["up"]`, via `climb`). The workbook's charts carry the same Add lines.
  - Real fills: `.longterm_fills.json` on the state disk ONLY. This repository is public, so real purchases are
    never committed. They are shown and edited only when the page is opened with the admin link (the site's
    existing `?admin=` check, passed as `render(..., admin=)`); `LONGTERM_FILLS_PUBLIC=1` would show them to all.
    Entry: one line each, `NAME buy|sell PRICE USDT [UNITS]`. A name with real fills is tracked from them
    (`longterm.actual_state`): the n-th buy is tranche n at its real price and amount, each tranche still to come is
    sized like the first buy, and the page flags a level the market touched that has no recorded fill yet.
    Without the admin link the page shows the mechanical plan view only.
  - Guard: `.longterm_test.py` (82).
- **Sixteen names and the combined calculator (2026-11-15, user: "also add thse to long term investment and deploy" ·
  "total will be option A at 10000 dollars option B at 12000" · "a combine ROI as well and calculation under one
  table … with their marking of numbers for buying and selling … a more advance one calculator").**
  - Names: WLD, TAO, HYPE, ONDO, LINK, QNT join the ten. `freeze_plan.py` now ADDS names the plan does not hold
    (each with its own `asof` / `start` / `date_label`, here the 14 Nov close) and never touches names already in
    it; `--reanchor` is the only way to re-freeze everything. The page walks each name from its own start.
    The build reads Binance's perpetual candles for HYPE and ONDO (`PERP_HISTORY`), which go back further than
    spot; `BUILD_VER = 3`. Names with under three years of prices show "too new" in the history columns.
  - Positions: `longterm.position(fills)` nets the recorded fills of a name into money in, units, average price
    and sells; a holding sold out completely moves its result to `realized` and counts toward the money to share
    out. `longterm.actual_state` is gone: money decides, not the number of orders. `real_state(row, pos, alloc)`
    counts the money in against the tranches from the top, so a part-covered tranche keeps only what is still
    to place at its level. A line may be a single order or a whole position at its average price; the form can
    replace everything recorded so far.
  - Names not held: with real fills in view they are priced `fresh_state` = as if started at the price now
    ("if bought now"); without the admin link every name follows the plan from its plan date, as before.
  - Money: `TOTAL_OPTIONS` (A $10,000 / B $12,000) or any amount; `split_total` shares it equally, levelling up
    (a name already holding more than an equal share keeps what it has), or takes amounts set by hand.
    Up to `MAX_PICKS = 10` names.
  - The page: one calculator table (`_calc_table`: planned, in so far, worth now, the buys still to make with
    their prices and dollars, average if all fill, the stop and its result, each sell level with what the name
    is then worth), a combined-result grid on the three paths (`_roi_grid`), option A against option B
    (equal split only), every order with money and units (`_orders`), and the chart / next steps / returns
    for one name at a time.
  - Perpetual history ships with the code (`longterm_data/seed/bn_HYPEUSDT.json`, `bn_ONDOUSDT.json`). Seen live
    right after the first deploy: the server returned Hyperliquid as 52 spot candles (its spot listing dates from
    Sep 2026), so its 200-day average was missing. The page (`_daily(..., deep=True)` for coins) now asks the
    perpetual feed directly when a frame is short and otherwise puts the shipped history in front of the spot
    candles; the build (`binance_daily`) does the same, so a blocked perpetual feed can no longer fail the
    daily rebuild.
  - Guard: `.longterm_test.py` (106).

## 🎮 DEMO GEN 20 (2026-11-17)

User, after the 16 Nov ledger read: "demo trade make it back · 1. Elite Stars no timings restriction just gated
ones and elite x prime being the primary trades you can add tokenized as well · 2. TP 1 bank full or 85% bank
full, no trails · 3. APEX V2 Gated add to the list · 4. STRONG TRIGGER X PRIME ADD TO THE LIST · reset the money
again" and "Lets try elite star and apex v2 together".

- **Roster (`demo_account.CLASS_W`, in order):** ⭐ gated star at any hour, both sides, one full seat (the GEN 19
  window book, its half / double seats and the shorts' heat and BTC-day rules are no longer read) · ⭐🥇 star ×
  prime · 🏆💎 APEX V2 gated (new feed `_DEMO_V2G`, filled where the gated tier is recorded) · 💥🥇 prime ×
  strong trigger (the `_DEMO_PT` feed, back on the roster) · ⭐🏆² star × APEX V2. Star × strong trigger and the
  conviction revival leave the money; their bells and desk tiers go on. Tokenized names seat like any other.
- **Exit:** the plan stop, or TP1 with 100% banked, or the near-TP bank (`NEAR_TP_SRC` = the roster: printed 85%
  of the way to TP1, then faded to 60% while in profit). `LADDER_SRC` and `SCALE_OUT_SRC` are empty: no ladder,
  no trail, no half at +0.3R, no stop to entry, no time cut. `REENTRY_ON = False`: a TP1 bank queues no momentum
  re-entry.
- **Money:** `GEN = 20`, fresh $2,000; `cutover_fresh_book` closes the GEN 19 seats at the live price into their
  own ledger and archives it (`.demo_account.json.gen19_<date>.json`). GEN 19 ended near $1,764.
- **Measured warning given at wire time (ledger to 16 Nov):** star × prime was GEN 19's worst seat (desk 13% /
  −0.66R on 15, demo 0 won of 10, −$372); gated stars since 7 Nov 52% / +0.04R (23), longs 33%, shorts 73%;
  APEX V2 gated 43% / −0.15R (14); prime × strong trigger 70% / +0.36R (10).
- Guard: `.demo_gen20_test.py`. Revert: GEN 19 is at dcb1015.

## 🔔 TELEGRAM BELLS section (2026-11-17)

User: "for every telegram streams we have show me the wn rates so I can see or mute from my mobile phone".

- **Page:** `🔔 Telegram Bells` on the left menu (`tg_bells_page.py`), drawn before the shared header and the
  scanner loads, then the script stops. One card per bell: all-history and last-14-day record (win rate, average
  R, closed trades) and the tokenized seats of the same stream apart. The gated ⭐ star is the star tier cut to
  the fires the bell's own gate passed (the `gate` stamp on the star's signal row).
- **Switches:** with the admin link each bell that has an on/off flag in `agent_worker.py` gets a toggle
  (`tg_switches.REGISTRY`: STAR × PRIME, STAR × STRONG TRIGGER, STAR × TAKE NOW HOT, STAR × APEX V2, APEX V2
  GATED, PRIME × STRONG TRIGGER, ELITE × PRIME, SECOND LEG × PRIME, GO LIVE, TRIGGER × KRONOS × PRIME, ARRIVAL
  T1, the 90% ping, the FREEZE reply). A flip is written to `<STATE_DIR>/.tg_switches.json`; `cycle()` calls
  `tg_switches.apply()` first thing and sets the worker's own flag, so the bell code is untouched and a muted
  bell behaves exactly as when its flag is False in the code. Delete the file to return to the code's settings.
- **No switch yet:** the gated ⭐ star bell and the conviction revival / GO REVIVED bells (their send sites carry
  thread bookkeeping; a switch there needs its own change).
- Telegram commands were not used on purpose: `channel_desk.py` already long-polls the same bot's updates, and
  a second reader of the same bot would take its messages.
- Guard: `.tg_switches_test.py`. Local preview: `.tg_bells_preview.py` (launch entry `bells-preview`).

## 🏦 Tokenized inventory: about 30 names (2026-11-17)

User: "add more tokenized stock to our inventory, we had 19 but we are now pushing to somewhere around 30" ·
"i am talking about futures stocks … we limited to 19 first i think we should do more".

- `config.BSTOCK_MIN_QV` 2,000,000 → 750,000 (24h turnover of the spot token) and `BSTOCK_MAX_N` 0 → 30 (the 30
  largest above the floor). Five tickers joined `TOKENIZED_STOCKS` (CBRSB, INTWB, IRENB, MUUB, AGPUB: same
  exchange permission set as NVDAB); GIGGLEUSDT left it (a crypto token; its 35 old desk rows stay under tok:*).
  On 16 Nov the universe read 100 coins + 30 tokenized names = 130 symbols.
- Load: the 13 Nov restart loop appeared at 119 symbols on this instance. If it returns: `BSTOCK_MAX_N = 20`.
- **Stock futures exist on Binance and the scanner does not read them yet.** USDT-M futures list 237
  `TRADIFI_PERPETUAL` contracts (199 US equities and ETFs, Korean / Hong Kong / China equities, commodities, a few
  pre-IPO names), named without the B: NVDAB (spot token) ↔ NVDAUSDT (perpetual). `binance_client.futures_symbols()`
  keeps `contractType == "PERPETUAL"` only, so `has_perp()` is False for all of them. The scanner reads the spot
  token; a trade on the same stock can be taken long or short on its perpetual. Reading the perpetuals directly
  (ranking by futures turnover, names with no spot token such as SK Hynix KR, Samsung, gold, oil) needs the
  futures host to be reachable from the server first: the 16 Nov long-term rebuild could not reach it.
- Guard: `.bstock_restore_test.py` (57).

- **40 stocks, all with a Binance stock perpetual (2026-11-17 later; user: "we have to have 40 stocks option for
  future preps … tokenized stock with b or no b it should be on binance future preps").** `config.BSTOCK_PERP` maps
  every tokenized spot ticker that has a `TRADIFI_PERPETUAL` on USDT-M futures to it (100 of 104 on 16 Nov; token
  NVDABUSDT → perpetual NVDAUSDT). `BSTOCK_PERP_ONLY = True` lets only those ride (`get_top_symbols`),
  `BSTOCK_MIN_QV = 500_000`, `BSTOCK_MAX_N = 40`: 100 coins + 40 stocks = 140 symbols. `TOKENIZED_STOCKS` now
  holds all 104 tokenized tickers (plus the old names), so none can enter the coin universe by volume;
  `BSTOCK_NO_PERP` (QNTB, STXB, USDEB, BBB) are classed as tokenized and never scanned. Ranking is by the spot
  token's turnover because that is the feed the server can read. If the restart loop returns: `BSTOCK_MAX_N = 20`.
  Guard: `.bstock_restore_test.py` (59).

## 🎮 DEMO GEN 21: stocks only (2026-11-17)

User: "demo trading we will reset and we will only take stock future trades ONLY no other than that. the streams
will be as follows. 1. ELITE CONFIRMED ENTRY 2. GO REVIVED 3. ELITE STARS 4. STRONG TRIGGERS with full leverage of
10x and bank at tp1" and "server reads B tokens make it a priority nvdab and nvda is both same so treat B stocks as
priority".

- **Stocks only:** `demo_account.STOCKS_ONLY = True`. `rank_candidates` drops any symbol that is not in
  `config.BSTOCK_PERP` (a tokenized stock with a Binance stock perpetual). No coin takes a seat.
- **Roster (`CLASS_W`, his order, keys = desk tiers):** `elite_confirm` > `go_revived` > `elite_star` >
  `trig_strong`. Every elite star, gated or not.
- **Feed:** `shadow_trader.open_from_signal` appends to `shadow_trader.DEMO_FEED` whenever the desk opens a seat
  under `tok:<one of the four>`; the worker's GEN 21 pools read that list (offers live 45 minutes). The demo
  therefore trades the same seats the page's tokenized records count, with the same plan. The older feeds
  (`_DEMO_STARS`, `_DEMO_SP`, `_DEMO_V2G`, `_DEMO_PT`, `_DEMO_SV2`, `_DEMO_GO`) are still filled and unused.
- **Exit and size:** as GEN 20: one full seat ($100 margin) at 10x; the stop, TP1 with 100% banked, or the near-TP
  bank; no ladder, no trail, no re-entry. Recent form is read from the `tok:` tiers.
- **Money:** `GEN = 21`, fresh $2,000; GEN 20 (a few hours old) is closed at the live price and archived.
- **Measured at wire time (stock names, 15-minute candles, stop or TP1 in full):** elite confirmed 74% / +0.23R
  (35) since 10 Nov, 40% / −0.25R (15) before; GO revived 89% / +0.30R (27), 50% / −0.26R (16) before; elite star
  80% / +0.39R (15), 45% / −0.22R (11) before; strong trigger 73% / +0.01R (33), 74% / +0.13R (35) before.
  Streams not on the roster with a longer positive record on stock names: top conviction 68% / +0.20R (50),
  surge 62% / +0.18R (91), best zone 59% / +0.12R (104), take-now hot 58% / +0.12R (106), nearly all before 10 Nov.
- Guard: `.demo_gen21_test.py`. Revert: GEN 20 is at 945907c.

- **GEN 22 (2026-11-17, minutes after GEN 21; user: "lets add elite conviction to the demo trading as well and have
  an account of 5000 dollars instead of 2000").** `GEN = 22`, `START_BAL = 5000.0` (a full seat is $250 of margin,
  $2,500 at 10x; the day-loss rail is a share of equity and scales by itself). `elite_conv` joins `CLASS_W` as the
  fifth stream, `shadow_trader.DEMO_FEED_TIERS`, the worker's pools and the form map. On stock names (candles,
  stop or TP1 in full) elite conviction is 54% / +0.11R (63) since 10 Nov and 30% / −0.07R (43) before; its target
  sits about 1.4R away. It is the parent fire of the confirmed entry, the GO and the star and fires first, and the
  demo holds one seat per name, so it will often be the seat taken on a move. Guard: `.demo_gen22_test.py`.

- **GEN 22.1 (2026-11-17; user: "yes let confirmed entry, go and star replace the conviction seat remove elite
  convcition from it").** `demo_account.REPLACE_SRC = {"elite_conv"}`, `REPLACE_BY = {"elite_confirm",
  "go_revived", "elite_star"}`: in `try_open`, a candidate from a REPLACE_BY stream on a name whose seat is held by
  a REPLACE_SRC stream runs every opening check first (zone, stop, heat and collateral with the old seat left out),
  then the conviction seat is closed at the live price (reason "replaced by <stream>", returned in the rotated
  list) and the newcomer opens. A strong trigger does not replace; no other seat gives way. No reset.
- **🔔 Telegram Bells, 2026-11-17 later (user: "the comparsion of crypto vs tokenzied stocks for telegram
  notificaitons as per streams and also add the streams to the list which … we set for demo").** The five demo
  streams are on the list (🎮), every card shows crypto against stocks for all history and the last 14 days
  (`records()` adds `tok_recent`), and a bell without a switch says what the code does with it today
  (`tg_switches.FIXED`: the gated star and the revival ring; the plain star fire, the confirmed entry, the strong
  trigger and the conviction fire are silent on the phone).

- **GEN 22.2 (2026-11-17; user: "remove conviction" · "have the elite confirmed run, if go revived is added to the
  same elite confirmed we add more margin to it … even if its elite star … 10x leverage but we add more margins if
  elite star fires or go revived fires").** Elite conviction is off the roster again (`CLASS_W`, the desk feed,
  the pools); a conviction seat still open runs out or gives way as in 22.1. **Stream add:** in `try_open`, a
  candidate from `ADD_BY` on a name already held through a different `ADD_BASE` stream, same side, adds
  `ADD_SEATS = 1.0` seat of margin at the live price through the GEN 18 add-on engine (`_stream_add` →
  `_add_on`: entry averaged, stop and TP1 kept, refused on short collateral, the heat cap, price through the stop
  or the 8% guard), once per stream (`add_srcs` on the position), never at or past TP1. A strong trigger neither
  adds nor receives. The adds of the last call are in `demo_account.STREAM_ADDS`; the worker logs them. No reset.

- **GEN 22.3 (2026-11-17; user: "For Demo Trading We wont take trades on the timings of 17-21 and 21-01 for all
  streams because they doesnt have good win rates" · "only strong trigger at the window of 17-21 shows really
  good signs lets have that only instead of 21-01").** `demo_account.NO_ENTRY_WINDOWS = {"17-21", "21-01"}` and
  `NO_ENTRY_EXEMPT = {("trig_strong", "17-21")}` (it was `("trig_strong", "21-01")` for half an hour, 617fd80),
  read by `entry_window_ok(src, now, fired_at)` at the top of the `try_open` loop: no new seat and no
  stream add while the PKT clock is in a shut window, nor on a desk seat FIRED in one (the feed offers a seat for
  45 minutes). The strong trigger seats 17–21 and is shut 21–01. A card that carries a shut stream's plan but also
  an open stream (a strong trigger beside a star, 17–21) seats the open stream with its own plan (`plans` on the
  ranked candidate). Open seats are managed as before; the real-money executor is not touched. Measured on the
  16 Nov ledger (stock seats of the four streams, desk booking, in-sample): 17–21 57% / −0.01R (49), 21–01 50% /
  +0.10R (24), the rest 74% / +0.24R (114); the strong trigger alone read 87% / +0.37R (15) and 70% / +0.33R (10)
  in the two windows. Guard: `.demo_gen22_test.py`. Revert: `NO_ENTRY_WINDOWS = set()`. No reset.

- **GEN 22.4 (2026-11-17; user: "priority on demos should be 05-09 , 9-13 signals and 01-05 with full leverage and
  add ons · 13-17 we can trade but few good ones only with 5x leverage only · strong trigger full leverage even
  for 17-21 · rest stays as it is").** The demo's clock book, by the PKT window of the open: 05–09 · 09–13 · 01–05
  every stream at 10x with stream adds (`ADD_WINDOWS`); 13–17 every stream at 5x (`WINDOW_LEV = {"13-17": 5.0}`,
  applied in `try_open` after `lev_for`, which the real-money executor reads and which stays 10x), at most
  `WINDOW_MAX_NEW = {"13-17": 2}` new seats in the window (`window_new_seats` counts open and closed seats opened
  since `window_start`), best-ranked first, no stream add; 17–21 the strong trigger only at 10x; 21–01 nothing.
  "Few good ones" is built as the cap: nine closed stock seats in 13–17 cannot support a quality bar. Measured
  (16 Nov ledger, stock seats, desk booking, in-sample): 05–09 78% / +0.39R (36), 09–13 90% / +0.34R (31), 13–17
  67% / +0.21R (9), 01–05 58% / +0.03R (38; confirmed entry 86% / +0.81R on 7, strong trigger 43% / −0.37R on
  14). Revert: `WINDOW_LEV = {}`, `WINDOW_MAX_NEW = {}`, `ADD_WINDOWS = set()`. No reset.

- **GEN 22.5 (2026-11-17; user: "1. We have 10x, ad ons all four streams where timings of 05-09 and 09-13 take
  the higest seats · 2. timings 13-17 7x seats for all four streams and strong trigger and just 2 new seats ·
  3. timings of 01-05 … · 4. Strong triggers will take only 10x on 17-21 and 21-01"; for 01–05, asked, he chose
  "only … elite confirmed entries as they have the high score here").** The clock book now reads: 05–09 · 09–13
  every stream at 10x with stream adds; 13–17 every stream at 7x, two new seats, no add; 17–21 · 21–01 the strong
  trigger only at 10x; 01–05 the confirmed entry only at 10x, no add. In code: `NO_ENTRY_WINDOWS = {"17-21",
  "21-01", "01-05"}`, `NO_ENTRY_EXEMPT = {("trig_strong", "17-21"), ("trig_strong", "21-01"), ("elite_confirm",
  "01-05")}`, `WINDOW_LEV = {"13-17": 7.0}`, `ADD_WINDOWS = {"05-09", "09-13"}`. The fire-time rule still holds: a
  seat fired in a window that is shut for its stream is not taken after that window ends. Measured (16 Nov ledger,
  stock seats, desk booking, in-sample, thin): 01–05 confirmed entry 86% / +0.81R (7); 21–01 strong trigger 70% /
  +0.33R (10); 17–21 87% / +0.37R (15); 13–17 all four 67% / +0.21R (9). No reset.
  **Adds (user, the same hour: "add on 01-05 if go revived agree with it"):** `ADD_PAIRS = {("01-05", "go_revived",
  "elite_confirm")}` read by `add_ok(win, by, base, now, fired_at)`: in 01–05 GO revived opens no seat but adds
  one seat of margin to a name held through a confirmed entry. **Add fix:** the feed offers a desk seat for 45
  minutes and `rank_candidates` folds every stream of a name into one card named after the highest stream, so a
  GO revived fired within 45 minutes of the confirmed entry was hidden and its add often never made; `try_open`
  now reads every stream on the card (`plans`) for an add on a held name.

## 📱 PHONE ROSTER BY ASSET CLASS (2026-11-17) — `tg_roster.py`

User: "New Stream should be introduced for tokenized stocks … For Crypto …" · "measure stocks tokenzied stock
seperately and crypto seperatly and their information card on the buzz should have the information related to it
only" · "for tp1 hit only have on for the streams that are active on telegram" · "also deploy A grade as well to
the telegram crypto side".

- **Stocks ring:** 💎✅ confirmed entry (`TG_CONFIRM_STOCK`) · ⭐ every star, no gate (`TG_STAR_STOCK`), with its
  1H verdict and GO fast / late as replies in its thread · 💎⚡ conviction revival (`TG_CONV_REVIVAL`).
- **Coins ring:** ⭐ gated star, and every star 13–17 PKT with the caution line (`STAR_UNGATED_1317 = True` again)
  · 💎🏆 A-grade (`TG_AGRADE`) · 🔥🥇 second leg × PRIME · 💥🥇 PRIME × strong trigger · ⭐✅🔥 star × take-now hot
  · 🏆🔻 APEX V2 SHORTS (`TG_APEX_V2_SHORT`, every APEX V2 short fire, the three-rule gate's read on one line, the
  market side in the header, a thread anchor for the 1H verdict). ⚡🔮 KR-STRONG PREMIUM was not on his list and
  is left ringing; it has a switch now (`TG_KR_PREMIUM`).
- **Off the roster** (flags False, records and desk tiers go on): ⭐🥇 ⭐💥 ⭐🏆² 💎🥇 pairs, 🏆💎 APEX V2 gated, the
  conviction revival on coins.
- **Built, switched off:** 💎✅⭐ confirmed entry after a gated star (`TG_CONFIRM_STAR`). Measured the way the bell
  can know it (star first, then the confirm) it ran 48% / −0.21R (33). The order that paid, a confirmed entry
  first and then the gated star, 65% / +0.43R (55) against 57% / +0.07R (51), is a mark on the star's own card.
- **Class rule:** `tg_roster.CRYPTO_ONLY` / `STOCK_ONLY`, checked by `class_ok(key, symbol)` at each send site. A
  key in neither set rings on both classes when its switch is on.
- **Stock cards** print stock numbers only: `stock_line(tier, side, now)` reads the clean closes under
  `tok:<tier>` (this PKT window with the 🟢 / 🟡 / 🔴 light, this side, all; cached 30 min) and `us_session()`
  adds the US market state. Cards: `stock_star_card`, `stock_confirm_card`, `stock_verdict`, `stock_go_card`,
  `stock_revival_card`. No coin card text was changed; a coin star's card gains two marks under its header when
  they apply: 🔥 second leg already on the coin and 💎✅ confirmed entry already on the coin (6h look-back,
  `_star_marks`). The second-leg mark is rare: 16 of 572 stars had one before the fire (69% / +0.37R); the
  second leg usually arrives after the star.
- **Rang-bell log:** every entry bell that actually rings writes one row to the signals stream `tg_bell`
  (`_tg_rang`; the `tier` column carries the bell's key). The 🏦 TP1 HIT ping watches that log cut to
  `tg_roster.TP1_PING`, which is every bell on the roster (the first build left APEX V2 shorts, the stock revival
  and star × take-now out; he the same night: "add tp1 ones to the ones that rings so add it"), with a 48h bridge
  from the old streams for bells rung before `ROSTER_TS`. ⚡🔮 KR-STRONG PREMIUM was muted the same night on his
  word ("Mute KR STRONG", `TG_KR_PREMIUM = False`). The 💎✅⭐ bell stays off on his word ("Elite confirmed with
  star not the other way round"): the confirmed entry first and then the gated star is the star's bell with its mark. The 🚦 gatekeeper's burst read counts the same log (`tg_cells.BELL_STREAMS = ("tg_bell",)`).
- **Switches:** every flag above is on the 🔔 Telegram Bells page, ordered stocks, coins, off the roster. A
  switches file written before this roster is ignored (`tg_switches.ROSTER_TAG`).
- **Evidence standard:** every record on these cards is a slice of the ledger to 16 Nov (desk booking, about
  0.11–0.18R generous). Nothing here is forward-tested yet.
- **Guard:** `.tg_roster_test.py` (68 checks). **Revert:** set a flag False, or remove a key from the class sets.

## 🛡 THE STOP RULE (2026-11-17) — `stop_rule.py`

User, after an MVLL star he took by hand was stopped by a one-minute wick (low 8.58 against a stop of about 8.60)
and then ran to TP1: "sligh liquidation wick can hit stop but if its going our direction of tp we are out of the
trade on real money so we need to fix it" · "for everything paper trading and things we are doing we are changing
the rule of stops to 4h rule not the ones we have today this goes to all paper trading and to our telegram
notificaion streams · for stocks on telegram notificaitons and for paper trading page in our systems we add the
rule of 15m rule stops" · "we will have this information of updated win rates for every buzz".

- **The rule** (`stop_rule.rule_stop`): a quarter of the timeframe's ATR14 beyond the nearest swing (pivot, two
  candles each side) at or past the signal's own stop. Coins read the last 30 closed 4h candles, tokenized stocks
  the last 96 closed 15m candles (`SPEC`). No such swing: the look-back's extreme when it is past the plan stop,
  else the plan stop itself. Never tighter than the plan stop, never further than 8% from entry (`CAP`).
- **Where it acts.** `shadow_trader.open_from_signal`: every desk seat opens on the rule's stop (the mirrored
  `conviction_v2_rev` tier and any `mirror_of` plan keep their own). `paper_bot.open_position`: the Paper Trader
  page's own positions (`STOP_RULE`; the size is cut from the risk, so it shrinks). The six roster entry bells:
  `agent_worker._rule_card` -> `tg_roster.rule_card` carries the rule's stop INSIDE the card's own entry / SL / TP
  line (user, on seeing the first build: "stops please dont add line instead carry it within the tp sls and entry
  we have"): the `SL` token is the rule's stop and the (+x.xR) beside TP1 / TP2 is re-cut on it; no stop line is
  added. One replay line follows the card (the candle replay of that bell on that stop; stocks also by PKT
  window). The 1H verdict and GO replies follow the bell's stop (`tg_roster.rule_reply`, in memory for 36h: a
  restart between a bell and its reply leaves the plan stop on the reply).
- **What still reads the plan stop.** Every gate and signal, the real-money executor, the bank zone and the
  star card's half-off level.
- **The demo (GEN 22.6, user at the deploy: "also on demo trading apply 15m rule to it as well and also have
  conviction revival stream for demo tradings on for the timings of 01-05, 05-09 and 9-13 with full leverage and
  add ons").** The desk's demo feed carries the rule's stop (the plan's when the rule's is 7.8% or more from
  entry, `shadow_trader.DEMO_RULE_MAX`: the demo refuses stops of 8% at 10x). GO REVIVED, which is the conviction
  revival, now also opens seats 01–05 at 10x (`demo_account.NO_ENTRY_EXEMPT`), and in 01–05 a confirmed entry and
  a GO revived add margin to each other's seat (`ADD_PAIRS`). 13–17 stays all four streams at 7x.
- **Records.** Desk R is measured on the seat's stop: from `RULE_TS` a TP1 books a smaller R and a stop the same
  −1R, so records across that date are not comparable. Every seat whose stop moved writes one row in the signals
  stream `stop_rule` (plan stop and rule stop); every rung bell's `tg_bell` row carries `rule_stop`.
- **Measured** (7,082 closed desk trades to 16 Nov on 15m candles, wicks counted, fees in, stop or TP1 in full,
  in-sample, R per 1R risked): six coin bells 62% / +0.15R on the plan stop → 76% / +0.18R on the 4h rule (a
  stop-out costs about 1.5x); three stock bells 68% / +0.10R → 70% / +0.09R on the 15m rule (71% / +0.01R on the
  4h rule). The desk's own ladder (stop to entry at +1R, trail 1.2R) was NOT replayed on the new stops.
- **Fetch.** Candles are fetched only where `stop_rule.LIVE` is set (the worker sets it at import) or a caller
  passes `live=True` (the paper bot); one fetch per symbol per ten minutes. No candles, an error: the plan stop.
- **Off:** `stop_rule.RULE_ON = False`. Guard: `.tg_roster_test.py` (rule, card, reply, desk, 91 checks).

- **Demo GEN 22.7 (2026-11-17; user: "shut strong trigger 17-21 on demo and add 21-01 and deploy and for 13-17 all
  four streams we choose the one with highest win rates in it those get the seat").** `NO_ENTRY_EXEMPT` loses
  `("trig_strong", "17-21")`: 17–21 opens nothing (the cell it was opened on was desk booking, 87% / +0.37R on 15;
  the same trades on candles are 67% / −0.13R); 21–01 stays the strong trigger's at 10x. `WINDOW_PICK = {"13-17"}`:
  the worker passes `try_open(window_rank=…)` each stream's win rate over its closed stock seats opened in that PKT
  window (`tg_roster._stock_rows`, at least `WINDOW_PICK_MIN = 3` closes), and the window's two seats go to the
  best-ranked stream first; a card counts by the best-ranked stream on it; unranked streams keep the roster order.

## 🕐 THE DEMO'S FAST PATHS (2026-11-18) — `demo_watch.py`, `demo_account.walk`, `agent_worker._demo_instant`

User: "it didnt picked signals from 01-05 elitte confirmed entry can you tell me why? though they were good
signals" · "closing when tp is hit is slow on the demo trading can we fasten that for accuracy". Both came from
one fact: the demo touched its book once per worker cycle (17–20 minutes), at the end of it.

- **Seat at the signal** (`agent_worker._demo_instant`, set as `shadow_trader.DEMO_HOOK`): the moment the desk
  opens a stock seat of a demo stream, the demo runs `try_open` on that one candidate. Before, a fast signal was
  refused minutes later because price had run more than 25% of the way to TP1 (`ZONE_MAX`). Not in a
  `WINDOW_PICK` window (13–17: seats are picked by win rate at the end of the cycle), never inside the cycle's own
  demo block. Off: `agent_worker.DEMO_INSTANT = False`.
- **The watcher** (`demo_watch`, started once from `cycle()`; `PERIOD_S = 300`, his word after the first build at 60 s: "switch it to 5-10 mints"): every 5 minutes, when the demo holds a seat, it
  reads the 3-minute candles (`BAR = "3m"`; one-minute for the first hour, then his word: "3 mint candles check and every 5 to 10 minutes will be suitab;e") closed since the seat was last looked at (Binance spot) and replays them through
  `demo_account.walk`, which drives the same `manage()` as the cycle: the bad extreme of each minute first, then
  the good one, then the close. A stop or TP1 is booked at its level and stamped with the minute it happened; a
  wick counts (the MVLL case of 17 Nov would have been a stop). The demo's win rate should come down to what an
  exchange stop gives. Off: `demo_watch.ON = False`.
- **The lock** (`demo_account.lock / unlock / lock_mine`): the cycle's demo block holds it from its `load()` to
  its `save()`; the watcher and the instant seat take it for their own load-to-save, wait a few seconds, else skip.
  `save()` is atomic now (write beside, replace), so the page never reads half a file.
- **Seats not taken, and why** (`state["skip_log"]`, last `SKIP_KEEP = 60`; the demo page's 📝 list): every
  refusal in `try_open` leaves one line (price already ran, window shut, 13–17 seats used, stop too wide for the
  leverage, heat, collateral, already holding the name when the seat predates the signal).
- Guard: `.demo_fast_test.py` (40 checks: lock, atomic save, walk, tick, hook, instant seat, reasons log).
- **🩺 Feed diagnostic (written 2026-11-17, deployed 2026-11-23 on the user's "Yes, deploy"; read-only).**
  - Why: the ledger shows the server has read SPOT all along. After the 24 Oct perp-first change 209 of 215 BTC
    2-hour pulse readings equal the spot close to the cent and none equal the perpetual close; BTC desk prices sit
    off the perpetual's $0.10 grid as often as before; the OI radar and the funding edge (same futures host) have
    never recorded once on the server. Nothing said so anywhere: every futures failure is swallowed.
  - What: `binance_client._FEED` counts futures requests ok / failed (with the last error text, so the HTTP status
    is visible), candles from perp / spot / Bybit, single prices from perp / spot, and how many perpetual prices the
    last bulk refresh wrote. `feed_status()` returns a copy, `feed_line()` the same as one line. Neither sends a
    request; a failing counter cannot reach a caller.
  - Where: the worker prints `🩺 feed: …` after its first scan and then once an hour, and writes
    `<STATE_DIR>/.feed_status.json` (latest numbers + the last 48 hourly rows, so a state backup carries them). The
    admin panel (`?admin=`) shows two lines, the page's process and the worker's: they are separate processes.
  - No reading, bell, tier, seat or decision changes. Guard: `.feed_diag_test.py`.

## ⏳ WORKER SPEED + TWO BELL / METER FIXES (2026-11-23) — deployed on the user's word

User, after the 23 Nov ledger read: "The worker is slow … fix this we need to get it asap" · "apex v2 idont think i
got every signal here" · (the meter) "can you fix this and deploy as well".
- **Measured (cycles + signals tables, 23 Nov backup).** A cycle ran every ~17 min on 15–16 Nov and every 26–40 min
  from 17 Nov, with a 1.5–2.5 h gap every day. The scan itself is ~1.4 min. The time is the Kronos forecasts: up to
  8 new candidates plus the 20-coin flip watch (`config.WORKER_FLIP_WATCH`, forecast EVERY cycle, past the 2 h
  cache), one after the other, and one forecast took 21–24 s on the server until 17 Nov midday and 38–55 s since.
  20 × 22 s = the 8 silent minutes of a fast day; 20 × 55 s = the 18 silent minutes of a slow one.
- **Deployed, no reading changed:** the 18 Nov one-thread fix below (it had been written and was waiting for his
  word), and the futures back-off: `binance_client.futures_symbols()` asks a refusing futures host once per 5
  minutes (`_FUT_RETRY_TS`), not on every `has_perp()` call, and `prime_prices` skips the futures ticker when
  there is no perpetual list. On this server the host answers HTTP 451 (the feed meter, 23 Nov: 498 refused
  requests for 498 candle fetches in one scan), so every fetch paid one refused request plus a 0.2 s pause.
- **NOT changed, his decision:** the 20 flip-watch forecasts every cycle. Refreshing them less often is the
  certain way to a short cycle, and it changes how fresh the Kronos read is on those coins.
- **🏆🔻 APEX V2 SHORT bell.** `n_alerts` was created below the APEX V2 loop, so the bell's own `n_alerts += 1`
  raised right after the bell was sent: the phone got the bell, the rang-bell log did not (30 short fires, 0 rows,
  17 → 23 Nov), so no TP1 HIT ping, no gatekeeper count, no thread for the 1H verdict. The counter is created
  above the loop now.
- **🩺 feed meter.** Its hook called `_os.replace`, and `cycle()` uses `_os` as a loop variable further down (a
  local, unbound at the hook): the log line printed, the file stayed `.feed_status.json.tmp`. It imports
  `os as _fd_os` itself now.
- **The class of mistake** (a `cycle()` variable read before its first assignment; the unbound-name gate in
  `.agrade_test.py` cannot see it because the name IS bound somewhere): `.feed_diag_test.py` checks the meter's
  hook for it, and a bytecode scan of `cycle()` found `n_alerts` as the only other case.
- Guards: `.feed_diag_test.py` (the back-off: 300 checks + fetches = 1 futures request, 1 more after the wait),
  `.server_threads_test.py` (7).

## 🧵 ONE THREAD PER NUMERIC LIBRARY (2026-11-18) — `launch.py`, `kronos_forecast._cap_threads`

User: "i have a lot of server downs cant we fix it without reducing anything". Measured that evening with nothing
but health probes: full restarts at 19:10, 19:23 and 19:36 PKT (each about 13 minutes after the previous start),
then at 19:52 a two-minute stall (a timed-out check and four short 502s) with no page open. Short 502s are Render
taking an unresponsive service out of rotation (its health check on `/_stcore/health` failing ~15 s); a minute of
that and Render restarts it. Cause: torch (Kronos), OpenMP, MKL and OpenBLAS start one thread per HOST core, the
instance has one processor (plan `standard`), and no cap was set anywhere, so a batch of forecasts ran dozens of
threads inside a one-processor quota and throttled the whole container, the web process included. It clusters
after a start because the forecast cache (2 h) is empty then and the first scan runs the most forecasts.
- `launch.py` sets `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `NUMEXPR_NUM_THREADS`,
  `VECLIB_MAXIMUM_THREADS` to 1 (`setdefault`: a dashboard value wins) and `TOKENIZERS_PARALLELISM=false`, at module
  level, before numpy / torch are imported and before the Streamlit subprocess starts (it inherits them).
- `kronos_forecast._cap_threads()` sets `torch.set_num_threads` / `set_num_interop_threads` to `KRONOS_THREADS`
  (default 1) before the model is built, in whichever process forecasts.
- The brain thread lowers its own priority (`BRAIN_NICE = 10`, `os.setpriority` on its native thread id; inherited
  by the threads it starts): the web process goes first when both want the processor.
- Nothing is switched off; a forecast does the same work on one thread (about 11 s on a 16-core desktop).
- NOT verified from here: Render's own reason for each restart (its Events tab says "health check failed" or
  "out of memory"). If it says memory, this is not the whole fix. Guard: `.server_threads_test.py`.

## 📱 THREE COIN BELLS + THE RECORD SINCE THE STOP RULE (2026-11-23) — `tg_roster.py`, `agent_worker.py`

User: "Ok I want these on telegram now: For Crypto Coins: 1. Confirmed Entries 2. Conviction Revival (GO) 3. APEX V2
Shorts and Longs both. Both should ring with the latest information on the buzz signal after the stop loss rule
change. For Stocks, for Confirmed Entries: 13-17 timings and 21-01 timings were best update on the information buzz
according to our new rule applied so we should know".
- **Coins now also ring:** 💎✅ ELITE CONFIRMED ENTRY, every confirmed entry (`TG_CONFIRM_COIN`,
  `tg_roster.coin_confirm_card`); 💎⚡ CONVICTION REVIVAL, every revival, as on stocks (`TG_CONV_REVIVAL_COIN`,
  `coin_revival_card`; the gated coin bell of 14 / 19 Oct is no longer reached, kept for a revert); 🏆🔺 APEX V2
  LONG beside the short (`TG_APEX_V2_LONG`, bell key `apex_v2_long`, one card `apex_v2_card` for both sides).
  `tg_roster.STOCK_ONLY` is empty: each class has its own switch. All three are on the 🔔 Telegram Bells page.
- **The record on these cards is read live:** `tg_roster.since_rule_line(tier, symbol, side)` = the desk's closed
  trades OPENED since the stop rule went live (`RULE_SINCE_TS`, 17 Nov 20:08 PKT), for the bell's tier and class:
  this PKT window, this side, all. Desk booking, counts under 10 marked thin, cached 30 minutes. APEX V2 shows its
  own side's window and both sides. The APEX V2 short card no longer prints the fixed 23 Sep → 16 Nov stamp and
  record line.
- **Stock confirmed entry:** the same live line, plus `since_rule_windows` = every PKT window with a trade since
  the rule, best first (on 23 Nov: 21–01 78% (9) · 13–17 75% (4) · 01–05 25% (4) · 17–21 25% (4) · 05–09 12% (8)).
  Its fixed 🧪 replay cells to 16 Nov are removed (they read the other way round: 01–13 best, 21–01 29%).
- **What he was shown before he chose** (23 Nov ledger read): confirmed entry on coins 49% / +0.05R (1,391) before
  the stop change; conviction revival entered at the GO 54% / −0.04R (258); APEX V2 longs 41% / −0.04R (123); the
  week since the change was a falling one in which shorts paid. The gatekeeper line on each coin card keeps that
  longer read (`tg_cells.GATE_TRUST`: `elite_confirm` 🟡, `conv_revival` 🔴, `apex_v2_long` 🔴).
- Guards: `.tg_roster_test.py` (101), `.tg_switches_test.py`.

## ⏪⏩ BEFORE / AFTER THE STOP RULE ON EVERY ENTRY BELL (2026-11-23, the same evening) — `tg_roster.before_after`

User, once the three coin bells were ringing: "right now on telegram there is too much information and layers can we
have before the stop loss rule change and after the rule change and the red green yellow buttons accordingly right
now its getting very conufsing honestly", then, as the first build started to strip lines: "dont remove other layers
but have the information that is adjusted accordingly".
- Nothing is taken off any card. Every entry bell that goes through the worker's `_rule_card` (star / A-grade,
  confirmed entry, the pairs, PRIME × trigger, APEX V2 both sides, both revivals; coins and stocks) ends with the
  same two lines, read live from the desk for the bell's own tier, class and SIDE (`tg_roster.with_record`):
  `⏪ before the stop change: 🔴 shorts 54% / +0.12R (496)` and
  `⏩ after the stop change (17 Nov): 🟢 shorts 80% / +0.57R (30) · 21–01 PKT 🟢 93% (14)` (the last cell = this PKT
  window since the rule, left off when it has no trade).
- The light: his window light on the win rate (🟢 68%+, 🟡 60–68%, 🔴 under 60%), with one guard so a light never
  flatters: a record whose average R is at or under zero is never green. ⚪ = no closed trade. Under 10 trades the
  light keeps its colour and the text says `(n, thin)` (user the same evening, on "⚪ 83% / +0.26R (6)": "mark this
  green instead of grey just write (thin)"; the first build showed ⚪ for a thin record).
- The coin ⭐ star's two lines are cut to its gated fires (as on the Bells page). `BELL_TIER` maps a bell to its
  desk tier; a bell with no tier of its own (KR premium) gets no block.
- Adjusted so one card never shows two different numbers for the same thing: the morning's single 📊 line on the
  five new / changed cards is replaced by this block (`since_rule_line` is gone; the stock confirmed entry keeps its
  window list), and the gatekeeper's trust text for `apex_v2_short`, `apex_v2_long` and `elite_confirm` says its
  verdict in words, without the numbers.
- NOT changed: the older record lines the other cards already had (the stock line "desk since …", the 🕐 stamps to
  4 / 16 Nov, the 🧪 replay to 16 Nov). They stay on his word; they are older, fixed periods.
- Guard: `.tg_roster_test.py` (104).

- **💎🏆 A-GRADE bell muted (2026-11-23 night).** User, after the roster read by history (A-grade 36% / −0.01R over
  11 before the stop change, none since): "remove only A grade from the telegram notification". `TG_AGRADE = False`;
  the tier `elite_agrade` keeps recording and the switch is still on the 🔔 Telegram Bells page. The other three bells
  the read named (APEX V2 longs, confirmed entry and conviction revival on coins) stay ON: he chose only this one.

- **🏦 TP1 HIT ping: the streams and their fire times on their own line again (2026-11-23 night).** User: "tp1 hit
  notificaitons on the telegram should have the streams and time as it used to have before only for tp1 hit telegram
  notifications". The ping reads header · `from: <stream> fired HH:MM PKT · …` · `fire entry · SL · TP1` · record line,
  as before the 7 Nov concise pass put the streams, the entry and the stop on one line. Nothing else on Telegram changes.
  The record line is unchanged (the live stock line for a stock, the bell's 🕐 cell for a coin), except that a coin bell
  with no cell of its own (coin confirmed entry, coin conviction revival, APEX V2 longs) prints its live ⏪ / ⏩ record
  instead of nothing (`tg_roster.ping_stamp`). Same evening he asked whether the win rates can update by themselves as
  trades close: they do, on every entry bell and on these pings, read from the desk as the message goes out.

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

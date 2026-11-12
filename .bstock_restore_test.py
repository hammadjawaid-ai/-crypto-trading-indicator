"""Guard — 🏦 B-STOCKS BACK (2026-11-10, user: "bring B stocks and stock back to the system on elite conviction and
rest of the streams should also pick them up"). Checks: the switches (phone ON, universe ON, money gate still
CLOSED), the universe shape on a synthetic ticker feed (top-n crypto + liquid tokenized names appended, illiquid
ones left out, the crypto-only shape when the switch is off), the set's new tickers and no real crypto in it,
the worker's quiet rule reads the phone switch, the demo money gate still refuses a tokenized seat. No network.
Run: .venv\\Scripts\\python.exe .bstock_restore_test.py
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.environ["WORKER_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="bstock_"), "worker.db")
import config              # noqa: E402
import binance_client as bc  # noqa: E402
import demo_account as da  # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


print("1. switches")
check("phone ON (BSTOCK_BUZZ)", config.BSTOCK_BUZZ is True)
check("universe ON (BSTOCK_IN_UNIVERSE) with a volume floor", config.BSTOCK_IN_UNIVERSE is True and config.BSTOCK_MIN_QV >= 1_000_000)
check("money gate OPEN on his word (BSTOCK_VALIDATED) — demo / GEN 19 seats", config.BSTOCK_VALIDATED is True)
print("2. the set")
for s in ("TQQQBUSDT", "MRVLBUSDT", "CRWVBUSDT", "TSMBUSDT", "SNDKBUSDT", "NVDABUSDT"):
    check(f"{s} tagged tokenized", s in config.TOKENIZED_STOCKS)
for s in ("ARBUSDT", "BNBUSDT", "SHIBUSDT", "TRBUSDT", "CKBUSDT", "DGBUSDT"):
    check(f"{s} is crypto, not in the set", s not in config.TOKENIZED_STOCKS)
print("3. the universe on a synthetic feed")
feed = [
    {"symbol": "BTCUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "900", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ETHUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "800", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "SNDKBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(5_000_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "SOLUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "700", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ARBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "600", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "COINBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(500_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "TQQQBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(3_000_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "USDCUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "BTCUPUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ETHBTC", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
]
bc._get = lambda path, **kw: feed   # no network
u = bc.get_top_symbols(3)["symbol"].tolist()
check("top-3 crypto by volume first, in order", u[:3] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"], u)
check("liquid tokenized names appended alongside (≥ floor)", set(u[3:]) == {"SNDKBUSDT", "TQQQBUSDT"}, u)
check("the illiquid tokenized name is left out; ARB (crypto, rank 5) is not pulled in", "COINBUSDT" not in u and "ARBUSDT" not in u, u)
check("stables / leveraged / non-USDT dropped as before", not ({"USDCUSDT", "BTCUPUSDT", "ETHBTC"} & set(u)))
u4 = bc.get_top_symbols(4)["symbol"].tolist()
check("n=4 → ARB joins the crypto block, tokenized still appended", u4[:4] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"] and len(u4) == 6, u4)
check("no cap by default: every tokenized name above the floor rides along (the cap is the load-trim switch)", config.BSTOCK_MAX_N == 0)
config.BSTOCK_MAX_N = 1
u1 = bc.get_top_symbols(3)["symbol"].tolist()
check("cap 1 -> only the biggest tokenized name rides along", u1 == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SNDKBUSDT"], u1)
config.BSTOCK_MAX_N = 0
config.BSTOCK_IN_UNIVERSE = False
u0 = bc.get_top_symbols(5)["symbol"].tolist()
check("switch OFF → the crypto-only universe again", u0 == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"], u0)
config.BSTOCK_IN_UNIVERSE = True
print("4. the worker's quiet rule and the demo money gate")
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
i = W.index("def _bstock_quiet(")
body = W[i:i + 900]
check("worker: _bstock_quiet() returns False when BSTOCK_BUZZ is on (every stream rings)",
      'if getattr(config, "BSTOCK_BUZZ", False)' in body and "return False" in body)
cand = {"symbol": "SNDKBUSDT", "base": "SNDKB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
        "score": 90.0, "conf": 80.0, "burst": 0.0, "src": "elite_star", "heat": 50, "btc_day": -1.0}
check("demo: a tokenized star ranks like a coin now (BSTOCK_VALIDATED True)",
      len(da.rank_candidates({"elite_star": [cand]}, {})) == 1)
config.BSTOCK_VALIDATED = False
check("demo: with the gate closed again it would take no seat (the revert works)",
      da.rank_candidates({"elite_star": [cand]}, {}) == [])
config.BSTOCK_VALIDATED = True
check("demo: a crypto star still ranks", len(da.rank_candidates({"elite_star": [dict(cand, symbol="SOLUSDT", base="SOL")]}, {})) == 1)
print("5. the tokenized desk record, on its own (2026-11-10: 'have these for tokenized desk records separately')")
import time as _t                 # noqa: E402
import worker_store as store     # noqa: E402
import tg_cells as tc            # noqa: E402
import rung_stats as rs          # noqa: E402
since = float(config.BSTOCK_RESTORED_TS)
check("the restore moment is 10 Nov 2026 00:00 PKT", _t.strftime("%d %b %H:%M", _t.gmtime(since + 5 * 3600)) == "10 Nov 00:00")
_c = store._open()
for t, sy, d, o, stt, r in (("elite_star", "SNDKBUSDT", "LONG", since + 100, "CLOSED", 0.5),
                            ("elite_star", "SNDKBUSDT", "LONG", since + 200, "CLOSED", -1.0),
                            ("elite_star", "NVDABUSDT", "SHORT", since + 300, "OPEN", None),
                            ("elite_star", "SNDKBUSDT", "LONG", since - 1000, "CLOSED", 1.0),    # before the restore
                            ("elite_star", "SOLUSDT", "LONG", since + 100, "CLOSED", 2.0),       # crypto: never counted
                            ("star_prime", "TQQQBUSDT", "LONG", since + 100, "VOID", -50.0),     # thin-stop row: never counted
                            ("star_prime", "TQQQBUSDT", "LONG", since + 150, "CLOSED", 0.3)):
    _c.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, stop0, tp1, tp2, peak, opened_at, status, pnl_r, closed_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (t, sy, d, 100.0, 96.0, 96.0, 106.0, 110.0, 100.0, o, stt, r, (o + 60 if stt != "OPEN" else None)))
_c.commit()
_c.close()
dd = store.shadow_tokenized(sorted(config.TOKENIZED_STOCKS), since)
es = dd["tiers"].get("elite_star") or {}
check("⭐ tier: 3 tokenized closes all-time, 2 since the restore, 1 open; the crypto row is not counted",
      (es.get("n"), es.get("wins"), round(es.get("net_r", 9), 2), es.get("n_since"), es.get("wins_since"), round(es.get("net_since", 9), 2), es.get("open"))
      == (3, 2, 0.5, 2, 1, -0.5, 1), es)
sp = dd["tiers"].get("star_prime") or {}
check("a VOID (thin-stop) row never enters the tokenized record", (sp.get("n"), sp.get("n_since"), round(sp.get("net_r", 9), 2)) == (1, 1, 0.3), sp)
sy = dd["symbols"]
check("by stock, since the restore: SNDKB 2 closed, NVDAB 1 open, no crypto symbol",
      sy.get("SNDKBUSDT", {}).get("n") == 2 and sy.get("NVDABUSDT", {}).get("open") == 1 and "SOLUSDT" not in sy, sy)
check("no symbols → empty record", store.shadow_tokenized([], since)["tiers"] == {})
tc._TOK_CACHE.update(t=0.0, d=None)
note = tc.tok_note("SNDKBUSDT", "elite_star")
check("🏦 note on a tokenized star: the stream's tokenized record since 10 Nov, thin flag, crypto caveat",
      note.lstrip().startswith("🏦 tokenized stock · ⭐ stars on tokenized names since 10 Nov: 2 closed, 50% / -0.25R — thin")
      and note[:1] == chr(10) and note.endswith("the 🕐 cell is crypto-measured"), note)
check("a coin gets no 🏦 note", tc.tok_note("SOLUSDT", "elite_star") == "" and tc.tok_note(None, "elite_star") == "")
check("a tokenized bell on a stream with no tokenized close says so", "💥🥇 pairs on tokenized names since 10 Nov: no closes yet" in tc.tok_note("NVDABUSDT", "prime_trig"))
ewt = dict(base="SNDKB", side="LONG", symbol="SNDKBUSDT", entry0=1.0, stop=0.95, tp1=1.06, tp2=1.1, oneh="LIVE", star=True, fired_at=_t.time())
v = rs.verdict_text(ewt, 0.3, _t.time())
check("⏱ verdict on a tokenized star ends with the 🏦 line", v.split(chr(10))[-1].startswith("🏦 tokenized stock"), v)
g = rs.go_text(ewt, 0.4, 1800, 1.02, _t.time())
check("GO reply on a tokenized star: the five lines + the 🏦 line", len(g.split(chr(10))) == 6 and g.split(chr(10))[-1].startswith("🏦 tokenized stock"), g)
vc = rs.verdict_text(dict(ewt, symbol="SOLUSDT", base="SOL"), 0.3, _t.time())
check("the same replies on a coin are unchanged (no 🏦)", "🏦" not in vc and "🏦" not in rs.go_text(dict(ewt, symbol="SOLUSDT"), 0.4, 1800, 1.02, _t.time()))
check("worker: the 🏦 note rides the star card, revival, pairs, 💥🥇, APEX V2 + verdict, TP1 ping", W.count("tg_cells.tok_note(") >= 7, W.count("tg_cells.tok_note("))
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("page: the 🏦 TOKENIZED DESK block under the Decision Desk, cached",
      "🏦 TOKENIZED DESK — tokenized stocks, their own record" in A and "def _tokenized_desk_cached(" in A and "_tokenized_desk_cached(int(time.time() // 600))" in A)
print("6. split records: a stream's record is crypto-only, tokenized seats live in tok:<tier> (2026-11-11)")
import shadow_trader as sht      # noqa: E402
check("the split switch is on and the prefix is tok:", config.BSTOCK_SPLIT_TIERS is True and store.TOK_PREFIX == "tok:")
check("desk_tier: tokenized -> tok:<tier>, crypto unchanged, never double-prefixed",
      store.desk_tier("elite_star", "SNDKBUSDT") == "tok:elite_star" and store.desk_tier("elite_star", "SOLUSDT") == "elite_star"
      and store.desk_tier("tok:elite_star", "SNDKBUSDT") == "tok:elite_star" and store.base_tier("tok:prime") == "prime" and store.base_tier("prime") == "prime")
before = {r["tier"]: r for r in store.shadow_summary(include_tok=True)}
moved = store.shadow_split_tokenized(sorted(config.TOKENIZED_STOCKS))
check("one-time relabel moves the 6 tokenized rows seeded above (VOID and OPEN included), crypto rows stay", moved == 6, moved)
check("relabel is idempotent", store.shadow_split_tokenized(sorted(config.TOKENIZED_STOCKS)) == 0)
summ = {r["tier"]: r for r in store.shadow_summary()}
check("stream summary is crypto-only: elite_star = the SOL row alone, no tok: tier listed",
      int(summ["elite_star"]["n"]) == 1 and abs(float(summ["elite_star"]["net_r"]) - 2.0) < 1e-9 and not any(t.startswith("tok:") for t in summ), summ)
allr = {r["tier"]: r for r in store.shadow_summary(include_tok=True)}
check("the tokenized tiers exist beside it when asked for", int(allr["tok:elite_star"]["n"]) == 3 and int(allr["tok:elite_star"]["open_n"]) == 1 and "tok:star_prime" in allr, allr)
tc._TOK_CACHE.update(t=0.0, d=None)
dd2 = store.shadow_tokenized(sorted(config.TOKENIZED_STOCKS), since)
es2 = dd2["tiers"].get("elite_star") or {}
check("the tokenized read still keys by the stream and gives the same record after the relabel",
      (es2.get("n"), es2.get("wins"), round(es2.get("net_r", 9), 2), es2.get("n_since"), es2.get("open")) == (3, 2, 0.5, 2, 1) and "tok:elite_star" not in dd2["tiers"], dd2["tiers"])
check("the 🏦 bell line still reads it", "2 closed, 50% / -0.25R" in tc.tok_note("SNDKBUSDT", "elite_star"))
rs._CACHE.clear()
check("the bell's stream record (rung_stats.tier_rec) counts crypto only", rs.tier_rec("elite_star")[0] == 1, rs.tier_rec("elite_star"))
ok_t = sht.open_from_signal("prime", {"symbol": "NVDABUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0}, 100.0)
ok_c = sht.open_from_signal("prime", {"symbol": "ETHUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0}, 100.0)
opn = {(r["tier"], r["symbol"]) for r in store.shadow_open_trades()}
check("a new tokenized seat opens under tok:prime, a coin under prime", ok_t and ok_c and ("tok:prime", "NVDABUSDT") in opn and ("prime", "ETHUSDT") in opn, opn)
check("one open seat per tokenized tier + coin still holds", sht.open_from_signal("prime", {"symbol": "NVDABUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0}, 100.0) is False)
closed = sht.manage({"NVDABUSDT": 95.0, "ETHUSDT": 95.0})
check("the desk manages a tok: seat like any other (both stop out)", {c["tier"] for c in closed} >= {"tok:prime", "prime"}, [(c["tier"], c["reason"]) for c in closed])
check("recent form for the demo and the green light reads the stream's crypto rows only", store.shadow_recent_net("prime")["n"] == 1 and store.shadow_recent_net("tok:prime")["n"] == 1)
check("conf / heat / recent readers skip tok: tiers", all(not str(r.get("tier", "")).startswith("tok:") for r in store.shadow_recent(50)))
config.BSTOCK_SPLIT_TIERS = False
check("switch off -> a new tokenized seat shares the stream tier again", store.desk_tier("elite_star", "SNDKBUSDT") == "elite_star")
config.BSTOCK_SPLIT_TIERS = True
check("worker: the one-time relabel runs in cycle() beside the hygiene sweep", "store.shadow_split_tokenized(sorted(getattr(config, \"TOKENIZED_STOCKS\", ())))" in W)
print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)

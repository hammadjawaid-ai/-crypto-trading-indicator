"""Page-speed patch 2 — the two boards left after the warmer: THE NUMBERS /
PRESSING fetched one ticker per armed level (sequential HTTP, ~12s) and the
EDGE MINER re-mined every desk trade on every load (~10s).
1. binance_client.prime_prices(): ONE /api/v3/ticker/price call fills the
   15s price cache for every symbol, so per-symbol lookups become cache hits
   (same endpoint, same numbers). Guarded so it runs at most once per TTL.
2. _render_brain_memory primes once at the top; THE NUMBERS block primes again
   for its own rows (cache-guarded, so normally free).
3. EDGE MINER report cached 10 min (st.cache_data) — a report over closed
   desk trades, not a signal."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


B = open(ROOT + "binance_client.py", encoding="utf-8").read()
B = rep(B,
        "def get_ticker_price(symbol: str) -> float | None:\n",
        "_PX_PRIME_TS = 0.0\n"
        "\n"
        "\n"
        "def prime_prices(symbols=None) -> int:\n"
        "    \"\"\"⚡ page-speed (2026-10-04): fill the 15s price cache for EVERY\n"
        "    symbol with ONE /api/v3/ticker/price call (weight 2) instead of one\n"
        "    call per symbol. Same endpoint, same numbers; get_ticker_price then\n"
        "    hits the cache. Runs at most once per _PX_TTL; fail-soft (returns\n"
        "    0 and the per-symbol path works exactly as before).\"\"\"\n"
        "    global _PX_PRIME_TS\n"
        "    if time.time() - _PX_PRIME_TS < _PX_TTL:\n"
        "        return 0\n"
        "    try:\n"
        "        data = _get(\"/api/v3/ticker/price\")\n"
        "    except BinanceError:\n"
        "        return 0\n"
        "    want = set(symbols) if symbols else None\n"
        "    n = 0\n"
        "    now = time.time()\n"
        "    for row in data or []:\n"
        "        try:\n"
        "            sym = row[\"symbol\"]\n"
        "            if want is not None and sym not in want:\n"
        "                continue\n"
        "            _PX_CACHE[sym] = (now, float(row[\"price\"]))\n"
        "            n += 1\n"
        "        except (KeyError, TypeError, ValueError):\n"
        "            continue\n"
        "    _PX_PRIME_TS = now\n"
        "    return n\n"
        "\n"
        "\n"
        "def get_ticker_price(symbol: str) -> float | None:\n",
        "prime_prices")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        "        _al_lines = []\n"
        "        for _r in _al_rows:\n"
        "            try:\n"
        "                _lp = float(binance_client.get_ticker_price(\n",
        "        try:   # ⚡ one ticker call for every armed level (page-speed)\n"
        "            binance_client.prime_prices([_r.get(\"symbol\") for _r in _al_rows])\n"
        "        except Exception:\n"
        "            pass\n"
        "        _al_lines = []\n"
        "        for _r in _al_rows:\n"
        "            try:\n"
        "                _lp = float(binance_client.get_ticker_price(\n",
        "numbers board prime")
A = rep(A, "                _rep = _em.mine()\n",
        "                _rep = _edge_mine_cached(int(time.time() // 600))   # ⚡ 10-min cache\n",
        "edge miner call")
A = rep(A,
        "def _worker_scan_age_min():\n",
        "@st.cache_data(ttl=600, show_spinner=False)\n"
        "def _edge_mine_cached(_bust: int = 0):\n"
        "    \"\"\"🧠 EDGE MINER report over closed desk trades — a 10-min cached\n"
        "    read of the same miner (page-speed 2026-10-04; it is a report,\n"
        "    not a signal, and the desk ledger moves every ~17 min).\"\"\"\n"
        "    import edge_miner as _em_c\n"
        "    return _em_c.mine()\n"
        "\n"
        "\n"
        "def _worker_scan_age_min():\n",
        "edge cache def")
# prime once at the top of the brain-memory renderer (covers its ticker loops)
i = A.find("def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):")
if i < 0:
    raise SystemExit("renderer def not found")
j = A.find('"""', i)
j = A.find('"""', j + 3) + 3           # end of the docstring
k = A.find("\n", j) + 1
A = A[:k] + ("    try:   # ⚡ one ticker call primes every per-symbol price lookup below\n"
             "        binance_client.prime_prices()\n"
             "    except Exception:\n"
             "        pass\n") + A[k:]

T = open(ROOT + ".pt_speed_test.py", encoding="utf-8").read()
T = rep(T,
        "src_bc = open(r\"F:\\Trading Indicator\\binance_client.py\", encoding=\"utf-8\").read()\n",
        "src_bc = open(r\"F:\\Trading Indicator\\binance_client.py\", encoding=\"utf-8\").read()\n"
        "# prime_prices fills the price cache from one payload and is TTL-guarded\n"
        "bc._PX_CACHE.clear(); bc._PX_PRIME_TS = 0.0\n"
        "_og = bc._get\n"
        "bc._get = lambda path, params=None, max_attempts=4: [{\"symbol\": \"AAAUSDT\", \"price\": \"1.5\"}, {\"symbol\": \"BBBUSDT\", \"price\": \"2.5\"}, {\"symbol\": \"X\", \"price\": \"bad\"}]\n"
        "try:\n"
        "    if bc.prime_prices([\"AAAUSDT\", \"BBBUSDT\"]) != 2 or bc.get_ticker_price(\"BBBUSDT\") != 2.5:\n"
        "        fails.append(\"prime_prices did not fill the price cache\")\n"
        "    bc._get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(\"primed again inside the TTL\"))\n"
        "    if bc.prime_prices() != 0:\n"
        "        fails.append(\"prime_prices must be TTL-guarded\")\n"
        "    if bc.get_ticker_price(\"AAAUSDT\") != 1.5:\n"
        "        fails.append(\"primed price not served from cache\")\n"
        "except RuntimeError as exc:\n"
        "    fails.append(str(exc))\n"
        "finally:\n"
        "    bc._get = _og; bc._PX_CACHE.clear(); bc._PX_PRIME_TS = 0.0\n"
        "for need in (\"binance_client.prime_prices([_r.get(\\\"symbol\\\") for _r in _al_rows])\", \"binance_client.prime_prices()\", \"_edge_mine_cached(int(time.time() // 600))\", \"def _edge_mine_cached(\"):\n"
        "    if need not in A:\n"
        "        fails.append(f\"patch-2 wiring missing: {need}\")\n"
        "if \"_rep = _em.mine()\" in A:\n"
        "    fails.append(\"edge miner still mines on every load\")\n",
        "test additions")

for path, s in (("binance_client.py", B), ("app.py", A), (".pt_speed_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched binance_client.py, app.py, .pt_speed_test.py")

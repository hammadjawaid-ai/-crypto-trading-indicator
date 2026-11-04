"""📡 CHANNEL DESK — external Telegram signal channels measured FORWARD, each in its own demo book
(user 2026-11-05: "yes lets do it … have a demo v3 as well … for another channel crypto cycle vip").

Nothing here touches the GEN 18 demo, the desk tiers, our own streams' bells or the page's existing
boards: own state file, own books, own bell switch (TG_CHANNEL_DESK).

Every worker cycle, channel_desk.tick():
  1. drains the reader inbox. A SIGNAL post (coin · side · entry · targets · stop · leverage) is parsed,
     recorded, opened as a seat in that channel's book at the live price, stamped with our context and
     rung with the 🚦 light. A RESULT post ("Tp1 ✅", "All Hit", "SL hit") is tied to its signal as the
     channel's own CLAIM, so claimed vs printed sit side by side forever.
  2. manages the open seats on the 15m candle path, not the live tick: LIQUIDATION first (adverse move ×
     leverage ≥ 95% of margin — at 25x that is ~3.8%, usually long BEFORE the channel's stop), then the
     stop, then the channel's own ladder (50% off at TP1 → stop to entry · 25% at TP2 · the rest at TP3 or
     the 48h time stop). Fees 0.05% per side on notional. Same-bar stop and target = stop.
  3. keeps the forward truth table per channel (TP1 printed first / stop / liquidated / time · R at their
     stop · R with the liquidation distance as the stop) and the 🚦 light: ⚪ UNRATED until 60 resolved,
     then 🟢 TAKE / 🟡 / 🔴 SKIP from the channel's own forward R and the stamps that held in both halves.

Reader (own thread, started lazily by tick()):
  A. TELETHON USER SESSION — env TG_API_ID · TG_API_HASH · TG_SESSION (a StringSession the user generates
     with research_meta/tg_pull.py --session and pastes into Render; never into chat). Reads any channel
     the account is subscribed to, admin or not. Channels matched by title (CHANNELS[*]["match"]).
  B. BOT RELAY — env CHANNEL_RELAY_CHAT_ID: a private group the user forwards posts into (our bot inside);
     the forward header names the source channel. Bot API getUpdates long-poll. Also catches channel_post
     updates if the bot is ever made admin of a channel directly.
  C. DROP FILE — <STATE_DIR>/.channel_inbox.jsonl, one JSON per line {channel, id, ts, text, reply_text}:
     the guard test and manual feeds. Drained on every tick.
"""
from __future__ import annotations

import json
import os
import queue
import re
import sqlite3
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

import config
import binance_client as bc
import telegram_notify as tg

STATE_FILE = str(config.state_path(".channel_desk.json"))
INBOX_FILE = str(config.state_path(".channel_inbox.jsonl"))

CHANNELS = {
    "andrew": dict(title="Crypto Andrew VIP", match=("crypto andrew vip",), book="v2"),
    "cycle": dict(title="Crypto Cycle VIP", match=("crypto cycle vip", "crypto cycle 360 vip", "cycle 360 vip", "cryptocycle vip"), book="v3"),
}
BOOK_START = 1000.0
RISK_PCT = 0.02            # the channels' own rule: 2% of the wallet as margin per trade
MAX_LEV = 25
FEE = 0.0005               # taker, per side, on notional
LIQ_FRAC = 0.95            # liquidated when the adverse move eats 95% of the margin
MAX_HOLD_H = 48
LIGHT_MIN_RESOLVED = 60
TG_CHANNEL_DESK = True     # 📡 bell per parsed signal + the resolution reply in its thread
PKT = timedelta(hours=5)

_LOCK = threading.RLock()
_INBOX: "queue.Queue[dict]" = queue.Queue()
_READER = {"thread": None, "status": "not started", "mode": "-", "last_at": 0.0, "err": "", "chats": {}}


def _log(msg: str) -> None:
    print(f"📡 channel desk: {msg}", flush=True)


# ───────────────────────────── the parser (same rules as research_meta/channel_study.py) ─────────────────────────────
NUM = r"([0-9]*\.?[0-9]+)"
SYM_RX = [re.compile(r"#?\b([A-Z0-9]{1,12})\s*/\s*USDT\b"), re.compile(r"#?\b([A-Z0-9]{2,12})USDT(?:\.P|\s*PERP|\s*Perpetual)?\b"),
          re.compile(r"\$([A-Z0-9]{2,12})\b")]
SIDE_RX = re.compile(r"\b(LONG|BUY|SHORT|SELL)\b", re.I)
ENTRY_RX = [re.compile(r"entry(?:\s*(?:price|zone|at))?\s*[:@\-–=]*\s*" + NUM + r"(?:\s*[-–/to]+\s*" + NUM + ")?", re.I),
            re.compile(r"\b(?:LONG|SHORT|BUY|SELL)\b\s*(?:@|at)?\s*" + NUM, re.I),
            re.compile(r"(?:🟢|🔴)\s*(?:LONG|SHORT)\s*" + NUM, re.I)]
TP_RX = re.compile(r"(?:TP|T\.P\.?|Target|Take[\s-]*profit)\s*(\d{0,2})\s*[:@\-–=)]*\s*" + NUM, re.I)
CIRC_RX = re.compile(r"[❶-❿➀-➓①-⑳]\s*" + NUM + r"|(\d)️?⃣\s*" + NUM)   # ➊ 0.0285 · ❶ · ① · 1️⃣
TPLIST_RX = re.compile(r"(?:targets?|take[\s-]*profits?)\s*[:\-–]\s*([0-9.,\s/\-–]+)", re.I)
SL_RX = re.compile(r"(?:SL|S\.L\.?|Stop[\s-]*loss|Stoploss|Stop)\s*[:@\-–=)]*\s*" + NUM + r"\s*(%)?", re.I)
LEV_RX = re.compile(r"(?:leverage|lev)\s*[:\-–=]*\s*(?:cross|isolated)?\s*x?\s*(\d{1,3})\s*x?|\b(\d{1,3})\s*x\b", re.I)
RESULT_RX = re.compile(r"\b(?:tp|target)\s*(\d)|all\s*(?:targets?|tp|hit)|✅|\bsl\s*hit|stop\s*(?:loss\s*)?hit|stopped\s*out|❌|🛑|liquidat", re.I)


def parse_signal(text: str) -> dict | None:
    """coin · side · entry · targets · stop · leverage from one post, or None when it is not a signal."""
    t = (text or "").replace("​", "")
    sym = None
    for rx in SYM_RX:
        m = rx.search(t)
        if m and m.group(1) not in ("USDT", "TP", "SL", "TARGET", "STOP"):
            sym = m.group(1); break
    ms = SIDE_RX.search(t)
    side = 1 if (ms and ms.group(1).upper() in ("LONG", "BUY")) else -1 if ms else (1 if "🟢" in t else -1 if "🔴" in t else 0)
    if not sym or side == 0:
        return None
    entry = entry_hi = None
    for rx in ENTRY_RX:
        m = rx.search(t)
        if m:
            entry = float(m.group(1))
            entry_hi = float(m.group(2)) if (m.lastindex and m.lastindex >= 2 and m.group(2)) else None
            break
    tps = [float(m.group(1) or m.group(3)) for m in CIRC_RX.finditer(t)]
    if not tps:
        tps = [float(m.group(2)) for m in TP_RX.finditer(t)]
    if not tps:
        m = TPLIST_RX.search(t)
        if m:
            tps = [float(x) for x in re.findall(NUM, m.group(1))]
    sl = sl_pct = None
    m = SL_RX.search(t)
    if m:
        v = float(m.group(1))
        if m.group(2):
            sl_pct = v
        else:
            sl = v
    lev = None
    m = LEV_RX.search(t)
    if m:
        lev = int(m.group(1) or m.group(2))
    if entry is None or not tps:
        return None
    if entry_hi:
        entry = (entry + entry_hi) / 2
    tps = [x for x in tps if (x > entry if side == 1 else x < entry)]
    if not tps:
        return None
    if sl is None and sl_pct:
        sl = entry * (1 - side * sl_pct / 100)
    if sl is not None and not ((sl < entry) if side == 1 else (sl > entry)):
        sl = None
    return dict(sym=sym.upper(), side=side, entry=entry, tps=tps[:3], sl=sl, lev=lev)


def classify_result(text: str) -> str | None:
    """'tp1' / 'tp2' / 'tp3' / 'all' / 'sl' for a result post, None otherwise."""
    t = (text or "").strip()
    if len(t) > 160 or not RESULT_RX.search(t):
        return None
    if re.search(r"\bsl\b|stop|❌|🛑|liquidat", t, re.I):
        return "sl"
    if re.search(r"all\s*(?:targets?|tp|hit)", t, re.I):
        return "all"
    m = re.search(r"(?:tp|target)\s*(\d)", t, re.I)
    if m:
        return f"tp{m.group(1)}"
    return "tp1" if "✅" in t else None


# ───────────────────────────── state ─────────────────────────────
def _fresh_book(ck: str) -> dict:
    return {"channel": ck, "equity": BOOK_START, "start": BOOK_START, "peak": BOOK_START, "open": [], "closed": [], "since": time.time()}


def _fresh() -> dict:
    return {"ver": 1, "since": time.time(), "books": {c["book"]: _fresh_book(k) for k, c in CHANNELS.items()},
            "signals": [], "seen": {}, "reader": {}}


def load() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict) or "books" not in st:
            raise ValueError("bad state")
    except Exception:
        st = _fresh()
    for k, c in CHANNELS.items():
        st["books"].setdefault(c["book"], _fresh_book(k))
    st.setdefault("signals", []); st.setdefault("seen", {}); st.setdefault("reader", {})
    return st


def save(st: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, STATE_FILE)


def channel_of_title(title: str) -> str | None:
    t = (title or "").lower()
    for k, c in CHANNELS.items():
        if any(m in t for m in c["match"]):
            return k
    return None


# ───────────────────────────── the stamp (our context at the post) ─────────────────────────────
def _pkt_window(ts: float) -> str:
    h = (datetime.fromtimestamp(ts, tz=timezone.utc) + PKT).hour
    return "01–05" if 1 <= h < 5 else "05–09" if h < 9 else "09–13" if h < 13 else "13–17" if h < 17 else "17–21" if h < 21 else "21–01"


def _btc24() -> float | None:
    try:
        k = bc.get_klines("BTCUSDT", "1h", 26)
        if k is None or len(k) < 25:
            return None
        return float(k["close"].iloc[-1] / k["close"].iloc[-25] - 1) * 100
    except Exception:
        return None


def _our_fires(sym: str, side: int, ts: float) -> list:
    """Our own desk tiers that opened the same coin+side in the 4h before the post (read-only ledger peek)."""
    try:
        import worker_store as store
        db = store.stats().get("db")
        if not db or not os.path.exists(str(db)):
            return []
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = con.execute("select distinct tier from shadow_trades where symbol=? and side=? and opened_at between ? and ?",
                               (sym + "USDT", "LONG" if side == 1 else "SHORT", ts - 4 * 3600, ts + 900)).fetchall()
        finally:
            con.close()
        return sorted({r[0] for r in rows})
    except Exception:
        return []


def stamp_for(sig: dict) -> dict:
    btc = _btc24()
    return {"btc24": btc, "btc_band": None if btc is None else ("≤−1.5" if btc <= -1.5 else "flat" if btc <= 1.5 else ">+1.5"),
            "win": _pkt_window(sig["ts"]), "weekend": int((datetime.fromtimestamp(sig["ts"], tz=timezone.utc) + PKT).weekday() >= 5),
            "ours": _our_fires(sig["sym"], sig["side"], sig["ts"])}


# ───────────────────────────── truth table + light ─────────────────────────────
def truth(st: dict, ck: str) -> dict:
    res = [s for s in st["signals"] if s["channel"] == ck and s.get("result")]
    n = len(res)
    out = {"n": n, "tp1": 0, "stop": 0, "liq": 0, "time": 0, "r_their": None, "r_liq": None, "win_liq": None, "claims": 0, "claims_tp": 0,
           "claimed_but_lost": 0, "lost_unposted": 0, "signals": sum(1 for s in st["signals"] if s["channel"] == ck)}
    if not n:
        return out
    for s in res:
        out[s["result"]["first"]] = out.get(s["result"]["first"], 0) + 1
    rt = [s["result"]["r_their"] for s in res if s["result"].get("r_their") is not None]
    rl = [s["result"]["r_liq"] for s in res if s["result"].get("r_liq") is not None]
    out["r_their"] = sum(rt) / len(rt) if rt else None
    out["r_liq"] = sum(rl) / len(rl) if rl else None
    out["win_liq"] = 100.0 * sum(1 for x in rl if x > 0) / len(rl) if rl else None
    for s in [x for x in st["signals"] if x["channel"] == ck]:
        if s.get("claims"):
            out["claims"] += 1
            if any(c["kind"] != "sl" for c in s["claims"]):
                out["claims_tp"] += 1
                if s.get("result") and s["result"]["first"] in ("stop", "liq"):
                    out["claimed_but_lost"] += 1
        elif s.get("result") and s["result"]["first"] in ("stop", "liq"):
            out["lost_unposted"] += 1
    return out


def _held_cells(st: dict, ck: str) -> list:
    """Stamp cells that sorted the forward R (liquidation stop) in BOTH halves — the only bar we trust."""
    res = sorted([s for s in st["signals"] if s["channel"] == ck and s.get("result") and s["result"].get("r_liq") is not None],
                 key=lambda s: s["ts"])
    if len(res) < LIGHT_MIN_RESOLVED:
        return []
    half = len(res) // 2
    base = sum(s["result"]["r_liq"] for s in res) / len(res)
    feats = {
        "side": lambda s: "LONG" if s["side"] == 1 else "SHORT",
        "btc": lambda s: (s.get("stamp") or {}).get("btc_band"),
        "clock": lambda s: (s.get("stamp") or {}).get("win"),
        "weekend": lambda s: "weekend" if (s.get("stamp") or {}).get("weekend") else "weekday",
        "ours": lambda s: "our desk fired too" if (s.get("stamp") or {}).get("ours") else "no desk fire",
        "stop": lambda s: "stop ≤5%" if (s.get("stop_pct") or 0) <= 5 else "stop >5%",
        "tp1": lambda s: "TP1 ≥2%" if (s.get("tp1_pct") or 0) >= 2 else "TP1 <2%",
    }
    held = []
    for name, fn in feats.items():
        cells = {}
        for i, s in enumerate(res):
            v = fn(s)
            if v is None:
                continue
            c = cells.setdefault(v, [[], []]); c[0 if i < half else 1].append(s["result"]["r_liq"])
        for v, (h1, h2) in cells.items():
            if len(h1) >= 8 and len(h2) >= 8:
                m1, m2 = sum(h1) / len(h1), sum(h2) / len(h2); m = (sum(h1) + sum(h2)) / (len(h1) + len(h2))
                if (m1 - base) * (m2 - base) > 0 and abs(m - base) >= 0.10:
                    held.append({"feat": name, "cell": v, "r": m, "n": len(h1) + len(h2), "lift": m - base})
    return held


def light_for(st: dict, ck: str, sig: dict | None = None) -> dict:
    tr = truth(st, ck)
    if tr["n"] < LIGHT_MIN_RESOLVED:
        return {"code": "UNRATED", "emoji": "⚪", "text": f"UNRATED — forward record {tr['n']} of {LIGHT_MIN_RESOLVED} resolved"
                + (f" · so far {tr['win_liq']:.0f}% / {tr['r_liq']:+.2f}R at the liquidation stop" if tr["n"] >= 10 and tr["r_liq"] is not None else "")}
    r = tr["r_liq"] if tr["r_liq"] is not None else 0.0
    code, emoji = ("TAKE", "🟢") if r >= 0.10 else ("SKIP", "🔴") if r <= 0.0 else ("THIN", "🟡")
    why = f"channel forward {tr['win_liq']:.0f}% / {r:+.2f}R at the liquidation stop ({tr['n']})"
    if sig is not None:
        for h in _held_cells(st, ck):
            v = {"side": lambda s: "LONG" if s["side"] == 1 else "SHORT", "btc": lambda s: (s.get("stamp") or {}).get("btc_band"),
                 "clock": lambda s: (s.get("stamp") or {}).get("win"), "weekend": lambda s: "weekend" if (s.get("stamp") or {}).get("weekend") else "weekday",
                 "ours": lambda s: "our desk fired too" if (s.get("stamp") or {}).get("ours") else "no desk fire",
                 "stop": lambda s: "stop ≤5%" if (s.get("stop_pct") or 0) <= 5 else "stop >5%",
                 "tp1": lambda s: "TP1 ≥2%" if (s.get("tp1_pct") or 0) >= 2 else "TP1 <2%"}[h["feat"]](sig)
            if v == h["cell"]:
                if h["r"] >= 0.10 and code != "TAKE":
                    code, emoji = "TAKE", "🟢"
                elif h["r"] <= 0.0 and code != "SKIP":
                    code, emoji = "SKIP", "🔴"
                why += f" · {h['cell']}: {h['r']:+.2f}R ({h['n']}, both halves)"
    return {"code": code, "emoji": emoji, "text": f"{code} — {why}"}


# ───────────────────────────── the book ─────────────────────────────
def _live(sym: str) -> float | None:
    try:
        px = bc.get_ticker_price(sym + "USDT")
        return float(px) if px else None
    except Exception:
        return None


def _open_seat(book: dict, sig: dict, px: float) -> dict:
    lev = max(1, min(MAX_LEV, int(sig.get("lev") or 10)))
    margin = round(book["equity"] * RISK_PCT, 4)
    notional = margin * lev
    qty = notional / px
    gap = px - sig["entry"]                         # their geometry re-anchored on the fill
    seat = {"sig": sig["id"], "sym": sig["sym"], "side": sig["side"], "entry": px, "their_entry": sig["entry"], "lev": lev, "margin": margin,
            "notional": notional, "qty": qty, "qty_left": qty, "stop": (sig["sl"] + gap) if sig.get("sl") else None, "stop0": (sig["sl"] + gap) if sig.get("sl") else None,
            "tps": [t + gap for t in sig["tps"]], "liq": px * (1 - sig["side"] * LIQ_FRAC / lev), "opened_at": time.time(),
            "tp_hits": [], "be": False, "fees": notional * FEE, "realized": -notional * FEE, "last_bar": 0, "fav": 0.0, "adv": 0.0}
    book["equity"] = round(book["equity"] - notional * FEE, 4)      # the entry fee is paid at the open
    book["open"].append(seat)
    return seat


def _close_part(book: dict, seat: dict, qty: float, px: float, reason: str, at: float, st: dict) -> dict:
    qty = min(qty, seat["qty_left"])
    pnl = qty * (px - seat["entry"]) * seat["side"] - qty * px * FEE
    seat["realized"] += pnl; seat["fees"] += qty * px * FEE; seat["qty_left"] -= qty
    book["equity"] = round(book["equity"] + pnl, 4)
    book["peak"] = max(book["peak"], book["equity"])
    rec = {"sig": seat["sig"], "sym": seat["sym"], "side": seat["side"], "entry": seat["entry"], "exit": px, "lev": seat["lev"], "qty": qty,
           "pnl_usd": round(pnl, 4), "pnl_margin_pct": round(pnl / seat["margin"] * 100, 2), "reason": reason, "opened_at": seat["opened_at"], "closed_at": at}
    book["closed"].append(rec)
    book["closed"] = book["closed"][-400:]
    if seat["qty_left"] <= seat["qty"] * 1e-6:
        seat["qty_left"] = 0.0
        book["open"] = [s for s in book["open"] if s is not seat]
        sig = next((s for s in st["signals"] if s["id"] == seat["sig"]), None)
        if sig is not None:
            sig["status"] = "closed"; sig["closed_at"] = at
            sig["seat_pnl_usd"] = round(seat["realized"], 4); sig["seat_pnl_margin_pct"] = round(seat["realized"] / seat["margin"] * 100, 1)
    return rec


def _first_result(st: dict, seat: dict, first: str, at: float) -> dict | None:
    """The truth-table entry: what printed FIRST on the candle path, in R at their stop and at the liquidation stop."""
    sig = next((s for s in st["signals"] if s["id"] == seat["sig"]), None)
    if sig is None or sig.get("result"):
        return None
    e = seat["entry"]; tp1d = abs(seat["tps"][0] - e); liqd = abs(seat["liq"] - e)
    sd = abs(seat["stop0"] - e) if seat.get("stop0") else None
    fee_r_liq = 2 * FEE * e / liqd
    r_liq = (tp1d / liqd - fee_r_liq) if first == "tp1" else (-1.0 - fee_r_liq) if first in ("liq", "stop") and (sd is None or liqd <= sd) else \
            (-(sd / liqd) - fee_r_liq) if first == "stop" else (seat["fav"] / 100 * e / liqd - fee_r_liq) if first == "time" else None
    r_their = None
    if sd:
        fee_r = 2 * FEE * e / sd
        r_their = (tp1d / sd - fee_r) if first == "tp1" else (-1.0 - fee_r) if first == "stop" else (-(liqd / sd) - fee_r) if first == "liq" else \
                  (seat["fav"] / 100 * e / sd - fee_r) if first == "time" else None
    sig["result"] = {"first": first, "at": at, "hours": round((at - seat["opened_at"]) / 3600, 2), "r_their": None if r_their is None else round(r_their, 3),
                     "r_liq": None if r_liq is None else round(r_liq, 3), "fav_pct": round(seat["fav"], 2), "adv_pct": round(seat["adv"], 2)}
    return sig["result"]


def _bars_after(sym: str, since_ms: int, limit: int):
    try:
        k = bc.get_klines(sym + "USDT", "15m", limit)
    except Exception:
        return []
    if k is None or not len(k):
        return []
    out = []
    now_ms = int(time.time() * 1000)
    for ts, row in k.iterrows():
        ot = int(ts.timestamp() * 1000)
        if ot <= since_ms or ot + 900_000 > now_ms:        # completed bars only, after the last one seen
            continue
        out.append((ot, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    return out


def manage(st: dict, book: dict) -> list:
    events = []
    for seat in list(book["open"]):
        since = seat["last_bar"] or int(seat["opened_at"] // 900 * 900 * 1000)
        bars = _bars_after(seat["sym"], since, min(200, int((time.time() * 1000 - since) // 900_000) + 3))
        for ot, o, h, l, c in bars:
            side = seat["side"]; e = seat["entry"]
            fav = (h - e) / e * 100 if side == 1 else (e - l) / e * 100
            adv = (e - l) / e * 100 if side == 1 else (h - e) / e * 100
            seat["fav"] = max(seat["fav"], fav); seat["adv"] = max(seat["adv"], adv)
            at = ot / 1000 + 900
            hit_liq = (l <= seat["liq"]) if side == 1 else (h >= seat["liq"])
            hit_stop = seat["stop"] is not None and ((l <= seat["stop"]) if side == 1 else (h >= seat["stop"]))
            if hit_liq or hit_stop:                                   # adverse first — conservative
                if hit_liq and (seat["stop"] is None or (abs(seat["liq"] - e) <= abs(seat["stop"] - e))):
                    r = _first_result(st, seat, "liq", at)
                    events.append(("liq", seat, _close_part(book, seat, seat["qty_left"], seat["liq"], "liquidated", at, st), r))
                else:
                    first = "stop" if not seat["be"] else None
                    r = _first_result(st, seat, "stop", at) if first else None
                    events.append(("stop" if not seat["be"] else "be", seat, _close_part(book, seat, seat["qty_left"], seat["stop"], "stop" if not seat["be"] else "stop at entry", at, st), r))
                break
            for i, tp in enumerate(seat["tps"]):
                if i in seat["tp_hits"]:
                    continue
                if (h >= tp) if side == 1 else (l <= tp):
                    seat["tp_hits"].append(i)
                    r = _first_result(st, seat, "tp1", at) if i == 0 else None
                    if i == 0:
                        rec = _close_part(book, seat, seat["qty"] * 0.5, tp, "TP1 · 50% banked", at, st); seat["be"] = True; seat["stop"] = e
                    elif i == 1 and len(seat["tps"]) > 2:
                        rec = _close_part(book, seat, seat["qty"] * 0.25, tp, "TP2 · 25% banked", at, st)
                    else:
                        rec = _close_part(book, seat, seat["qty_left"], tp, f"TP{i + 1} · closed", at, st)
                    events.append((f"tp{i + 1}", seat, rec, r))
            if seat["qty_left"] <= 0:
                break
            if at - seat["opened_at"] >= MAX_HOLD_H * 3600:
                r = _first_result(st, seat, "time", at)
                events.append(("time", seat, _close_part(book, seat, seat["qty_left"], c, "48h time stop", at, st), r))
                break
            seat["last_bar"] = ot
    return events


# ───────────────────────────── bells ─────────────────────────────
def _fmt_px(x: float) -> str:
    return f"{x:.6g}"


def _fmt_signal_bell(sig: dict, seat: dict | None, light: dict, tr: dict) -> str:
    c = CHANNELS[sig["channel"]]
    e = sig["entry"]; side = "LONG" if sig["side"] == 1 else "SHORT"
    tp1 = sig["tps"][0]; tp1p = abs(tp1 - e) / e * 100
    lev = max(1, min(MAX_LEV, int(sig.get("lev") or 10)))
    liq = LIQ_FRAC / lev * 100
    lines = [f"📡 *CHANNEL SIGNAL* · {c['title']} → demo {c['book']}",
             f"*{sig['sym']} {side}* @ `{_fmt_px(e)}` · {sig.get('lev') or '?'}x · TP1 `{_fmt_px(tp1)}` ({tp1p:+.2f}%)"
             + (f" · TP2 `{_fmt_px(sig['tps'][1])}`" if len(sig["tps"]) > 1 else "") + (f" · TP3 `{_fmt_px(sig['tps'][2])}`" if len(sig["tps"]) > 2 else "")]
    if sig.get("sl"):
        sp = abs(sig["sl"] - e) / e * 100
        lines.append(f"SL `{_fmt_px(sig['sl'])}` ({-sp:.2f}%) · a win pays {tp1p / sp:.2f}R at their stop")
        if sp > liq:
            lines.append(f"⚠️ at {lev}x you are liquidated at −{liq:.1f}%, *before* their stop — the real risk is the whole margin")
    else:
        lines.append(f"no stop given → desk uses liquidation at {lev}x (−{liq:.1f}%) as the stop")
    lines.append(f"🚦 {light['emoji']} {light['text']}")
    stp = sig.get("stamp") or {}
    btc = stp.get("btc24")
    lines.append("🧭 our stamp: BTC day " + (f"{btc:+.1f}%" if btc is not None else "?") + f" · {stp.get('win', '?')} PKT" + (" · weekend" if stp.get("weekend") else "")
                 + " · our desk on this coin+side: " + ("/".join(stp.get("ours") or []) or "none"))
    if seat is not None:
        lines.append(f"🧾 demo {c['book']}: margin ${seat['margin']:.0f} × {seat['lev']}x, filled `{_fmt_px(seat['entry'])}` · 50% off at TP1 → stop to entry · 25% at TP2 · rest TP3 / 48h")
    else:
        lines.append(f"🧾 demo {c['book']}: no Binance price for {sig['sym']} — recorded, no seat")
    if tr["n"]:
        lines.append(f"📒 forward so far: {tr['n']} resolved · TP1 first {tr['tp1']} · stop {tr['stop']} · liquidated {tr['liq']} · time {tr['time']}"
                     + (f" · claimed wins that lost {tr['claimed_but_lost']} · losses never posted {tr['lost_unposted']}" if tr["claims"] else ""))
    return "\n".join(lines)


def _fmt_event_reply(kind: str, seat: dict, rec: dict, sig: dict) -> str:
    c = CHANNELS[sig["channel"]]
    hrs = (rec["closed_at"] - seat["opened_at"]) / 3600
    head = {"tp1": "🏦 *TP1 printed*", "tp2": "🏦 *TP2 printed*", "tp3": "🏁 *TP3 printed*", "stop": "🔴 *STOP printed*", "be": "⚪ *stopped at entry* (after TP1)",
            "liq": "💀 *LIQUIDATED* — their stop never printed", "time": "⏱ *48h time stop*"}.get(kind, kind)
    move = (rec["exit"] - seat["entry"]) / seat["entry"] * 100 * seat["side"]
    txt = f"{head} · {sig['sym']} {'LONG' if sig['side'] == 1 else 'SHORT'} · {move:+.2f}% after {hrs:.1f}h · demo {c['book']} {rec['pnl_margin_pct']:+.0f}% of margin (${rec['pnl_usd']:+.2f})"
    if kind == "tp1":
        txt += " · 50% banked, stop → entry"
    if sig.get("claims"):
        txt += " · channel posted: " + ", ".join(cl["kind"].upper() for cl in sig["claims"])
    return txt


# ───────────────────────────── inbox → ledger → book ─────────────────────────────
def _drain_dropfile() -> list:
    out = []
    try:
        if os.path.exists(INBOX_FILE):
            with open(INBOX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
            os.remove(INBOX_FILE)
    except Exception:
        pass
    return out


def ingest(st: dict, msg: dict) -> list:
    """One channel post → signal record + seat + bell, or a claim on an earlier signal. Returns bells to send."""
    ck = msg.get("channel")
    if ck not in CHANNELS:
        return []
    mid = str(msg.get("id") or int(msg.get("ts") or time.time()))
    seen = st["seen"].setdefault(ck, [])
    if mid in seen:
        return []
    seen.append(mid); st["seen"][ck] = seen[-2000:]
    text = msg.get("text") or ""
    ts = float(msg.get("ts") or time.time())
    bells = []
    sig = parse_signal(text)
    if sig:
        sig.update(id=f"{ck}:{mid}", channel=ck, msg_id=mid, ts=ts, text=text[:600], claims=[], status="open", stamp=stamp_for(dict(sig, ts=ts)),
                   tp1_pct=round(abs(sig["tps"][0] - sig["entry"]) / sig["entry"] * 100, 3),
                   stop_pct=round(abs(sig["sl"] - sig["entry"]) / sig["entry"] * 100, 3) if sig.get("sl") else None)
        book = st["books"][CHANNELS[ck]["book"]]
        px = _live(sig["sym"])
        seat = None
        if px and px > 0:
            seat = _open_seat(book, sig, px)
            sig["seat"] = {"entry": px, "lev": seat["lev"], "margin": seat["margin"]}
        else:
            sig["status"] = "no_price"
        tr = truth(st, ck)
        light = light_for(st, ck, sig)
        sig["light"] = light
        st["signals"].append(sig)
        st["signals"] = st["signals"][-3000:]
        bells.append(("signal", sig, _fmt_signal_bell(sig, seat, light, tr)))
        return bells
    kind = classify_result(text)
    if kind:
        q = parse_signal(msg.get("reply_text") or "")
        target = None
        cands = [s for s in st["signals"] if s["channel"] == ck]
        if q:
            target = next((s for s in reversed(cands) if s["sym"] == q["sym"] and s["side"] == q["side"] and abs(s["entry"] - q["entry"]) / q["entry"] < 1e-6), None)
        if target is None and msg.get("reply_id"):
            target = next((s for s in reversed(cands) if s["msg_id"] == str(msg["reply_id"])), None)
        if target is not None:
            target["claims"].append({"kind": kind, "ts": ts, "text": text[:80]})
        else:
            st.setdefault("orphan_claims", []).append({"channel": ck, "kind": kind, "ts": ts, "text": text[:80], "quoted": (msg.get("reply_text") or "")[:120]})
            st["orphan_claims"] = st["orphan_claims"][-300:]
    return bells


def tick() -> dict:
    """Called once per worker cycle. Never raises."""
    summary = {"ingested": 0, "events": 0, "bells": 0}
    try:
        _ensure_reader()
        with _LOCK:
            st = load()
            msgs = _drain_dropfile()
            while True:
                try:
                    msgs.append(_INBOX.get_nowait())
                except queue.Empty:
                    break
            msgs.sort(key=lambda m: float(m.get("ts") or 0))
            bells = []
            for m in msgs:
                try:
                    bells += ingest(st, m); summary["ingested"] += 1
                except Exception as exc:
                    _log(f"ingest error: {exc}")
            for ck, c in CHANNELS.items():
                book = st["books"][c["book"]]
                try:
                    for kind, seat, rec, _r in manage(st, book):
                        summary["events"] += 1
                        sig = next((s for s in st["signals"] if s["id"] == seat["sig"]), None)
                        if sig is not None:
                            bells.append(("event", sig, _fmt_event_reply(kind, seat, rec, sig)))
                except Exception as exc:
                    _log(f"manage error {ck}: {exc}")
            st["reader"] = {k: v for k, v in _READER.items() if k != "thread"}
            save(st)
            if TG_CHANNEL_DESK and tg.enabled():
                for kind, sig, text in bells:
                    try:
                        if kind == "signal":
                            ok, _m, ids = tg.send_thread(text, None, silent=False)
                            if ok:
                                sig["tg_ids"] = ids; summary["bells"] += 1
                        else:
                            ok, _m, _ids = tg.send_thread(text, sig.get("tg_ids") or None, silent=True)
                            summary["bells"] += 1 if ok else 0
                    except Exception as exc:
                        _log(f"bell error: {exc}")
                if bells:
                    save(st)
    except Exception as exc:
        _log(f"tick error: {exc}")
        traceback.print_exc()
    return summary


# ───────────────────────────── readers ─────────────────────────────
def _ensure_reader() -> None:
    t = _READER.get("thread")
    if t is not None and t.is_alive():
        return
    api_id, api_hash, session = config._secret("TG_API_ID"), config._secret("TG_API_HASH"), config._secret("TG_SESSION")
    relay = config._secret("CHANNEL_RELAY_CHAT_ID")
    if api_id and api_hash and session:
        target, mode = _telethon_reader, "telethon user session"
    elif relay and tg.enabled():
        target, mode = _relay_reader, f"bot relay group {relay}"
    else:
        _READER.update(status="OFF — set TG_API_ID + TG_API_HASH + TG_SESSION (or CHANNEL_RELAY_CHAT_ID); drop-file inbox still works", mode="drop file only")
        return
    _READER.update(mode=mode, status="starting", err="")
    th = threading.Thread(target=target, daemon=True, name="channel-desk-reader")
    _READER["thread"] = th
    th.start()


def _telethon_reader() -> None:
    import asyncio
    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except Exception as exc:
        _READER.update(status=f"telethon missing: {exc}"); return
    api_id, api_hash, session = config._secret("TG_API_ID"), config._secret("TG_API_HASH"), config._secret("TG_SESSION")

    async def run():
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            _READER.update(status="session not authorized — regenerate TG_SESSION with research_meta/tg_pull.py --session"); return
        targets = {}
        async for d in client.iter_dialogs(limit=500):
            ck = channel_of_title(d.name)
            if ck:
                targets[d.id] = ck
        _READER.update(chats={str(k): v for k, v in targets.items()})
        if not targets:
            _READER.update(status="connected, but none of the watched channels is in this account's chats"); return
        _READER.update(status=f"listening to {', '.join(CHANNELS[v]['title'] for v in targets.values())}")

        @client.on(events.NewMessage(chats=list(targets)))
        async def _on(ev):
            try:
                m = ev.message
                reply_text, reply_id = "", None
                if m.reply_to:
                    reply_id = m.reply_to.reply_to_msg_id
                    try:
                        r = await m.get_reply_message()
                        reply_text = (r.message or "") if r else ""
                    except Exception:
                        pass
                _INBOX.put(dict(channel=targets.get(ev.chat_id), id=m.id, ts=m.date.timestamp(), text=m.message or "", reply_text=reply_text, reply_id=reply_id))
                _READER["last_at"] = time.time()
            except Exception as exc:
                _READER["err"] = str(exc)
        await client.run_until_disconnected()

    while True:
        try:
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            loop.run_until_complete(run())
            _READER.update(status="disconnected — reconnecting")
        except Exception as exc:
            _READER.update(status="reader error — retrying", err=str(exc)[:200])
        time.sleep(30)


def _relay_reader() -> None:
    import requests
    token = config.TELEGRAM_BOT_TOKEN
    relay = str(config._secret("CHANNEL_RELAY_CHAT_ID")).strip()
    offset = None
    _READER.update(status=f"polling the bot for posts forwarded into {relay}")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                             params={"timeout": 25, "offset": offset, "allowed_updates": json.dumps(["message", "channel_post"])}, timeout=35)
            for u in (r.json() or {}).get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or u.get("channel_post") or {}
                chat = m.get("chat") or {}
                title = ""
                if str(chat.get("id")) == relay:
                    fo = m.get("forward_origin") or {}
                    title = ((fo.get("chat") or {}).get("title") or (m.get("forward_from_chat") or {}).get("title") or "")
                else:
                    title = chat.get("title") or ""
                ck = channel_of_title(title)
                if not ck:
                    continue
                rep = m.get("reply_to_message") or {}
                _INBOX.put(dict(channel=ck, id=m.get("forward_from_message_id") or m.get("message_id"), ts=m.get("forward_date") or m.get("date") or time.time(),
                                text=m.get("text") or m.get("caption") or "", reply_text=rep.get("text") or rep.get("caption") or "", reply_id=rep.get("message_id")))
                _READER["last_at"] = time.time()
        except Exception as exc:
            _READER.update(err=str(exc)[:200]); time.sleep(15)


# ───────────────────────────── page ─────────────────────────────
def render(st_mod) -> None:
    """The 📡 CHANNEL DESK section of the Paper Trader (st_mod = streamlit). Reads the worker's state only."""
    st = load()
    st_mod.markdown("### 📡 CHANNEL DESK — outside signal channels, measured forward")
    st_mod.caption("Each channel's posts are parsed the moment they land, run in **their own demo book** at the channel's own rule "
                   "(2% of the wallet as margin at the stated leverage · 50% off at TP1 → stop to entry · 25% at TP2 · rest TP3 / 48h) and judged on the "
                   "**15m candle path**: liquidation first, then the stop, then the targets. The 🚦 light is ⚪ until 60 forward trades have resolved — "
                   "claimed wins are counted next to what actually printed. Never touches GEN 18.")
    rd = st.get("reader") or {}
    st_mod.caption(f"reader: {rd.get('mode', '-')} · {rd.get('status', '-')}" + (f" · last post {datetime.fromtimestamp(rd['last_at'], tz=timezone.utc).strftime('%d %b %H:%M')} UTC" if rd.get("last_at") else "")
                   + (f" · ⚠️ {rd['err']}" if rd.get("err") else ""))
    cols = st_mod.columns(len(CHANNELS))
    for col, (ck, c) in zip(cols, CHANNELS.items()):
        book = st["books"][c["book"]]
        tr = truth(st, ck); light = light_for(st, ck)
        unreal = 0.0
        for seat in book["open"]:
            px = _live(seat["sym"])
            if px:
                unreal += seat["qty_left"] * (px - seat["entry"]) * seat["side"]
        with col:
            st_mod.markdown(f"**demo {c['book']} · {c['title']}**")
            st_mod.metric("equity", f"${book['equity'] + unreal:,.2f}", f"{(book['equity'] + unreal) / book['start'] * 100 - 100:+.1f}% since start")
            st_mod.markdown(f"🚦 {light['emoji']} {light['text']}")
            st_mod.caption(f"signals {tr['signals']} · resolved {tr['n']} · TP1 first {tr['tp1']} · stop {tr['stop']} · liquidated {tr['liq']} · time {tr['time']}"
                           + (f" · R at their stop {tr['r_their']:+.2f} · at the liquidation stop {tr['r_liq']:+.2f} ({tr['win_liq']:.0f}% win)" if tr["r_liq"] is not None else "")
                           + (f" · claimed wins that lost {tr['claimed_but_lost']} · losses never posted {tr['lost_unposted']}" if tr["claims"] else ""))
            if book["open"]:
                rows = []
                for seat in book["open"]:
                    px = _live(seat["sym"])
                    mv = ((px - seat["entry"]) / seat["entry"] * 100 * seat["side"]) if px else None
                    rows.append({"coin": seat["sym"], "side": "LONG" if seat["side"] == 1 else "SHORT", "entry": _fmt_px(seat["entry"]), "lev": f"{seat['lev']}x",
                                 "now": f"{mv:+.2f}%" if mv is not None else "?", "TP1": _fmt_px(seat["tps"][0]) + (" ✅" if 0 in seat["tp_hits"] else ""),
                                 "stop": (_fmt_px(seat["stop"]) + (" (entry)" if seat["be"] else "")) if seat["stop"] is not None else "liq only",
                                 "liq": _fmt_px(seat["liq"]), "age h": f"{(time.time() - seat['opened_at']) / 3600:.1f}"})
                st_mod.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st_mod.caption("no open seats")
            if book["closed"]:
                rows = [{"coin": r["sym"], "side": "LONG" if r["side"] == 1 else "SHORT", "reason": r["reason"], "move": f"{(r['exit'] - r['entry']) / r['entry'] * 100 * r['side']:+.2f}%",
                         "margin": f"{r['pnl_margin_pct']:+.0f}%", "usd": f"{r['pnl_usd']:+.2f}", "closed": datetime.fromtimestamp(r["closed_at"], tz=timezone.utc).strftime("%d %b %H:%M")}
                        for r in reversed(book["closed"][-12:])]
                st_mod.dataframe(rows, hide_index=True, use_container_width=True)
    recent = [s for s in reversed(st["signals"])][:20]
    if recent:
        rows = []
        for s in recent:
            res = s.get("result") or {}
            rows.append({"when": datetime.fromtimestamp(s["ts"], tz=timezone.utc).strftime("%d %b %H:%M"), "channel": CHANNELS[s["channel"]]["book"], "coin": s["sym"],
                         "side": "LONG" if s["side"] == 1 else "SHORT", "entry": _fmt_px(s["entry"]), "TP1 %": f"{s.get('tp1_pct', 0):.2f}", "stop %": f"{s['stop_pct']:.2f}" if s.get("stop_pct") else "—",
                         "lev": f"{s.get('lev') or '?'}x", "printed first": res.get("first", s.get("status", "")), "R liq-stop": f"{res['r_liq']:+.2f}" if res.get("r_liq") is not None else "",
                         "channel says": ", ".join(c["kind"].upper() for c in s.get("claims", [])) or "—", "light": (s.get("light") or {}).get("emoji", "")})
        st_mod.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st_mod.caption("no channel signals received yet")

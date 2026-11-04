"""CHANNEL STUDY — an external Telegram signal channel measured by our ruler (research only).

Input: a Telegram Desktop export (three dots → Export chat history → JSON, messages only) —
pass the result.json or its folder. Nothing here touches the live worker or page.

Step 1  parse every signal (coin · side · entry · targets · stop · leverage · post time) and
        every result post the channel made ("Tp1 ✅", "SL hit" …) → channel_signals.csv
Step 2  replay each signal on 15m Binance USDT-M perp candles (spot fallback):
        · MARKET  — entry at the next 15m open after the post (what a subscriber can do)
        · LIMIT   — their entry price if touched within 4h, else no trade
        stop = their SL; when the post has none, an IMPOSED stop (3×ATR15, or 5% of price)
        is used and labelled on every number.  TP = their first target.  Also the 50%-at-TP1
        ladder the channel's pinned rule describes.  Fees 0.14% round trip, in R.
        Matched random control (same coin, side, stop distance, reward multiple, ±3 days).
Step 3  our context stamp on each signal (BTC day / 4h, clock window PKT, weekend, stop
        width, reward multiple, RS vs BTC, 24h run, RSI, distance from the 24h high, our own
        desk fires on that coin+side within ±4h) and which stamps separated winners from
        losers in BOTH halves → the TAKE / SKIP bar candidates ("channel alone" vs
        "channel on TAKE only").

Run:  research_meta\\.venv\\Scripts\\python.exe -I research_meta\\channel_study.py <export> [--dry]
      --dry  parse only: prints the parsed signals and the first unparsed messages so the
             regexes can be fixed against the real format before any candle is fetched.
"""
import json
import os
import re
import sqlite3
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")
ROOT = r"F:\Trading Indicator"
RM = os.path.join(ROOT, "research_meta")
sys.path.insert(0, RM)
import harness as H  # noqa: E402

KL_DIR = os.path.join(RM, "kl_channel")        # own cache: perp 15m candles from before the first signal
LEDGER = os.path.join(ROOT, ".state_backup_1104", "worker.db")
LOGF = None
PKT = 5 * 3600


def log(s=""):
    print(s, flush=True)
    if LOGF:
        LOGF.write(s + "\n"); LOGF.flush()


# ───────────────────────── export reader ─────────────────────────
def read_export(path):
    if os.path.isdir(path):
        path = os.path.join(path, "result.json")
    j = json.load(open(path, encoding="utf-8"))
    msgs = []
    for m in j.get("messages", []):
        if m.get("type") != "message":
            continue
        t = m.get("text", "")
        if isinstance(t, list):
            t = "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in t)
        ts = int(m.get("date_unixtime") or pd.Timestamp(m["date"]).timestamp())
        msgs.append(dict(id=m["id"], ts=ts, text=t or "", reply_to=m.get("reply_to_message_id"), photo=bool(m.get("photo")),
                         fwd=m.get("forwarded_from"), reply_text=m.get("reply_text") or ""))
    return j.get("name", "?"), msgs


# ───────────────────────── signal parser ─────────────────────────
SYM_RX = [re.compile(r"#?\b([A-Z0-9]{2,12})\s*/\s*USDT\b"), re.compile(r"#?\b([A-Z0-9]{2,12})USDT(?:\.P|\s*PERP|\s*Perpetual)?\b"),
          re.compile(r"\$([A-Z0-9]{2,12})\b")]
NUM = r"([0-9]*\.?[0-9]+)"
SIDE_RX = re.compile(r"\b(LONG|BUY|SHORT|SELL)\b", re.I)
ENTRY_RX = [re.compile(r"entry(?:\s*(?:price|zone|at))?\s*[:@\-–=]*\s*" + NUM + r"(?:\s*[-–/to]+\s*" + NUM + ")?", re.I),
            re.compile(r"\b(?:LONG|SHORT|BUY|SELL)\b\s*(?:@|at)?\s*" + NUM, re.I),
            re.compile(r"(?:🟢|🔴)\s*(?:LONG|SHORT)\s*" + NUM, re.I)]
TP_RX = re.compile(r"(?:TP|T\.P\.?|Target|Take[\s-]*profit)\s*(\d{0,2})\s*[:@\-–=)]*\s*" + NUM, re.I)
CIRC_RX = re.compile(r"[\u2776-\u277f\u2780-\u2793\u2460-\u2473]\s*" + NUM + r"|(\d)\ufe0f?\u20e3\s*" + NUM)   # ➊ 0.0285 · ❶ · ① · 1️⃣
TPLIST_RX = re.compile(r"(?:targets?|take[\s-]*profits?)\s*[:\-–]\s*([0-9.,\s/\-–]+)", re.I)
SL_RX = re.compile(r"(?:SL|S\.L\.?|Stop[\s-]*loss|Stoploss|Stop)\s*[:@\-–=)]*\s*" + NUM + r"\s*(%)?", re.I)
LEV_RX = re.compile(r"(?:leverage|lev)\s*[:\-–=]*\s*(?:cross|isolated)?\s*x?\s*(\d{1,3})\s*x?|\b(\d{1,3})\s*x\b", re.I)
CLAIM_RX = re.compile(r"(TP\s*\d|Tp\s*\d|target\s*\d|all\s*(?:targets?|tp)\s*(?:hit|done)|✅|SL\s*hit|stop\s*(?:loss\s*)?hit|stopped|❌|🛑|liquidat)", re.I)


def parse_signal(text):
    t = text.replace("\u200b", "")
    sym = None
    for rx in SYM_RX:
        m = rx.search(t)
        if m and m.group(1) not in ("USDT", "TP", "SL", "TARGET"):
            sym = m.group(1); break
    ms = SIDE_RX.search(t)
    side = 1 if (ms and ms.group(1).upper() in ("LONG", "BUY")) else -1 if ms else (1 if "🟢" in t else -1 if "🔴" in t else 0)
    if not sym or side == 0:
        return None
    entry = entry_hi = None
    for rx in ENTRY_RX:
        m = rx.search(t)
        if m:
            entry = float(m.group(1)); entry_hi = float(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else None
            break
    tps = []
    for m in CIRC_RX.finditer(t):
        tps.append(float(m.group(1) or m.group(3)))
    if not tps:
        for m in TP_RX.finditer(t):
            tps.append(float(m.group(2)))
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
    if entry is None and not tps:
        return None
    return dict(sym=sym, side=side, entry=entry, entry_hi=entry_hi, tps=tps, sl=sl, sl_pct=sl_pct, lev=lev)


def parse_all(msgs):
    sigs, claims, unparsed = [], [], []
    for m in msgs:
        s = parse_signal(m["text"])
        if s:
            s.update(id=m["id"], ts=m["ts"], text=m["text"][:400]); sigs.append(s); continue
        if CLAIM_RX.search(m["text"]) and (m["reply_to"] or m.get("reply_text") or len(m["text"]) < 80):
            q = parse_signal(m.get("reply_text") or "")
            claims.append(dict(id=m["id"], ts=m["ts"], reply_to=m["reply_to"], text=m["text"][:120], q_sym=q["sym"] if q else None,
                               q_side=q["side"] if q else None, q_entry=q["entry"] if q else None, q_tps=q["tps"] if q else None, q_sl=q["sl"] if q else None,
                               kind="tp" if re.search(r"TP|target|✅", m["text"], re.I) and not re.search(r"SL|stop|❌|🛑", m["text"], re.I) else
                               "sl" if re.search(r"SL|stop|❌|🛑|liquidat", m["text"], re.I) else "other"))
        elif len(m["text"].strip()) > 25:
            unparsed.append(m)
    return sigs, claims, unparsed


# ───────────────────────── candles (own cache) ─────────────────────────
def fetch_klines(sym, start_ms, perp=True):
    import requests
    url = "https://fapi.binance.com/fapi/v1/klines" if perp else "https://api.binance.com/api/v3/klines"
    rows, t, now = [], start_ms, int(time.time() * 1000)
    while t < now:
        data = None
        for attempt in range(4):
            try:
                r = requests.get(url, params={"symbol": sym, "interval": "15m", "startTime": t, "limit": 1500}, timeout=20)
                if r.status_code in (418, 429):
                    time.sleep(30 * (attempt + 1)); continue
                if r.status_code == 400:
                    return None
                r.raise_for_status(); data = r.json(); break
            except Exception:
                time.sleep(3 * (attempt + 1))
        if not data:
            break
        rows.extend(data); t = int(data[-1][0]) + 900_000; time.sleep(0.12)
        if len(data) < 1500:
            break
    if not rows:
        return None
    f = pd.DataFrame(rows, columns=["ot", "o", "h", "l", "c", "v", "ct", "qv", "n", "tb", "tbq", "x"])
    return f[["ot", "o", "h", "l", "c", "v", "tb", "qv", "n"]].drop_duplicates("ot")


_CANDLES = {}


def candles(sym, start_ms):
    """15m frame covering start_ms → now from research_meta/kl_channel (perp first, spot fallback)."""
    if sym in _CANDLES:
        return _CANDLES[sym]
    os.makedirs(KL_DIR, exist_ok=True)
    p = os.path.join(KL_DIR, sym + "USDT.csv")
    ok = False
    if os.path.exists(p):
        head = pd.read_csv(p, nrows=1)
        ok = len(head) and int(head.ot.iat[0]) <= start_ms + 86_400_000
    if not ok:
        f = fetch_klines(sym + "USDT", start_ms, perp=True)
        src = "perp"
        if f is None or len(f) < 50:
            f = fetch_klines(sym + "USDT", start_ms, perp=False); src = "spot"
        if f is None or len(f) < 50:
            _CANDLES[sym] = None; return None
        f["src"] = src
        f.to_csv(p, index=False)
    d = H.load(sym + "USDT", KL_DIR)
    d["src"] = pd.read_csv(p, usecols=["src"]).src.iat[0] if "src" in pd.read_csv(p, nrows=1).columns else "perp"
    d["rsi"] = rsi(d.c, 14)
    _CANDLES[sym] = d
    return d


def rsi(s, n=14):
    diff = s.diff(); up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


# ───────────────────────── replay ─────────────────────────
def resolve(d, j, e, side, stop, tp1, max_hold=192, from_touch=False):
    """Position of entry price e opened on bar j (inclusive). Same-bar stop+TP = stop.
    Returns (net_R, hold_bars, hit)."""
    risk = abs(e - stop)
    if risk <= 0 or (side == 1 and not (stop < e < tp1)) or (side == -1 and not (stop > e > tp1)):
        return None
    hi = d.h.to_numpy()[j:j + max_hold]; lo = d.l.to_numpy()[j:j + max_hold]; cl = d.c.to_numpy()[j:j + max_hold]
    sl_hit = (lo <= stop) if side == 1 else (hi >= stop)
    tp_hit = (hi >= tp1) if side == 1 else (lo <= tp1)
    k_sl = int(np.argmax(sl_hit)) if sl_hit.any() else 10 ** 9
    k_tp = int(np.argmax(tp_hit)) if tp_hit.any() else 10 ** 9
    fee_r = H.FEE_RT * e / risk
    if k_sl <= k_tp and k_sl < 10 ** 9:
        return (-1.0 - fee_r, k_sl + 1, "sl")
    if k_tp < 10 ** 9:
        return (abs(tp1 - e) / risk - fee_r, k_tp + 1, "tp")
    if len(cl) < max_hold:
        return None
    return ((cl[-1] - e) * side / risk - fee_r, max_hold, "time")


def ladder(d, j, e, side, stop, tps, max_hold=192):
    """The channel's pinned rule: 50% off at TP1, stop to entry, rest to TP2 (or time)."""
    if not tps:
        return None
    o = resolve(d, j, e, side, stop, tps[0], max_hold)
    if o is None:
        return None
    r1, k1, hit = o
    risk = abs(e - stop); fee_r = H.FEE_RT * e / risk
    if hit != "tp":
        return o
    half = 0.5 * (abs(tps[0] - e) / risk)
    j2 = j + k1 - 1
    tp2 = tps[1] if len(tps) > 1 else None
    if tp2 is None or j2 + 1 >= len(d):
        return (half - fee_r, k1, "tp")
    o2 = resolve(d, j2 + 1, e, side, e, tp2, max_hold - k1)      # stop at entry after TP1 (BE)
    if o2 is None:
        return (half - fee_r, k1, "tp")
    r2, k2, hit2 = o2
    r2_net = 0.5 * (abs(tp2 - e) / risk) if hit2 == "tp" else 0.0 if hit2 == "sl" else 0.5 * r2
    return (half + r2_net - fee_r, k1 + k2, "tp2" if hit2 == "tp" else "tp")


def replay_one(s, d, btc24):
    """One signal → rows for every plan variant + the context stamp."""
    ot = d.ot.to_numpy()
    i = int(np.searchsorted(ot, s["ts"] * 1000, side="right") - 1)        # bar containing the post
    if i < 60 or i + 2 >= len(d):
        return None
    side = s["side"]; nxt = float(d.o.iat[i + 1]); atr = float(d.atr.iat[i]) if d.atr.iat[i] == d.atr.iat[i] else None
    their_e = s["entry"] if s["entry"] else nxt
    if s.get("entry_hi"):
        their_e = (s["entry"] + s["entry_hi"]) / 2
    tps = [x for x in s["tps"] if (x > their_e if side == 1 else x < their_e)]
    out = dict(sym=s["sym"], side=side, ts=s["ts"], id=s["id"], post_px=nxt, their_entry=s["entry"], lev=s["lev"], n_tps=len(tps), src=d.src.iat[0])
    # stop: theirs, else imposed
    stops = {}
    if s["sl"]:
        stops["their SL"] = s["sl"]
    elif s["sl_pct"]:
        stops["their SL%"] = their_e * (1 - side * s["sl_pct"] / 100)
    if atr:
        stops["IMPOSED 3×ATR"] = their_e - side * 3 * atr
    stops["IMPOSED 5%"] = their_e * (1 - side * 0.05)
    out["has_sl"] = bool(s["sl"] or s["sl_pct"])
    out["fill_gap_pct"] = (nxt - their_e) / their_e * 100 * side        # + = market already past their entry (worse fill)
    if not tps:
        out["note"] = "no usable target"; return out
    tp1 = tps[0]
    out["tp1_pct"] = abs(tp1 - their_e) / their_e * 100
    for sname, stop in stops.items():
        risk = abs(their_e - stop)
        if risk <= 0:
            continue
        key = sname.replace(" ", "_").replace("×", "x").replace("%", "pct")
        out[f"stop_pct__{key}"] = risk / their_e * 100
        out[f"rr__{key}"] = abs(tp1 - their_e) / risk
        # MARKET: next open, their TP1 / this stop re-anchored on the fill
        e = nxt; st = e - side * risk; tp_m = e + (tp1 - their_e)     # their geometry re-anchored on the fill
        o = resolve(d, i + 1, e, side, st, tp_m)
        if o:
            out[f"mkt_r__{key}"], out[f"mkt_hold__{key}"], out[f"mkt_hit__{key}"] = o
            out[f"ctrl__{key}"] = H.matched_control(d, i, side, risk, abs(tp_m - e) / risk, n=3)
        # LIMIT at their entry within 4h
        if s["entry"]:
            touched = None
            if abs(nxt - their_e) / their_e <= 0.003:
                touched = i + 1
            else:
                for j in range(i + 1, min(i + 17, len(d))):
                    if (side == 1 and d.l.iat[j] <= their_e) or (side == -1 and d.h.iat[j] >= their_e):
                        touched = j; break
            out[f"lim_touched__{key}"] = touched is not None
            if touched is not None:
                o = resolve(d, touched, their_e, side, stop, tp1)
                if o:
                    out[f"lim_r__{key}"], out[f"lim_hold__{key}"], out[f"lim_hit__{key}"] = o
                ol = ladder(d, touched, their_e, side, stop, tps)
                if ol:
                    out[f"lad_r__{key}"], _, out[f"lad_hit__{key}"] = ol
        ol = ladder(d, i + 1, nxt, side, nxt - side * risk, [tp + (nxt - their_e) for tp in tps])
        if ol:
            out[f"mktlad_r__{key}"] = ol[0]
    # context stamp at the post bar
    c = d.c.to_numpy(); h = d.h.to_numpy(); l = d.l.to_numpy()
    out["btc24"] = float(btc24.get(int(ot[i]), np.nan)) if btc24 is not None else np.nan
    pkt_h = ((s["ts"] + PKT) % 86400) / 3600
    out["pkt_h"] = pkt_h; out["win"] = "01-05" if 1 <= pkt_h < 5 else "05-09" if pkt_h < 9 else "09-13" if pkt_h < 13 else "13-17" if pkt_h < 17 else "17-21" if pkt_h < 21 else "21-01"
    out["weekend"] = int(pd.Timestamp(s["ts"], unit="s", tz="UTC").tz_convert("Asia/Karachi").dayofweek >= 5)
    out["run24"] = (c[i] / c[i - 96] - 1) * 100 if i >= 96 else np.nan
    out["rs24"] = out["run24"] - out["btc24"] if out["btc24"] == out["btc24"] else np.nan
    out["rsi15"] = float(d.rsi.iat[i]) if d.rsi.iat[i] == d.rsi.iat[i] else np.nan
    out["dist_hi24_atr"] = (h[i - 96:i + 1].max() - c[i]) / atr if atr else np.nan
    out["dist_lo24_atr"] = (c[i] - l[i - 96:i + 1].min()) / atr if atr else np.nan
    out["atr_pct"] = atr / c[i] * 100 if atr else np.nan
    out["month"] = pd.Timestamp(s["ts"], unit="s", tz="UTC").strftime("%Y-%m")
    return out


def our_fires(sym, side, ts, con):
    """Our desk fires on the same coin and side within ±4h of the post (from the ledger backup)."""
    if con is None:
        return "", 0
    sd = "LONG" if side == 1 else "SHORT"
    rows = con.execute("select tier from shadow_trades where symbol=? and side=? and opened_at between ? and ?",
                       (sym + "USDT", sd, ts - 4 * 3600, ts + 4 * 3600)).fetchall()
    tiers = sorted({r[0] for r in rows})
    return "|".join(tiers), len(tiers)


# ───────────────────────── scoring ─────────────────────────
def rec(x):
    x = pd.Series(x).dropna().astype(float)
    return (float((x > 0).mean() * 100), float(x.mean()), len(x)) if len(x) else (np.nan, np.nan, 0)


def fmt(x):
    w, r, n = rec(x)
    return f"{w:3.0f}% / {r:+.2f}R (n={n})" if n else "—"


def band_scan(R, col, label, feats):
    """Which stamps separate winners from losers, both halves."""
    R = R.dropna(subset=[col]).sort_values("ts").reset_index(drop=True)
    R["half"] = (R.index >= len(R) // 2).astype(int)
    base = R[col].mean()
    log(f"\n── stamps vs {label} (baseline {fmt(R[col])}) ──")
    found = []
    for f in feats:
        x = R[f]
        if x.notna().sum() < 30 or x.nunique() < 2:
            continue
        if x.nunique() <= 6:
            bands = x.astype(str); labs = None
        else:
            try:
                bands, edges = pd.qcut(x, 3, labels=False, retbins=True, duplicates="drop")
            except Exception:
                continue
            labs = [f"{edges[k]:.3g}..{edges[k + 1]:.3g}" for k in range(len(edges) - 1)]
        cells = []
        for b, g in R.groupby(bands):
            if len(g) < 10:
                continue
            w, r, n = rec(g[col]); h1 = rec(g[g.half == 0][col])[1]; h2 = rec(g[g.half == 1][col])[1]
            cells.append((labs[int(b)] if labs else str(b), w, r, n, h1, h2))
        if len(cells) < 2:
            continue
        best = max(cells, key=lambda z: z[2]); worst = min(cells, key=lambda z: z[2])
        stable = best[4] > worst[4] and best[5] > worst[5] and best[4] == best[4] and worst[5] == worst[5]
        log(f"  {'★' if stable else ' '} {f:14s} best {best[0]:>14s} {best[1]:3.0f}% / {best[2]:+.2f}R (n={best[3]}, halves {best[4]:+.2f}/{best[5]:+.2f}) · "
            f"worst {worst[0]:>14s} {worst[1]:3.0f}% / {worst[2]:+.2f}R (n={worst[3]}) · spread {best[2] - worst[2]:+.2f}R")
        if stable:
            found.append((f, best, worst, best[2] - worst[2]))
    return found


def main():
    global LOGF
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if not args:
        print(__doc__); return
    name, msgs = read_export(args[0])
    LOGF = open(os.path.join(RM, "channel_study_log.txt"), "w", encoding="utf-8")
    sigs, claims, unparsed = parse_all(msgs)
    t0 = pd.Timestamp(min(m["ts"] for m in msgs), unit="s", tz="UTC") if msgs else None
    t1 = pd.Timestamp(max(m["ts"] for m in msgs), unit="s", tz="UTC") if msgs else None
    log(f"CHANNEL STUDY · {name} · {len(msgs)} messages {t0:%d %b %Y} → {t1:%d %b %Y} · parsed {len(sigs)} signals · {len(claims)} result posts · {len(unparsed)} unparsed")
    S = pd.DataFrame(sigs)
    if len(S):
        S["date"] = pd.to_datetime(S.ts, unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M")
        S.to_csv(os.path.join(RM, "channel_signals.csv"), index=False)
        log(f"  longs {int((S.side == 1).sum())} · shorts {int((S.side == -1).sum())} · with entry {int(S.entry.notna().sum())} · with SL {int((S.sl.notna() | S.sl_pct.notna()).sum())} · "
            f"with ≥1 target {int((S.tps.str.len() > 0).sum())} · leverage stated {int(S.lev.notna().sum())} · coins {S.sym.nunique()}")
        log("\n  first parsed signals:")
        for s in sigs[:6]:
            log(f"    {pd.Timestamp(s['ts'], unit='s', tz='UTC'):%d %b %H:%M} {s['sym']:6s} {'LONG' if s['side'] == 1 else 'SHORT'} entry {s['entry']} tps {s['tps'][:4]} sl {s['sl'] or s['sl_pct']} lev {s['lev']}")
    # the channel's own claims
    if claims:
        C = pd.DataFrame(claims)
        log(f"\n  channel's own result posts: {int((C.kind == 'tp').sum())} target/✅ posts · {int((C.kind == 'sl').sum())} stop posts · {int((C.kind == 'other').sum())} other")
        if "q_sym" in C.columns and C.q_sym.notna().any():
            have = {(x["sym"], x["side"], x["entry"]) for x in sigs}
            gone = C[C.q_sym.notna()].apply(lambda r: (r.q_sym, r.q_side, r.q_entry) not in have, axis=1)
            G = C[C.q_sym.notna() & gone].drop_duplicates(["q_sym", "q_side", "q_entry"])
            log(f"  result posts quoting a signal: {int(C.q_sym.notna().sum())} · quoted signals NOT in the history any more (deleted or older than the window): {len(G)}")
            for r in G.itertuples():
                log(f"    · {r.q_sym} {'LONG' if r.q_side == 1 else 'SHORT'} entry {r.q_entry} sl {r.q_sl} → claimed '{r.text.strip()[:30]}' at {pd.Timestamp(r.ts, unit='s', tz='UTC').tz_convert('Asia/Karachi'):%d %b %H:%M} PKT")
            C.to_csv(os.path.join(RM, "channel_claims.csv"), index=False)
    if unparsed:
        log("\n  first unparsed messages (fix the regexes if these are signals):")
        for m in unparsed[:8]:
            log("    · " + m["text"][:160].replace("\n", " ⏎ "))
    if dry or not len(S):
        log("\n--dry: stopping before candles."); return

    # ── candles + replay ──
    start_ms = int((S.ts.min() - 3 * 86400) * 1000)
    con = None
    if os.path.exists(LEDGER):
        con = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    btc = candles("BTC", start_ms)
    btc24 = None
    if btc is not None:
        b = btc.copy(); b["btc24"] = (b.c / b.c.shift(96) - 1) * 100; btc24 = b.set_index("ot")["btc24"].to_dict()
    rows, missing = [], []
    for k, s in enumerate(sigs):
        d = candles(s["sym"], start_ms)
        if d is None:
            missing.append(s["sym"]); continue
        r = replay_one(s, d, btc24)
        if r is None:
            continue
        r["our_tiers"], r["our_n"] = our_fires(s["sym"], s["side"], s["ts"], con)
        rows.append(r)
        if (k + 1) % 25 == 0:
            log(f"  … {k + 1}/{len(sigs)} replayed")
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(RM, "channel_replay.csv"), index=False)
    log(f"\nreplayed {len(R)} of {len(sigs)} signals · no candles for {len(set(missing))} coins: {', '.join(sorted(set(missing))[:12])}")
    if not len(R):
        return
    if "note" in R.columns:
        log(f"  no usable target: {int(R.note.notna().sum())}")
    R = R[R.get("note", pd.Series(index=R.index, dtype=object)).isna()] if "note" in R.columns else R

    # ── the ledger table ──
    log("\n══════ THE CHANNEL BY OUR RULER — win % / mean R per trade after fees (R = 1 stop) ══════")
    keys = [c.split("__", 1)[1] for c in R.columns if c.startswith("mkt_r__")]
    for key in keys:
        lab = key.replace("_", " ")
        log(f"\n  stop = {lab}  (their TP1 as the target)")
        log(f"    MARKET next 15m open ........ {fmt(R[f'mkt_r__{key}'])}  · random control {fmt(R[f'ctrl__{key}'])}  · TP1 printed first {float((R[f'mkt_hit__{key}'] == 'tp').mean() * 100):.0f}%")
        if f"lim_r__{key}" in R.columns:
            t = R[f"lim_touched__{key}"].fillna(False)
            log(f"    LIMIT at their entry (≤4h) .. {fmt(R[f'lim_r__{key}'])}  · touched {float(t.mean() * 100):.0f}% of posts  · not touched = no trade")
            if f"lad_r__{key}" in R.columns:
                log(f"    LADDER 50% at TP1, BE, TP2 .. {fmt(R[f'lad_r__{key}'])}")
        if f"mktlad_r__{key}" in R.columns:
            log(f"    MARKET + ladder ............. {fmt(R[f'mktlad_r__{key}'])}")
        log(f"    stop width median {R[f'stop_pct__{key}'].median():.2f}% · reward multiple median {R[f'rr__{key}'].median():.2f}")
    main_key = keys[0]
    col = f"mkt_r__{main_key}"
    log(f"\n  main read = MARKET entry, stop '{main_key.replace('_', ' ')}' → by month / side (R = 1 stop):")
    for m, g in R.groupby("month"):
        log(f"    {m}  {fmt(g[col])}   longs {fmt(g[g.side == 1][col])}   shorts {fmt(g[g.side == -1][col])}")
    log(f"  fill gap (next open vs their entry, + = worse): median {R.fill_gap_pct.median():+.2f}% · beyond ±0.5% in {float((R.fill_gap_pct.abs() > 0.5).mean() * 100):.0f}% of posts")
    log(f"  their leverage, median {R.lev.median() if R.lev.notna().any() else float('nan'):.0f}x · TP1 distance median {R.tp1_pct.median():.2f}% of price")
    if "has_sl" in R.columns:
        log(f"  posts with their own stop: {int(R.has_sl.sum())} of {len(R)} — rows without one use the IMPOSED stop shown above")

    # ── the context stamp ──
    feats = ["btc24", "win", "weekend", "fill_gap_pct", "run24", "rs24", "rsi15", "dist_hi24_atr", "dist_lo24_atr", "atr_pct", "tp1_pct", f"stop_pct__{main_key}", f"rr__{main_key}", "our_n", "side"]
    found = band_scan(R, col, "MARKET R", [f for f in feats if f in R.columns])
    log("\n══════ TAKE / SKIP bar candidates — stamps that sorted winners from losers in BOTH halves ══════")
    if not found:
        log("  none held in both halves → no bar yet (channel alone is the read)")
    for f, best, worst, spread in sorted(found, key=lambda z: -z[3]):
        log(f"  {f:14s} TAKE when {best[0]:>14s} → {best[1]:3.0f}% / {best[2]:+.2f}R (n={best[3]}) · SKIP when {worst[0]:>14s} → {worst[1]:3.0f}% / {worst[2]:+.2f}R (n={worst[3]})")
    log("\ndone · research_meta/channel_study_log.txt · channel_signals.csv · channel_replay.csv")


if __name__ == "__main__":
    main()

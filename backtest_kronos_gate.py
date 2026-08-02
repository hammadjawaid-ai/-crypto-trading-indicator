"""🔮 KRONOS GATE VALIDATION — the compass over OUR system's entries.

User 2026-07-28: "kronos is a compass that can feed and build on our
system... backtest it now, validate with our system with everything we
have on paper trading."

Apples-to-apples with the proven harness (backtest_tf30 1h arm): SAME
scoring engine (es.score_from_data), SAME tier cells (MAX/HIGH/STRONG),
SAME validated confirm (pullback + confirmation candle + vol>1.2x),
SAME structural plan (swing-10 +/- 0.25xATR, TP1 1:1), SAME Bybit taker
fees. The ONLY addition: at each confirmed entry, Kronos forecasts the
next 24h from the 400 closed candles, and we record agree/disagree/flat
vs our side. If the agree subset beats baseline and the disagree subset
underperforms, the compass gate is proven ON OUR OWN TRADES.

Checkpointed to .krgate_rows.jsonl (KRG_MAX_NEW coins per run — rerun
to resume). Research-only: deploys nothing, alerts nothing.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import binance_client
import experimental_signals as es
import kronos_forecast as kf

N_COINS = int(os.environ.get("KRG_N", "25"))
MAX_NEW = int(os.environ.get("KRG_MAX_NEW", "2"))
FEE = 0.00055
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ROWS_FILE = ".krgate_rows.jsonl"
CFG = dict(bars=800, warmup=420, step=4, alive=48, fwd=24,
           swin=10, awin=14)          # warmup>=420 so Kronos gets 400
KR_HORIZON = 24


def _outcome(side, entry, stop, tp1, hi, lo, a, b, n):
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    rr = abs(tp1 - entry) / risk
    fee_r = 2 * FEE * entry / risk
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return ("LOSS", -1.0 - fee_r)
            if hi[fb] >= tp1:
                return ("WIN", rr - fee_r)
        else:
            if hi[fb] >= stop:
                return ("LOSS", -1.0 - fee_r)
            if lo[fb] <= tp1:
                return ("WIN", rr - fee_r)
    return ("NONE", 0.0)


def _walk(sym, df, d4):
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    qv = df["quote_volume"].to_numpy()
    ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    ts_all = pd.Series(pd.to_datetime(df.index))
    n = len(df)
    rows = []
    end = n - CFG["alive"] - CFG["fwd"] - 4
    for t in range(CFG["warmup"], end, CFG["step"]):
        s1 = df.iloc[:t + 1]
        ts = s1.index[-1]
        try:
            s4 = d4[d4.index <= ts]
        except Exception:
            continue
        if len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0)
        side = r.get("side")
        tier = (r.get("tier") or "")
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        if tier not in ("MAX", "HIGH", "STRONG"):
            continue
        # offline plan (trade_plan is valid:False on slices) — house
        # standard construct, same as the proven harness
        _aw = CFG["awin"]; _sn = CFG["swin"]
        _hh = h[max(0, t - _aw + 1):t + 1]
        _ll = l[max(0, t - _aw + 1):t + 1]
        _tr = np.maximum(_hh - _ll, 0)
        _atr = float(np.mean(_tr[-_aw:])) if len(_tr) >= 5 else 0.0
        pe = float(c[t])
        if _atr <= 0 or pe <= 0:
            continue
        if side == "LONG":
            _sw = float(np.min(l[max(0, t - _sn + 1):t + 1]))
            ps = _sw - 0.25 * _atr
            if not (0 < pe - ps <= 4 * _atr):
                ps = pe - 1.5 * _atr
            tp1 = pe + (pe - ps)
        else:
            _sw = float(np.max(h[max(0, t - _sn + 1):t + 1]))
            ps = _sw + 0.25 * _atr
            if not (0 < ps - pe <= 4 * _atr):
                ps = pe + 1.5 * _atr
            tp1 = pe - (ps - pe)
        if pe <= 0 or ps <= 0 or tp1 <= 0:
            continue
        pulled = False
        conf_i = None
        for i in range(t + 1, min(t + 1 + CFG["alive"], n)):
            if side == "LONG" and l[i] <= ps:
                break
            if side == "SHORT" and h[i] >= ps:
                break
            if side == "LONG":
                if l[i] <= pe:
                    pulled = True
                ok = (pulled and c[i] > o[i] and c[i] > c[i - 1]
                      and c[i] > ema20[i]
                      and vma[i] > 0 and v[i] > VOL_MULT * vma[i])
            else:
                if h[i] >= pe:
                    pulled = True
                ok = (pulled and c[i] < o[i] and c[i] < c[i - 1]
                      and c[i] < ema20[i]
                      and vma[i] > 0 and v[i] > VOL_MULT * vma[i])
            if ok:
                conf_i = i
                break
        if conf_i is None:
            continue
        ent = float(c[conf_i])
        okp = (ps < ent < tp1) if side == "LONG" else (ps > ent > tp1)
        if not okp:
            continue
        out = _outcome(side, ent, ps, tp1, h, l,
                       conf_i + 1, conf_i + 1 + CFG["fwd"], n)
        if out is None or out[0] == "NONE":
            continue
        # 🔮 the ONLY new variable: Kronos verdict at the entry candle,
        # from the 400 CLOSED candles up to and including conf_i.
        kr_dir, kr_exp = "ERR", None
        try:
            a0 = conf_i - 400 + 1
            x_df = pd.DataFrame({
                "open": o[a0:conf_i + 1], "high": h[a0:conf_i + 1],
                "low": l[a0:conf_i + 1], "close": c[a0:conf_i + 1],
                "volume": v[a0:conf_i + 1], "amount": qv[a0:conf_i + 1]})
            x_ts = ts_all.iloc[a0:conf_i + 1]
            pred = kf.forecast_window(x_df, x_ts, horizon=KR_HORIZON)
            s = kf.summarize(ent, pred)
            kr_dir, kr_exp = s["direction"], s["exp_move_pct"]
        except Exception:
            pass
        verdict = ("agree" if
                   (kr_dir == "UP" and side == "LONG") or
                   (kr_dir == "DOWN" and side == "SHORT") else
                   "disagree" if kr_dir in ("UP", "DOWN") else
                   "flat" if kr_dir == "FLAT" else "err")
        rows.append({"sym": sym, "tier": tier, "side": side,
                     "o": out[0], "net": round(out[1], 4),
                     "kr": verdict, "kr_exp": kr_exp, "t": str(ts)})
    return rows


def _one(sym):
    try:
        d4 = binance_client.get_klines(sym, "4h", limit=400)
        df = binance_client.get_klines(sym, "1h", limit=CFG["bars"])
    except Exception:
        return []
    if d4 is None or len(d4) < 60 or df is None or \
            len(df) < CFG["warmup"] + CFG["alive"] + CFG["fwd"] + 10:
        return []
    return _walk(sym, df, d4)


def _load():
    rows, done = [], set()
    if not os.path.exists(ROWS_FILE):
        return rows, done
    for ln in open(ROWS_FILE, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        ob = json.loads(ln)
        if "done_coin" in ob:
            done.add(ob["done_coin"])
        else:
            rows.append(ob)
    return rows, done


def _append(sym, rs):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for rec in rs:
            f.write(json.dumps(rec) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def _seg(df, name):
    if not len(df):
        return
    w = (df.o == "WIN").mean() * 100
    print(f"  {name:<26} n={len(df):5} win {w:5.1f}% "
          f"exp {df.net.mean():+.3f}R net {df.net.sum():+.1f}R")


def _report(rows, done_n):
    print("\n" + "=" * 72)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"🔮 KRONOS GATE ON OUR ENTRIES [{tag}] — {len(rows)} "
          f"confirmed entries · fees in")
    print("=" * 72)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    _seg(df, "BASELINE (all our entries)")
    for k in ("agree", "disagree", "flat", "err"):
        _seg(df[df.kr == k], f"kronos {k.upper()}")
    ag = df[df.kr == "agree"]
    if len(ag):
        strong = ag[ag.kr_exp.abs() >= 1.5]
        _seg(strong, "AGREE + |exp|>=1.5%")
    print("  --- by side ---")
    for sd in ("LONG", "SHORT"):
        s = df[df.side == sd]
        _seg(s, f"{sd} baseline")
        _seg(s[s.kr == "agree"], f"{sd} agree")
        _seg(s[s.kr == "disagree"], f"{sd} disagree")
    print("  --- by tier (agree) ---")
    for tier in ("MAX", "HIGH", "STRONG"):
        _seg(df[(df.tier == tier) & (df.kr == "agree")],
             f"{tier} agree")
        _seg(df[(df.tier == tier) & (df.kr == "disagree")],
             f"{tier} disagree")
    print("=" * 72)


if __name__ == "__main__":
    if not kf.available():
        print("KRONOS UNAVAILABLE:", kf._import_err, flush=True)
        sys.exit(1)
    kf._get_predictor()          # load once up front
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} entries). Run: {todo}",
          flush=True)
    t0 = time.time()
    for s in todo:
        try:
            rs = _one(s)
        except Exception as exc:
            print(f"  {s}: ERROR {exc}", flush=True)
            rs = []
        _append(s, rs)
        rows.extend(rs)
        print(f"  done {s:12} +{len(rs):4} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)

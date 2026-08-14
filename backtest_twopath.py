"""TWO-PATH ENTRY VALIDATION — the ACE fix, measured before it ships.

User 2026-08-14: FRESH / TAKE NOW HOT / APEX fired ACE 12-14h late at
+20% because their ONLY entry path waits for a pullback + confirmation
candle — a runner never pulls back, so the boards structurally cannot
fire early on the strongest moves, then fire late into exhaustion.

This measures, on the same historical population as the master deep
validation (score>=80 fires, MAX/HIGH/STRONG), per FIRE (not per
confirmation — the old per-conf sampling silently dropped every runner
that never confirmed, which is exactly the ACE case):

  PATH A (deployed): pullback to plan entry + confirmation candle
          (close beyond EMA20, momentum, volume>1.2x) -> enter at conf
          close, plan TP1, structural stop.
  PATH B (candidate): the coin REFUSES to pull back and instead breaks
          the 24-bar high (low for SHORT) on a conviction candle with
          expanding volume (>1.5x) while still on the right side of
          the EMA20 -> enter at break close, geometry RE-ANCHORED to
          the break price (same relative TP/stop as the plan, then the
          structural stop on top). The break construct is the only one
          that measured positive across six pre-burst tests (+0.10R).
  GUARD (candidate): at entry time, how far has price already RUN from
          the fire price ("paid-up %")? Buckets decide whether late
          entries (the +20% ACE fire) should be blocked.

Outputs per board (TAKE NOW HOT / FRESH+HOT / APEX proxy): A-only vs
two-path (first of A/B), the B-only recovered fires, runner coverage
(no-pullback fires with mfe>=5% — the ACE population), and the paid-up
bucket table that sets the guard threshold. Splits older/recent.

Measurement only — nothing deploys unless it wins after fees.
Chunked + checkpointed like the master run.
Env: TP_N (coins, 30), TP_MAX_NEW (10), TP_BARS (3000), TP_K (4).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es
import velocity_burst as vb
import smart_stop
import deep_history as dh

N_COINS = int(os.environ.get("TP_N", "30"))
MAX_NEW = int(os.environ.get("TP_MAX_NEW", "10"))
BARS = int(os.environ.get("TP_BARS", "3000"))
K = int(os.environ.get("TP_K", "4"))
WARMUP = 220
ALIVE = 48          # bars after the fire in which either path may trigger
FWD = 24            # outcome horizon after entry (same as master run)
SCORE_FLOOR = 80.0
VOL_MULT = 1.2      # path A confirmation volume (deployed)
BRK_LOOK = 24       # path B: recent-high window at the fire
BRK_VOL = 1.5       # path B: expanding-volume multiple
HOT_PCTILE = 60.0
FRESH_GAP_H = 72
ROW_GAP = 12        # min bars between sampled fires per side (dedup)
ROWS_FILE = f".twopath_rows_{BARS}.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _pr(arr, val):
    if len(arr) == 0:
        return 0.0
    return float((arr < val).mean() * 100.0)


def _tp_before_stop(side, entry, stop, tp1, hi, lo, a, b, n):
    risk = abs(entry - stop)
    if risk <= 0:
        return ("NONE", 0.0)
    rr = abs(tp1 - entry) / risk
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return ("LOSS", rr)
            if hi[fb] >= tp1:
                return ("WIN", rr)
        else:
            if hi[fb] >= stop:
                return ("LOSS", rr)
            if lo[fb] <= tp1:
                return ("WIN", rr)
    return ("NONE", rr)


def _one(sym):
    try:
        d1 = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS))
        d4 = indicators.enrich(dh.get_klines_deep(sym, "4h",
                                                  BARS // 4 + 60))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + ALIVE + FWD + 5:
        return []
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    atr = _atr(h, l, c, 14)
    roc6 = np.abs(c / np.roll(c, 6) - 1.0); roc6[:6] = 0.0
    e4_20 = d4["close"].ewm(span=20, adjust=False).mean()
    n = len(d1); half = n // 2; rows = []
    last_fire: dict = {}   # fresh bookkeeping (matches worker's 72h idea)
    last_row: dict = {}    # sampling dedup — one row per move episode

    def _edge_pack(i, side, ts, fresh):
        hot = _pr(atr[max(0, i-100):i], atr[i]) >= HOT_PCTILE
        rocb = _pr(roc6[max(0, i-100):i], roc6[i]) >= HOT_PCTILE
        vbe = False
        try:
            bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:i+1])
            vbe = bs >= 78 and (bside or "").upper() == side
        except Exception:
            pass
        mtf = False
        try:
            e4v = float(e4_20[e4_20.index <= ts].iloc[-1])
            s4c = d4[d4.index <= ts]
            c4v = float(s4c["close"].iloc[-1])
            mtf = ((side == "LONG" and c4v > e4v)
                   or (side == "SHORT" and c4v < e4v))
        except Exception:
            pass
        return hot, int(hot) + int(rocb) + int(vbe) + int(mtf) + int(fresh)

    for t in range(WARMUP, n - ALIVE - FWD - 1, K):
        s1 = d1.iloc[:t+1]; ts = s1.index[-1]
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
        sc = float(r.get("score") or 0); side = r.get("side")
        tier = (r.get("tier") or "")
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        if tier not in ("MAX", "HIGH", "STRONG"):
            continue
        prev = last_fire.get(side)
        last_fire[side] = t
        fresh = prev is None or (t - prev) > FRESH_GAP_H
        prow = last_row.get(side)
        if prow is not None and (t - prow) < ROW_GAP:
            continue                      # same move episode — sampled
        plan = r.get("trade_plan") or {}
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0)
        tp1 = float(plan.get("tp1") or 0)
        if p_entry <= 0 or p_stop <= 0 or tp1 <= 0:
            continue
        last_row[side] = t
        sig_px = float(c[t])
        lng = side == "LONG"
        ref_hi = float(np.max(h[max(0, t-BRK_LOOK):t+1]))
        ref_lo = float(np.min(l[max(0, t-BRK_LOOK):t+1]))

        pulled = False
        conf_i = None
        brk_i = None
        for i in range(t+1, min(t+1+ALIVE, n)):
            if lng:
                if l[i] <= p_entry:
                    pulled = True
                if conf_i is None and pulled and c[i] > o[i] \
                        and c[i] > c[i-1] and c[i] > ema20[i] \
                        and vma[i] > 0 and v[i] > VOL_MULT * vma[i]:
                    conf_i = i
                # break race is OPEN from the fire bar — the smoke run
                # proved a "no pullback yet" gate kills B entirely
                # (plan entries sit ~at live px, so 93% of fires
                # technically "pull back" within a bar or two)
                if brk_i is None and c[i] > ref_hi \
                        and c[i] > o[i] and c[i] > ema20[i] \
                        and vma[i] > 0 and v[i] > BRK_VOL * vma[i]:
                    brk_i = i
            else:
                if h[i] >= p_entry:
                    pulled = True
                if conf_i is None and pulled and c[i] < o[i] \
                        and c[i] < c[i-1] and c[i] < ema20[i] \
                        and vma[i] > 0 and v[i] > VOL_MULT * vma[i]:
                    conf_i = i
                if brk_i is None and c[i] < ref_lo \
                        and c[i] < o[i] and c[i] < ema20[i] \
                        and vma[i] > 0 and v[i] > BRK_VOL * vma[i]:
                    brk_i = i
            if conf_i is not None and brk_i is not None:
                break
        # mfe from the fire price over the window (runner detection)
        j0, j1 = t+1, min(t+1+ALIVE, n)
        mfe_pct = ((float(np.max(h[j0:j1])) / sig_px - 1.0) if lng
                   else (1.0 - float(np.min(l[j0:j1])) / sig_px)) * 100.0

        row = {"tier": tier, "fresh": bool(fresh),
               "half": "recent" if t >= half else "older",
               "pulled": bool(pulled), "mfe": round(mfe_pct, 2),
               "a": None, "b": None}

        if conf_i is not None:
            ci = conf_i
            ent = float(c[ci])
            hot, edges = _edge_pack(ci, side, d1.index[ci], fresh)
            s_st = smart_stop.structural_stop(d1.iloc[:ci+1], side, ent,
                                              p_stop, tp1)
            out, rr = _tp_before_stop(side, ent, s_st, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
            ext = (ent / sig_px - 1.0) * (1 if lng else -1) * 100.0
            row["a"] = {"d": ci - t, "ext": round(ext, 2),
                        "hot": bool(hot), "edges": int(edges),
                        "o": out, "rr": rr}
        if brk_i is not None:
            bi = brk_i
            ent_b = float(c[bi])
            hot_b, edges_b = _edge_pack(bi, side, d1.index[bi], fresh)
            # geometry RE-ANCHORED to the break price: same relative
            # stop/TP as the plan, structural stop on top — what the
            # live system would do if it re-planned at the break.
            stop_fb = ent_b * (p_stop / p_entry)
            tp1_b = ent_b * (tp1 / p_entry)
            s_st_b = smart_stop.structural_stop(d1.iloc[:bi+1], side,
                                                ent_b, stop_fb, tp1_b)
            out_b, rr_b = _tp_before_stop(side, ent_b, s_st_b, tp1_b,
                                          h, l, bi+1, bi+1+FWD, n)
            ext_b = (ent_b / sig_px - 1.0) * (1 if lng else -1) * 100.0
            row["b"] = {"d": bi - t, "ext": round(ext_b, 2),
                        "hot": bool(hot_b), "edges": int(edges_b),
                        "o": out_b, "rr": rr_b}
        rows.append(row)
    return rows


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
            r2 = dict(rec); r2["sym"] = sym
            f.write(json.dumps(r2) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def _stat(entries):
    """entries: list of path dicts ({'o','rr'}). Win% over decided,
    expectancy per taken trade (NONE counts 0 in the numerator)."""
    dec = [e for e in entries if e["o"] in ("WIN", "LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
        / max(1, len(entries))
    return (w/len(dec)*100 if dec else 0.0), exp, len(entries)


def _first(row):
    """The two-path system's entry for this fire: whichever triggered
    first (A on pullback days, B on runner days)."""
    a, b = row["a"], row["b"]
    if a is not None and b is not None:
        return (a, "a") if a["d"] <= b["d"] else (b, "b")
    if a is not None:
        return a, "a"
    if b is not None:
        return b, "b"
    return None, None


def _board_rows(rows, board):
    """Board membership judged at each path's OWN entry bar (hot/edges
    at entry — same definition as the master validation)."""
    def _in(pe):
        if pe is None:
            return False
        if board == "tnh":
            return pe["hot"]
        if board == "fresh":
            return pe["hot"]          # + row-level fresh checked below
        if board == "apex":
            return pe["edges"] >= 2
        return True
    out = []
    for r in rows:
        if board == "fresh" and not r["fresh"]:
            continue
        if r["tier"] not in ("MAX", "HIGH") and board != "em":
            continue
        if board == "em" and r["tier"] != "STRONG":
            continue
        out.append((r, _in))
    return out


def report(rows):
    print("=" * 104)
    n_conf = sum(1 for r in rows if r["a"] is not None)
    n_brk = sum(1 for r in rows if r["b"] is not None)
    n_both = sum(1 for r in rows if r["a"] and r["b"])
    runners = [r for r in rows if not r["pulled"] and r["mfe"] >= 5.0]
    print(f"TWO-PATH VALIDATION — {len(rows)} score-fires "
          f"({sum(1 for r in rows if r['tier'] in ('MAX','HIGH'))} "
          f"MAX/HIGH) · A confirms {n_conf} ({n_conf/max(1,len(rows))*100:.0f}%)"
          f" · B breaks {n_brk} ({n_brk/max(1,len(rows))*100:.0f}%)"
          f" · both {n_both}")
    # THE ACE SHAPES — the two failure modes the user reported:
    #   MISSED MONEY: the move ran >=5% but A never confirmed inside
    #     48h (the board simply never fired — invisible today)
    #   LATE FIRES : A confirmed but only after price already ran
    #     >=5% from the fire (the "+20% after 13h" buzz)
    missed = [r for r in rows if r["a"] is None and r["mfe"] >= 5.0]
    late = [r for r in rows if r["a"] is not None
            and r["a"]["ext"] >= 5.0]
    print(f"MISSED MONEY (mfe>=5%, A never confirmed): {len(missed)} "
          f"fires · B recovers "
          f"{sum(1 for r in missed if r['b'] is not None)}")
    mbe = [r["b"] for r in missed if r["b"] is not None]
    if mbe:
        w, e, nn = _stat(mbe)
        d = np.median([x["d"] for x in mbe])
        print(f"  B on missed money: n={nn} win {w:.1f}% exp {e:+.3f}R"
              f" · median entry {d:.0f}h after the fire")
    la = [r["a"] for r in late]
    if la:
        w, e, nn = _stat(la)
        print(f"LATE FIRES (A confirmed >=5% paid-up): n={nn} win "
              f"{w:.1f}% exp {e:+.3f}R  <- what the guard would block")
    if runners:
        rb = sum(1 for r in runners if r["b"] is not None)
        print(f"pure runners (never touched entry, mfe>=5%): "
              f"{len(runners)} · B covers {rb}")
    print("-" * 104)
    for board, label in (("tnh", "✅🔥 TAKE NOW HOT (MAX/HIGH)"),
                         ("fresh", "🌱 FRESH + HOT (MAX/HIGH)"),
                         ("apex", "🏆 APEX proxy (2+ edges, MAX/HIGH)"),
                         ("em", "⚡ EARLY MOVERS (STRONG, hot)")):
        brs = _board_rows(rows, board)
        a_только = [r["a"] for r, _in in brs
                    if r["a"] is not None and _in(r["a"])]
        two = []
        added = []
        for r, _in in brs:
            pe, which = _first(r)
            if pe is None or not _in(pe):
                continue
            two.append(pe)
            if which == "b" and (r["a"] is None or not _in(r["a"])):
                added.append(pe)
        wa, ea, na = _stat(a_только)
        wt, et, nt = _stat(two)
        wx, ex, nx = _stat(added)
        da = np.median([x["d"] for x in a_только]) if a_только else 0
        dt = np.median([x["d"] for x in two]) if two else 0
        print(f"  {label}")
        print(f"    A-only (deployed) | n={na:4} | win {wa:5.1f}% "
              f"exp {ea:+.3f}R | median entry {da:4.0f}h after fire")
        print(f"    TWO-PATH (A|B 1st)| n={nt:4} | win {wt:5.1f}% "
              f"exp {et:+.3f}R | median entry {dt:4.0f}h after fire")
        print(f"    B-added fires     | n={nx:4} | win {wx:5.1f}% "
              f"exp {ex:+.3f}R  <- trades A misses today")
    print("-" * 104)
    print("PAID-UP GUARD — A entries by how far price already ran from "
          "the fire (sets the late-fire block):")
    a_all = [(r, r["a"]) for r in rows
             if r["a"] is not None and r["tier"] in ("MAX", "HIGH")]
    for lo_, hi_, lbl in ((-99, 0, "entered at/below fire px"),
                          (0, 2, "paid up 0-2%"),
                          (2, 5, "paid up 2-5%"),
                          (5, 999, "paid up >5%  (the ACE fire)")):
        seg = [a for _, a in a_all if lo_ <= a["ext"] < hi_]
        w, e, nn = _stat(seg)
        print(f"  {lbl:28} | n={nn:4} | win {w:5.1f}% exp {e:+.3f}R")
    seg_b = [r["b"] for r in rows if r["b"] is not None]
    for lo_, hi_, lbl in ((-99, 2, "B paid up <2%"),
                          (2, 5, "B paid up 2-5%"),
                          (5, 999, "B paid up >5%")):
        seg = [b for b in seg_b if lo_ <= b["ext"] < hi_]
        w, e, nn = _stat(seg)
        print(f"  {lbl:28} | n={nn:4} | win {w:5.1f}% exp {e:+.3f}R")
    print("-" * 104)
    for hlf in ("older", "recent"):
        sub = [r for r in rows if r["half"] == hlf]
        a_ = [r["a"] for r in sub if r["a"] is not None]
        t_ = [pe for pe in (_first(r)[0] for r in sub) if pe is not None]
        wa, ea, na = _stat(a_); wt, et, nt = _stat(t_)
        print(f"  {hlf:6} | A-only n={na:4} {wa:5.1f}%/{ea:+.3f}R | "
              f"two-path n={nt:4} {wt:5.1f}%/{et:+.3f}R")
    print("=" * 104)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} fires). Run: {todo}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(4, len(todo) or 1)) as pool:
        futs = {pool.submit(_one, s): s for s in todo}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                rr = fut.result()
            except Exception as exc:
                print(f"  {s} failed: {exc}", flush=True)
                rr = []
            _append(s, rr)
            rows.extend(rr)
            print(f"  done {s:12} +{len(rr)} (cum {len(rows)}, "
                  f"{time.time()-t0:.0f}s)", flush=True)
    done2 = done | set(todo)
    tag = ("COMPLETE" if len(done2) >= N_COINS
           else f"PARTIAL {len(done2)}/{N_COINS}")
    print(f"\n[{tag}]")
    report(rows)
    if len(done2) < N_COINS:
        print(">> Re-run to add more coins.")
    print(f"Done in {time.time()-t0:.0f}s.")

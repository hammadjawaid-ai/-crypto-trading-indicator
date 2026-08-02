"""🧠 EDGE MINER — mine the Decision Desk's own record for what works.

The user's call (2026-07-28): "you have huge amount of data from decision
desk now... decide what is exactly working... which trades were the most
effective, what were their scores when they started going in our favour
and when it didn't." We can't take thousands of NEW trades to prove a
design — but we already TOOK thousands. This mines them.

Joins every CLOSED shadow trade to its originating signal snapshot
(symbol+side, nearest ts within JOIN_WINDOW) and slices after-fee R by
the conditions that existed AT FIRE: desk tier, signal grade (MAX/HIGH/
STRONG), score bucket, ATR heat, side, plus trade-path facts the desk
recorded itself (peak = max favorable excursion, exit reason, hold time).
Everything is descriptive — minimum segment size enforced so noise can't
masquerade as edge. Read-only; touches nothing that trades.
"""
from __future__ import annotations

import json
import time

import worker_store as ws

JOIN_WINDOW = 900          # seconds between signal ts and desk open
MIN_SEG = 25               # segments smaller than this are labeled thin


def _load(limit: int = 6000):
    """Closed shadow trades (full columns) + signals, joined."""
    c = ws._open()
    try:
        trades = [dict(zip([d[0] for d in cur.description], row))
                  for cur in [c.execute(
                      "SELECT tier,symbol,side,entry,stop,stop0,tp1,tp2,"
                      "peak,be_set,tp1_hit,opened_at,closed_at,exit_px,"
                      "exit_reason,pnl_r FROM shadow_trades "
                      "WHERE status='CLOSED' ORDER BY opened_at "
                      f"LIMIT {int(limit)}")]
                  for row in cur.fetchall()]
        sigs = [dict(zip([d[0] for d in cur.description], row))
                for cur in [c.execute(
                    "SELECT ts,stream,symbol,side,tier,score,conviction,"
                    "hot,atr_pct,extra FROM signals ORDER BY ts")]
                for row in cur.fetchall()]
    finally:
        c.close()
    by_key: dict = {}
    for s in sigs:
        by_key.setdefault((s["symbol"], s["side"]), []).append(s)
    joined = []
    for t in trades:
        cand = by_key.get((t["symbol"], t["side"]), [])
        best, bdt = None, JOIN_WINDOW + 1
        for s in cand:
            dt = abs(float(s["ts"]) - float(t["opened_at"]))
            if dt < bdt:
                best, bdt = s, dt
        row = dict(t)
        if best is not None:
            row["sig_grade"] = best.get("tier")        # MAX/HIGH/STRONG
            row["sig_score"] = best.get("score")
            row["sig_hot"] = best.get("hot")
            row["sig_atr_pct"] = best.get("atr_pct")
            try:
                extra = json.loads(best.get("extra") or "{}")
            except Exception:
                extra = {}
            row["sig_lanes"] = extra.get("lanes") or extra.get(
                "early_lanes")
            row["sig_conf"] = extra.get("_conf")
        # Max favorable excursion in R, from the desk's own peak tracking.
        try:
            risk = abs(float(t["entry"]) - float(t["stop0"] or t["stop"]))
            if risk > 0 and t.get("peak"):
                mfe = ((float(t["peak"]) - float(t["entry"])) if
                       t["side"] == "LONG" else
                       (float(t["entry"]) - float(t["peak"]))) / risk
                row["mfe_r"] = round(mfe, 2)
        except Exception:
            pass
        row["hold_h"] = round((float(t["closed_at"]) -
                               float(t["opened_at"])) / 3600, 1)
        joined.append(row)
    return joined


def _stat(rows):
    n = len(rows)
    if not n:
        return None
    rs = [float(r["pnl_r"] or 0) for r in rows]
    wins = sum(1 for x in rs if x > 0)
    return {"n": n, "win_pct": round(wins / n * 100, 1),
            "net_r": round(sum(rs), 2),
            "avg_r": round(sum(rs) / n, 3),
            "thin": n < MIN_SEG}


def _seg(rows, key_fn, label):
    out = []
    groups: dict = {}
    for r in rows:
        k = key_fn(r)
        if k is None:
            continue
        groups.setdefault(k, []).append(r)
    for k, g in groups.items():
        s = _stat(g)
        if s:
            s[label] = k
            out.append(s)
    out.sort(key=lambda x: -x["avg_r"])
    return out


def mine(days: float | None = None) -> dict:
    rows = _load()
    if days:
        cut = time.time() - days * 86400
        rows = [r for r in rows if float(r["closed_at"]) >= cut]
    matched = [r for r in rows if "sig_grade" in r]

    def score_bucket(r):
        s = r.get("sig_score")
        if s is None:
            return None
        s = float(s)
        return "90+" if s >= 90 else ("85-90" if s >= 85 else
                                      ("80-85" if s >= 80 else "<80"))

    def heat_bucket(r):
        a = r.get("sig_atr_pct")
        if a is None:
            return None
        a = float(a)
        return "blazing 90+" if a >= 90 else (
            "hot 70-90" if a >= 70 else "cool <70")

    def mfe_bucket(r):
        m = r.get("mfe_r")
        if m is None:
            return None
        return ("never favoured (<0.2R)" if m < 0.2 else
                "teased 0.2-0.8R" if m < 0.8 else
                "paid 0.8R+ first")

    losers = [r for r in rows if float(r["pnl_r"] or 0) <= 0
              and r.get("mfe_r") is not None]
    teased = [r for r in losers if r["mfe_r"] >= 0.5]

    report = {
        "total": _stat(rows), "matched_n": len(matched),
        "by_tier": _seg(rows, lambda r: r["tier"], "tier"),
        "by_grade": _seg(matched, lambda r: r.get("sig_grade"), "grade"),
        "by_score": _seg(matched, score_bucket, "score"),
        "by_heat": _seg(matched, heat_bucket, "heat"),
        "by_side": _seg(rows, lambda r: r["side"], "side"),
        "by_exit": _seg(rows, lambda r: r.get("exit_reason"), "exit"),
        "by_mfe": _seg(rows, mfe_bucket, "mfe"),
        "loser_tease_pct": round(len(teased) / len(losers) * 100, 1)
        if losers else None,
        # The cross-cut that parameterizes TRUE SIGNAL: tier x grade x
        # heat, best first, thin segments flagged not hidden.
        "best_cells": _seg(
            matched, lambda r: (r["tier"], str(r.get("sig_grade")),
                                heat_bucket(r) or "?"), "cell")[:12],
    }
    return report

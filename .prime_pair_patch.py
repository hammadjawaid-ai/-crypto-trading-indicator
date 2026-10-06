"""⭐🥇 STAR × PRIME and 💎🥇 ELITE × PRIME — two separate bells with their own
switches (user 2026-10-06: "built and deploy this as separate notification …
both should have their separate spots on telegram so in case it gets noisy I
will switch off"). Bands by his call: star 40-54 / 55-64 / 75-84 / 85+ (not
65-74); conviction 40-54 / 55-64 / 65-74. Pairing pass after the elite push;
desk tiers star_prime / conv_prime record EVERY band so the forward ledger can
judge the band rule. Study: .prime_x_elite.py on the 09-28 desk copy."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()

HELPERS = '''# ⭐🥇 / 💎🥇 PRIME PAIRS (user 2026-10-06: "when elite star and prime agree the
# win rate is really good … deploy this as separate notification … elite and
# prime agrees … both should have their separate spots so in case it gets noisy
# I will switch off"). Study .prime_x_elite.py on the 09-28 desk copy, overlap =
# a 🥇 PRIME signal 2h before → 30 min after the elite fire, outcome = the elite
# trade's desk result. ONE regime (September) — the forward ledgers judge it.
TG_STAR_PRIME = True   # ⭐🥇 bell. False = silent; desk tier star_prime continues.
TG_CONV_PRIME = True   # 💎🥇 bell. False = silent; desk tier conv_prime continues.
PRIME_PAIR_BEFORE, PRIME_PAIR_AFTER = 2 * 3600, 30 * 60
PRIME_PAIR_FRESH = 35 * 60       # an elite record pairs only while this fresh
STAR_PRIME_BANDS = ("40-54", "55-64", "75-84", "85+")   # user: "just not 65 to 74"
CONV_PRIME_BANDS = ("40-54", "55-64", "65-74")           # user: "40-54, 55-64, 65-74"
STAR_PRIME_REC = {
    "window": "desk 09 Sep → 28 Sep", "all": "76% / +0.48R (33)",
    "alone": "57% / +0.15R (171)", "40-54": "92% / +0.58R (12)",
    "55-64": "67% / +0.50R (6)", "65-74": "50% / +0.26R (4)",
    "75-84": "100% / +0.87R (3)", "85+": "62% / +0.26R (8)",
    "LONG": "73% / +0.44R (22)", "SHORT": "82% / +0.55R (11)"}
CONV_PRIME_REC = {
    "window": "desk 01 Sep → 28 Sep", "all": "60% / +0.28R (85)",
    "alone": "41% / +0.06R (750)", "40-54": "60% / +0.32R (35)",
    "55-64": "62% / +0.32R (21)", "65-74": "67% / +0.70R (6)",
    "75-84": "62% / +0.19R (13)", "85+": "50% / −0.06R (10)",
    "LONG": "61% / +0.22R (46)", "SHORT": "59% / +0.36R (39)"}


def _conf_band(conf):
    """'40-54' / '55-64' / '65-74' / '75-84' / '85+' — None when unreadable."""
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return None
    if not 0 <= c <= 100:
        return None
    return ("40-54" if c < 55 else "55-64" if c < 65 else "65-74" if c < 75
            else "75-84" if c < 85 else "85+")


def _fmt_prime_pair(kind, sig, px, now):
    """The pair bell: action word, the two fires, the plan, the pair record
    with its window, this band's cell, the side's cell, the forward ledger."""
    star = kind == "star"
    rec = STAR_PRIME_REC if star else CONV_PRIME_REC
    tier = "star_prime" if star else "conv_prime"
    band = _conf_band(sig.get("conf"))
    side = (sig.get("side") or "").upper()
    head = (("⭐🥇 *STAR × PRIME" if star else "💎🥇 *ELITE × PRIME")
            + f" — {sig['base']} {side} · TAKE · {rung_stats.pkt_hm(now)} PKT*")
    who = "⭐ star fire" if star else "💎 elite conviction fire"
    l2 = (f"{who} + 🥇 PRIME on the same coin and side (PRIME within 2h "
          f"before → 30 min after the fire)")
    t2 = f" · TP2 `{float(sig['tp2']):g}`" if sig.get("tp2") else ""
    cf = sig.get("conf")
    plan = (f"entry `{float(sig['entry']):g}` · live `{float(px):g}` · SL "
            f"`{float(sig['stop']):g}` · TP1 `{float(sig['tp1']):g}`{t2} · "
            f"🎯 conf {cf if cf is not None else '?'} ({band or '?'} band)")
    l4 = (f"pair record ({rec['window']}): {rec['all']} vs "
          f"{'star' if star else 'elite'} alone {rec['alone']} · this band "
          f"{rec.get(band or '', '—')} · {side.lower()}s {rec.get(side, '—')}")
    try:
        fwd = rung_stats.rec(rung_stats.tier_rec(tier, None, now))
    except Exception:
        fwd = "record unavailable"
    l5 = f"forward ledger ({tier}): {fwd} · {rung_stats.stamp_now(now)}"
    l6 = ("_one regime (September) behind the pair record — the forward ledger "
          "per band decides; bands outside your list record silently._")
    return "\\n".join([head, l2, plan, l4, l5, l6])


def cycle() -> None:
'''
W = rep(W, "def cycle() -> None:\n", HELPERS, "helpers before cycle")

BLOCK = '''    # ⭐🥇 / 💎🥇 PRIME PAIRS — pairing pass. Runs after both elite pushes
    # so this cycle's elite_star records are already in the DB. A star fire
    # takes the ⭐🥇 bell only (never both). Records + desk open for EVERY
    # band; the bell applies the user's band list and its own switch.
    try:
        import json as _json_pp
        _now_pp = time.time()
        _paired_pp = set()
        for _kind, _stream_pp, _tier_pp, _bands_pp, _on_pp in (
                ("star", "elite_star", "star_prime", STAR_PRIME_BANDS,
                 TG_STAR_PRIME),
                ("conv", "elite_conv", "conv_prime", CONV_PRIME_BANDS,
                 TG_CONV_PRIME)):
            for _sg in store.recent_by_stream(_stream_pp, 80):
                try:
                    _ts_pp = float(_sg.get("ts") or 0)
                    if _now_pp - _ts_pp > PRIME_PAIR_FRESH:
                        continue
                    _sym_pp = _sg.get("symbol")
                    _sd_pp = (_sg.get("side") or "").upper()
                    if not _sym_pp or (_sym_pp, _sd_pp) in _paired_pp:
                        continue
                    if (_kind == "conv" and store.seen_between(
                            "elite_star", _sym_pp, _sd_pp,
                            _ts_pp - 900, _ts_pp + 900)):
                        continue
                    if not store.seen_between(
                            "prime", _sym_pp, _sd_pp,
                            _ts_pp - PRIME_PAIR_BEFORE,
                            _ts_pp + PRIME_PAIR_AFTER):
                        continue
                    if not (_sg.get("entry") and _sg.get("stop")
                            and _sg.get("tp1")):
                        continue
                    if not store.should_alert(
                            f"{_tier_pp}:{_sym_pp}:{_sd_pp}", 3 * 3600):
                        continue
                    _paired_pp.add((_sym_pp, _sd_pp))
                    try:
                        _ex_pp = _json_pp.loads(_sg.get("extra") or "{}")
                    except Exception:
                        _ex_pp = {}
                    _conf_pp = _ex_pp.get("conf")
                    _band_pp = _conf_band(_conf_pp)
                    _sig_pp = {"symbol": _sym_pp,
                               "base": _sg.get("base")
                               or str(_sym_pp).replace("USDT", ""),
                               "side": _sd_pp, "entry": _sg.get("entry"),
                               "stop": _sg.get("stop"), "tp1": _sg.get("tp1"),
                               "tp2": _sg.get("tp2"), "tier": _sg.get("tier"),
                               "score": _sg.get("score"), "conf": _conf_pp,
                               "band": _band_pp, "elite_ts": _ts_pp}
                    _px_pp = None
                    try:
                        _px_pp = binance_client.get_ticker_price(_sym_pp)
                    except Exception:
                        _px_pp = None
                    store.record_signal(_tier_pp, _sig_pp)
                    shadow_trader.open_from_signal(_tier_pp, _sig_pp, _px_pp)
                    _bell_pp = ("off" if not _on_pp else
                                "band-out" if _band_pp not in _bands_pp else
                                "quiet" if _bstock_quiet(_sym_pp) else "due")
                    if _bell_pp == "due":
                        ok, _m_pp = tg.send(
                            _fmt_prime_pair(
                                _kind, _sig_pp,
                                float(_px_pp or _sig_pp["entry"]), _now_pp)
                            + _kr_note(_sig_pp))
                        n_alerts += 1 if ok else 0
                        _bell_pp = "sent" if ok else f"failed: {_m_pp}"
                    print(f"  [prime-pair] {_kind} {_sym_pp} {_sd_pp} "
                          f"band={_band_pp} bell={_bell_pp}", flush=True)
                except Exception as _pp1:
                    print("  prime-pair item error:", _pp1, flush=True)
    except Exception as _pp_exc:
        print("  prime-pair error:", _pp_exc, flush=True)

    # 💯 CONVICTION v2 (user 2026-08-23: "remove kronos its not even
'''
W = rep(W, '    # 💯 CONVICTION v2 (user 2026-08-23: "remove kronos its not even\n',
        BLOCK, "pairing pass after the elite push")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "arr_long": "⚡ ARRIVAL T3 — every long break at an "\n'
        '                               "armed number (76%/+0.11R replay, proving)",\n',
        '                   "arr_long": "⚡ ARRIVAL T3 — every long break at an "\n'
        '                               "armed number (76%/+0.11R replay, proving)",\n'
        '                   "star_prime": "⭐🥇 STAR × PRIME — star fire + 🥇 PRIME on "\n'
        '                                 "the coin (76%/+0.48R Sep desk, every "\n'
        '                                 "band recorded, proving)",\n'
        '                   "conv_prime": "💎🥇 ELITE × PRIME — conviction fire + 🥇 "\n'
        '                                 "PRIME on the coin (60%/+0.28R Sep desk, "\n'
        '                                 "every band recorded, proving)",\n',
        "app tier names")

U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "arr_long": "arr_long",\n',
        '    "arr_long": "arr_long",\n    "star_prime": "star_prime",\n    "conv_prime": "conv_prime",\n',
        "auditor map")

for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: STAR × PRIME + ELITE × PRIME bells, tiers, names")

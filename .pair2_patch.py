"""💥🔮🥇 TRIG × KR × PRIME and 🔥🥇 SECOND LEG × PRIME (user 2026-10-11: "deploy
only prime with Trig x KR and Second leg with Prime … on the decision desk with
conf band split and on telegram"). Study .prime_pairs_all.py, desk 01-28 Sep,
overlap = PRIME 2h before → 30 min after the partner's open:
  trig_strong_kr + PRIME 83% / +0.37R (23) vs alone 70% / +0.05R (77); LONG 86% /
  +0.48R (7), SHORT 81% / +0.32R (16)
  second_leg + PRIME 73% / +0.47R (37) vs alone 51% / +0.10R (358); LONG 65% /
  +0.36R (23), SHORT 86% / +0.64R (14)
Both ride the existing pairing pass: own switch, own records-only desk tier,
every conf band rings and records (no band rule — the user asked for the split
on the desk), conf computed at the pass when the fire carries none. The decision
desk shows a by-conf-band line under every pair tier's row."""
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
W = rep(W, "TG_CONV_PRIME = True   # 💎🥇 bell. False = silent; desk tier conv_prime continues.\n",
        "TG_CONV_PRIME = True   # 💎🥇 bell. False = silent; desk tier conv_prime continues.\n"
        "# user 2026-10-11 (\"deploy only prime with Trig x KR and Second leg with\n"
        "# Prime\"): .prime_pairs_all.py — the strongest win-rate pair and the\n"
        "# biggest-lift pair on the board. No band rule: every band rings and records,\n"
        "# the desk splits the record by band.\n"
        "TG_TRIGKR_PRIME = True   # 💥🔮🥇 bell. False = silent; tier trigkr_prime continues.\n"
        "TG_LEG2_PRIME = True     # 🔥🥇 bell. False = silent; tier leg2_prime continues.\n", "switches")
W = rep(W,
        '    "LONG": "61% / +0.22R (46)", "SHORT": "59% / +0.36R (39)"}\n',
        '    "LONG": "61% / +0.22R (46)", "SHORT": "59% / +0.36R (39)"}\n'
        "TRIGKR_PRIME_REC = {\n"
        '    "window": "desk 01 Sep → 28 Sep", "all": "83% / +0.37R (23)",\n'
        '    "alone": "70% / +0.05R (77)", "LONG": "86% / +0.48R (7)",\n'
        '    "SHORT": "81% / +0.32R (16)"}\n'
        "LEG2_PRIME_REC = {\n"
        '    "window": "desk 01 Sep → 28 Sep", "all": "73% / +0.47R (37)",\n'
        '    "alone": "51% / +0.10R (358)", "LONG": "65% / +0.36R (23)",\n'
        '    "SHORT": "86% / +0.64R (14)"}\n'
        "PAIR_KINDS = {\n"
        '    "star": dict(tier="star_prime", rec=STAR_PRIME_REC, head="⭐🥇 *STAR × PRIME",\n'
        '                 who="⭐ star fire", alone="star", tag="⭐🥇", bands=True),\n'
        '    "conv": dict(tier="conv_prime", rec=CONV_PRIME_REC, head="💎🥇 *ELITE × PRIME",\n'
        '                 who="💎 elite conviction fire", alone="elite", tag="💎🥇", bands=True),\n'
        '    "trigkr": dict(tier="trigkr_prime", rec=TRIGKR_PRIME_REC,\n'
        '                   head="💥🔮🥇 *TRIG × KR × PRIME", who="💥🔮 TRIG × KR break",\n'
        '                   alone="TRIG × KR", tag="💥🔮🥇", bands=False),\n'
        '    "leg2": dict(tier="leg2_prime", rec=LEG2_PRIME_REC,\n'
        '                 head="🔥🥇 *SECOND LEG × PRIME", who="🔥 second-leg fire",\n'
        '                 alone="second leg", tag="🔥🥇", bands=False)}\n', "rec tables")
W = rep(W,
        "    star = kind == \"star\"\n"
        "    rec = STAR_PRIME_REC if star else CONV_PRIME_REC\n"
        "    tier = \"star_prime\" if star else \"conv_prime\"\n"
        "    band = _conf_band(sig.get(\"conf\"))\n"
        "    side = (sig.get(\"side\") or \"\").upper()\n"
        "    head = ((\"⭐🥇 *STAR × PRIME\" if star else \"💎🥇 *ELITE × PRIME\")\n"
        "            + f\" — {sig['base']} {side} · TAKE · {rung_stats.pkt_hm(now)} PKT*\")\n"
        "    who = \"⭐ star fire\" if star else \"💎 elite conviction fire\"\n",
        "    kd = PAIR_KINDS[kind]\n"
        "    rec, tier = kd[\"rec\"], kd[\"tier\"]\n"
        "    band = _conf_band(sig.get(\"conf\"))\n"
        "    side = (sig.get(\"side\") or \"\").upper()\n"
        "    head = (kd[\"head\"]\n"
        "            + f\" — {sig['base']} {side} · TAKE · {rung_stats.pkt_hm(now)} PKT*\")\n"
        "    who = kd[\"who\"]\n", "fmt head")
W = rep(W,
        "    l4 = (f\"pair record ({rec['window']}): {rec['all']} vs \"\n"
        "          f\"{'star' if star else 'elite'} alone {rec['alone']} · this band \"\n"
        "          f\"{rec.get(band or '', '—')} · {side.lower()}s {rec.get(side, '—')}\")\n",
        "    band_cell = (f\"this band {rec.get(band or '', '—')}\" if kd[\"bands\"]\n"
        "                 else \"every band rings; the desk splits the record by band\")\n"
        "    l4 = (f\"pair record ({rec['window']}): {rec['all']} vs \"\n"
        "          f\"{kd['alone']} alone {rec['alone']} · {band_cell} · \"\n"
        "          f\"{side.lower()}s {rec.get(side, '—')}\")\n", "fmt l4")
W = rep(W,
        "    l5 = (f\"forward ledger ({'⭐🥇' if star else '💎🥇'} pair): {fwd} · \"\n"
        "          f\"{rung_stats.stamp_now(now)}\")\n"
        "    l6 = (\"_one regime (September) behind the pair record — the forward ledger \"\n"
        "          \"per band decides; bands outside your list record silently._\")\n",
        "    l5 = (f\"forward ledger ({kd['tag']} pair): {fwd} · \"\n"
        "          f\"{rung_stats.stamp_now(now)}\")\n"
        "    l6 = ((\"_one regime (September) behind the pair record — the forward ledger \"\n"
        "           \"per band decides; bands outside your list record silently._\")\n"
        "          if kd[\"bands\"] else\n"
        "          (\"_one regime (September) and a thin count behind the pair record — \"\n"
        "           \"every band rings; the desk ledger split by band decides._\"))\n", "fmt l5 l6")
W = rep(W,
        "                (\"conv\", \"elite_conv\", \"conv_prime\", CONV_PRIME_BANDS,\n"
        "                 TG_CONV_PRIME)):\n",
        "                (\"conv\", \"elite_conv\", \"conv_prime\", CONV_PRIME_BANDS,\n"
        "                 TG_CONV_PRIME),\n"
        "                (\"trigkr\", \"trig_strong_kr\", \"trigkr_prime\", None,\n"
        "                 TG_TRIGKR_PRIME),\n"
        "                (\"leg2\", \"second_leg\", \"leg2_prime\", None,\n"
        "                 TG_LEG2_PRIME)):\n", "loop entries")
W = rep(W,
        "                    _conf_pp = _ex_pp.get(\"conf\")\n",
        "                    _conf_pp = _ex_pp.get(\"conf\")\n"
        "                    if _conf_pp is None:\n"
        "                        try:   # the fire carried no conf — read the board now\n"
        "                            _conf_pp = best_board.confidence(_sym_pp, _sd_pp)\n"
        "                        except Exception:\n"
        "                            _conf_pp = None\n", "conf fallback")
W = rep(W,
        "                                \"band-out\" if _band_pp not in _bands_pp else\n",
        "                                \"band-out\" if (_bands_pp is not None\n"
        "                                               and _band_pp not in _bands_pp) else\n", "band rule optional")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "conv_prime": "💎🥇 ELITE × PRIME — conviction fire + 🥇 "\n'
        '                                 "PRIME on the coin (60%/+0.28R Sep desk, "\n'
        '                                 "every band recorded, proving)",\n',
        '                   "conv_prime": "💎🥇 ELITE × PRIME — conviction fire + 🥇 "\n'
        '                                 "PRIME on the coin (60%/+0.28R Sep desk, "\n'
        '                                 "every band recorded, proving)",\n'
        '                   "trigkr_prime": "💥🔮🥇 TRIG × KR × PRIME — kronos-backed break + "\n'
        '                                   "🥇 PRIME on the coin (83%/+0.37R over 23, Sep "\n'
        '                                   "desk, thin; every band records, proving)",\n'
        '                   "leg2_prime": "🔥🥇 SECOND LEG × PRIME — second-leg fire + 🥇 "\n'
        '                                 "PRIME on the coin (73%/+0.47R over 37, Sep desk; "\n'
        '                                 "every band records, proving)",\n', "app names")
A = rep(A,
        "def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):\n",
        "_PAIR_SPLIT_TIERS = (\"star_prime\", \"conv_prime\", \"trigkr_prime\", \"leg2_prime\")\n"
        "\n"
        "\n"
        "@st.cache_data(ttl=300, show_spinner=False)\n"
        "def _pair_band_split(tier: str) -> str:\n"
        "    \"\"\"🥇 pair tiers on the desk, split by the fire's conf band (user\n"
        "    2026-10-11: 'on the decision desk with conf band split'). Clean closes,\n"
        "    read-only; a band under 5 closes prints its count only.\"\"\"\n"
        "    import sqlite3 as _sq_pb\n"
        "    _c = _sq_pb.connect(f\"file:{_ws_c.DB_PATH}?mode=ro\", uri=True)\n"
        "    try:\n"
        "        rows = _c.execute(\n"
        "            \"SELECT conf, pnl_r FROM shadow_trades WHERE tier=? AND status='CLOSED' \"\n"
        "            \"AND pnl_r IS NOT NULL AND entry>0 AND abs(entry-stop0)/entry>=0.005\",\n"
        "            (tier,)).fetchall()\n"
        "    finally:\n"
        "        _c.close()\n"
        "    if not rows:\n"
        "        return \"by conf band: no closes yet\"\n"
        "    bands = {\"40-54\": [], \"55-64\": [], \"65-74\": [], \"75-84\": [], \"85+\": [], \"unknown\": []}\n"
        "    for cf, r in rows:\n"
        "        try:\n"
        "            c = float(cf)\n"
        "            b = (\"40-54\" if c < 55 else \"55-64\" if c < 65 else \"65-74\" if c < 75\n"
        "                 else \"75-84\" if c < 85 else \"85+\") if 0 <= c <= 100 else \"unknown\"\n"
        "        except (TypeError, ValueError):\n"
        "            b = \"unknown\"\n"
        "        bands[b].append(float(r))\n"
        "    bits = []\n"
        "    for b, xs in bands.items():\n"
        "        if not xs:\n"
        "            continue\n"
        "        if len(xs) < 5:\n"
        "            bits.append(f\"{b}: {len(xs)} close{'s' if len(xs) != 1 else ''}\")\n"
        "        else:\n"
        "            bits.append(f\"{b}: {sum(1 for x in xs if x > 0) / len(xs) * 100:.0f}% / \"\n"
        "                        f\"{sum(xs) / len(xs):+.2f}R ({len(xs)})\")\n"
        "    return \"by conf band: \" + \" · \".join(bits)\n"
        "\n"
        "\n"
        "def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):\n", "split helper")
A = rep(A,
        "                f\"{_opn} open</span></div>\", unsafe_allow_html=True)\n"
        "\n"
        "        _active_rows, _bench_rows = [], []\n",
        "                f\"{_opn} open</span></div>\", unsafe_allow_html=True)\n"
        "            if rec.get(\"tier\") in _PAIR_SPLIT_TIERS:\n"
        "                try:   # 🥇 pair tiers: the record split by conf band\n"
        "                    st.caption(_pair_band_split(rec.get(\"tier\")))\n"
        "                except Exception:\n"
        "                    pass\n"
        "\n"
        "        _active_rows, _bench_rows = [], []\n", "split under the row")

U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "conv_prime": "conv_prime",\n',
        '    "conv_prime": "conv_prime",\n    "trigkr_prime": "trigkr_prime",\n    "leg2_prime": "leg2_prime",\n', "auditor map")

T = open(ROOT + ".prime_pair_test.py", encoding="utf-8").read()
T = rep(T,
        '            "STAR_PRIME_REC", "CONV_PRIME_REC", "STAR_PRIME_BANDS", "CONV_PRIME_BANDS", "TG_STAR_PRIME", "TG_CONV_PRIME") for t in n.targets):\n',
        '            "STAR_PRIME_REC", "CONV_PRIME_REC", "TRIGKR_PRIME_REC", "LEG2_PRIME_REC", "PAIR_KINDS", "STAR_PRIME_BANDS", "CONV_PRIME_BANDS",\n'
        '            "TG_STAR_PRIME", "TG_CONV_PRIME", "TG_TRIGKR_PRIME", "TG_LEG2_PRIME") for t in n.targets):\n', "test consts")
T = rep(T,
        "m3 = fmt(\"star\", dict(sig, conf=None), 184.5, NOW)\n",
        "m3 = fmt(\"star\", dict(sig, conf=None), 184.5, NOW)\n"
        "m4 = fmt(\"trigkr\", dict(sig, side=\"SHORT\", conf=58), 183.9, NOW)\n"
        "for need in (\"💥🔮🥇 *TRIG × KR × PRIME — AAVE SHORT · TAKE · \", \"💥🔮 TRIG × KR break + 🥇 PRIME\",\n"
        "             \"pair record (desk 01 Sep → 28 Sep): 83% / +0.37R (23) vs TRIG × KR alone 70% / +0.05R (77) · every band rings; the desk splits the record by band · shorts 81% / +0.32R (16)\",\n"
        "             \"forward ledger (💥🔮🥇 pair): \", \"a thin count behind the pair record\"):\n"
        "    if need not in m4:\n"
        "        fails.append(f\"trigkr pair message missing {need!r}\")\n"
        "m5 = fmt(\"leg2\", dict(sig, conf=72), 184.5, NOW)\n"
        "if not m5.startswith(\"🔥🥇 *SECOND LEG × PRIME — AAVE LONG · TAKE · \") or \"73% / +0.47R (37) vs second leg alone 51% / +0.10R (358)\" not in m5 or \"longs 65% / +0.36R (23)\" not in m5:\n"
        "    fails.append(f\"leg2 pair message wrong:\\n{m5}\")\n"
        "if not (ns[\"TG_TRIGKR_PRIME\"] is True and ns[\"TG_LEG2_PRIME\"] is True) or set(ns[\"PAIR_KINDS\"]) != {\"star\", \"conv\", \"trigkr\", \"leg2\"}:\n"
        "    fails.append(\"new pair switches / kinds wrong\")\n", "test formats")
T = rep(T, "for m in (m1, m2, m3):\n", "for m in (m1, m2, m3, m4, m5):\n", "markdown loop")
T = rep(T,
        "                  ('(\"conv\", \"elite_conv\", \"conv_prime\", CONV_PRIME_BANDS,\\n                 TG_CONV_PRIME)', \"conv pair config\"),\n",
        "                  ('(\"conv\", \"elite_conv\", \"conv_prime\", CONV_PRIME_BANDS,\\n                 TG_CONV_PRIME)', \"conv pair config\"),\n"
        "                  ('(\"trigkr\", \"trig_strong_kr\", \"trigkr_prime\", None,\\n                 TG_TRIGKR_PRIME)', \"trigkr pair config\"),\n"
        "                  ('(\"leg2\", \"second_leg\", \"leg2_prime\", None,\\n                 TG_LEG2_PRIME)', \"leg2 pair config\"),\n"
        "                  ('\"band-out\" if (_bands_pp is not None\\n                                               and _band_pp not in _bands_pp) else', \"band rule optional\"),\n"
        "                  ('_conf_pp = best_board.confidence(_sym_pp, _sd_pp)', \"conf fallback at the pass\"),\n", "test wiring")
T = rep(T,
        "for need in ('\"star_prime\": \"⭐🥇 STAR × PRIME', '\"conv_prime\": \"💎🥇 ELITE × PRIME'):\n",
        "for need in ('\"star_prime\": \"⭐🥇 STAR × PRIME', '\"conv_prime\": \"💎🥇 ELITE × PRIME', '\"trigkr_prime\": \"💥🔮🥇 TRIG × KR × PRIME',\n"
        "             '\"leg2_prime\": \"🔥🥇 SECOND LEG × PRIME', 'def _pair_band_split(tier: str) -> str:', 'st.caption(_pair_band_split(rec.get(\"tier\")))',\n"
        "             '_PAIR_SPLIT_TIERS = (\"star_prime\", \"conv_prime\", \"trigkr_prime\", \"leg2_prime\")'):\n", "test app")
T = rep(T,
        "for need in ('    \"star_prime\": \"star_prime\",\\n', '    \"conv_prime\": \"conv_prime\",\\n'):\n",
        "for need in ('    \"star_prime\": \"star_prime\",\\n', '    \"conv_prime\": \"conv_prime\",\\n', '    \"trigkr_prime\": \"trigkr_prime\",\\n', '    \"leg2_prime\": \"leg2_prime\",\\n'):\n", "test auditor")
for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U), (".prime_pair_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: TRIG × KR × PRIME + SECOND LEG × PRIME bells, tiers, desk conf split")

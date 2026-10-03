"""One-shot patch (user 2026-10-04: "Also mute from telegram: Comeback family,
unusual moves"): the three 🪂 comeback bells go through _MUTE_R9 and the news
radar's 🚨 unusual-move bell is switched off by a flag. Records, desk tiers,
the radar's memory and the 09:00 digest all continue. Anchors must match once."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
W = rep(W,
        '                    ok, _ = tg.send(\n'
        '                        f"🌊🪂 *FLUSH COMEBACK — {_cb_sig[\'base\']} "\n',
        '                    # 📵 MUTED (user 2026-10-04: "mute from telegram\n'
        '                    # ... Comeback family") — all three 🪂 bells.\n'
        '                    # Desk tiers comeback / comeback_g / comeback_f\n'
        '                    # and the board keep recording. Revert: _MUTE_R9\n'
        '                    # -> tg.send at the three sends.\n'
        '                    ok, _ = _MUTE_R9(\n'
        '                        f"🌊🪂 *FLUSH COMEBACK — {_cb_sig[\'base\']} "\n',
        "flush comeback")
W = rep(W,
        '                    ok, _ = tg.send(\n'
        '                        f"🛡🪂 *GUARDED COMEBACK — {_cb_sig[\'base\']} "\n',
        '                    ok, _ = _MUTE_R9(            # 📵 muted 2026-10-04\n'
        '                        f"🛡🪂 *GUARDED COMEBACK — {_cb_sig[\'base\']} "\n',
        "guarded comeback")
W = rep(W,
        '                    ok, _ = tg.send(\n'
        '                        f"🪂 *COMEBACK — {_cb_sig[\'base\']} "\n',
        '                    ok, _ = _MUTE_R9(            # 📵 muted 2026-10-04\n'
        '                        f"🪂 *COMEBACK — {_cb_sig[\'base\']} "\n',
        "plain comeback")

N = open(ROOT + "news_radar.py", encoding="utf-8").read()
N = rep(N,
        "MAX_BELLS_PER_RUN = 8\n",
        "MAX_BELLS_PER_RUN = 8\n"
        "# 📵 SURGE BELL OFF (user 2026-10-04: \"mute from telegram ... unusual\n"
        "# moves\"): the 🚨 UNUSUAL MOVE / DROP bell is not sent. The scan still\n"
        "# runs, records (kind unusual_move / unusual_drop), feeds the radar's\n"
        "# memory and the 09:00 PKT digest's 24h list. Revert: True.\n"
        "SURGE_BELL = False\n",
        "surge bell flag")
N = rep(N,
        "                 \"headlines\": [h.get(\"title\") for h in heads]})\n"
        "            out.append((2, msg))\n",
        "                 \"headlines\": [h.get(\"title\") for h in heads]})\n"
        "            if SURGE_BELL:\n"
        "                out.append((2, msg))\n",
        "surge outbox gate")

T = open(ROOT + ".news_radar_test.py", encoding="utf-8").read()
T = rep(T,
        "    out, rec = Outbox(), Recorder()\n"
        "    sent = nr.run(gk, [\"QNTUSDT\", \"BTCUSDT\"], out, record=rec, now=t0,\n"
        "                  fetch=no_fetch(rss=lambda: rows))\n"
        "    assert len(sent) == 1 and sent[0].startswith(\n"
        "        \"🚨 *UNUSUAL MOVE — QNT +\"), sent\n",
        "    out, rec = Outbox(), Recorder()\n"
        "    # 📵 the surge bell is muted by default since 2026-10-04 — the\n"
        "    # muted path must still RECORD and remember, and send nothing\n"
        "    assert nr.SURGE_BELL is False\n"
        "    sent = nr.run(gk, [\"QNTUSDT\", \"BTCUSDT\"], out, record=rec, now=t0,\n"
        "                  fetch=no_fetch(rss=lambda: rows))\n"
        "    assert sent == [], sent\n"
        "    assert any(p.get(\"kind\") == \"unusual_move\" for _, p in rec.rows)\n"
        "    assert nr._load_state().get(\"surges\"), \"muted surge must stay in memory\"\n"
        "    # the message itself, exercised once with the bell switched on\n"
        "    fresh_state(\"replay\")\n"
        "    nr.SURGE_BELL = True\n"
        "    out, rec = Outbox(), Recorder()\n"
        "    sent = nr.run(gk, [\"QNTUSDT\", \"BTCUSDT\"], out, record=rec, now=t0,\n"
        "                  fetch=no_fetch(rss=lambda: rows))\n"
        "    nr.SURGE_BELL = False\n"
        "    assert len(sent) == 1 and sent[0].startswith(\n"
        "        \"🚨 *UNUSUAL MOVE — QNT +\"), sent\n",
        "news radar test: muted path + message")

for path, s in (("agent_worker.py", W), ("news_radar.py", N), (".news_radar_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched agent_worker.py, news_radar.py, .news_radar_test.py")

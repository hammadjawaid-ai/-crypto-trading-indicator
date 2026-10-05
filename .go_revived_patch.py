"""⭐⚡ GO REVIVED as its own bell (user 2026-10-05: "have a GO revived as a
separate one please"). DEAD-at-1h fire ignites -> standalone message (the old
revival bell, new text); LIVE-at-1h fire ignites -> reply in the thread."""
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
W = rep(W,
        "                                try:\n"
        "                                    tg.send_thread(\n"
        "                                        rung_stats.go_text(\n"
        "                                            _ew, _prg, _age, _ew_px,\n"
        "                                            _ew_now),\n"
        '                                        reply_to=_ew.get("tg_ids"))\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _go_exc:\n",
        "                                try:\n"
        "                                    _go9 = rung_stats.go_text(\n"
        "                                        _ew, _prg, _age, _ew_px,\n"
        "                                        _ew_now)\n"
        '                                    if _ew.get("oneh") == "DEAD":\n'
        "                                        # ⭐⚡ GO REVIVED is its own\n"
        "                                        # bell (user 2026-10-05:\n"
        '                                        # "have a GO revived as a\n'
        '                                        # separate one") — standalone,\n'
        "                                        # not a thread reply.\n"
        "                                        tg.send(_go9)\n"
        "                                    else:\n"
        "                                        tg.send_thread(\n"
        "                                            _go9,\n"
        '                                            reply_to=_ew.get("tg_ids"))\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _go_exc:\n", "GO split")

T = open(ROOT + ".tg_rules_test.py", encoding="utf-8").read()
T = rep(T,
        '                  ("rung_stats.go_text(\\n                                            _ew, _prg, _age, _ew_px,\\n                                            _ew_now),\\n                                        reply_to=_ew.get(\\"tg_ids\\"))", "GO reply"),\n',
        '                  ("_go9 = rung_stats.go_text(\\n                                        _ew, _prg, _age, _ew_px,\\n                                        _ew_now)", "GO text built"),\n'
        '                  (\'if _ew.get("oneh") == "DEAD":\\n                                        # ⭐⚡ GO REVIVED is its own\', "revived branch"),\n'
        '                  ("tg.send(_go9)", "GO REVIVED standalone"),\n'
        '                  ("tg.send_thread(\\n                                            _go9,\\n                                            reply_to=_ew.get(\\"tg_ids\\"))", "GO thread reply"),\n',
        "test anchors")

for path, s in (("agent_worker.py", W), (".tg_rules_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: GO REVIVED standalone, GO reply for the rest")

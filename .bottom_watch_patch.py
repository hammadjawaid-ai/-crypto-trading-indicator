"""🌊⬆️ BOTTOM WATCH hook in the worker cycle, right after the shock-watch block:
one factual message per BTC dump print, with the SHORT bells rung into the low."""
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
W = rep(W, "import btc2h\n", "import btc2h\nimport bottom_watch\n", "import")
W = rep(W,
        "    except Exception as _sw_exc2:\n"
        '        print("  shock_watch start error:", _sw_exc2, flush=True)\n',
        "    except Exception as _sw_exc2:\n"
        '        print("  shock_watch start error:", _sw_exc2, flush=True)\n'
        "\n"
        "    # 🌊⬆️ BOTTOM WATCH (user 2026-10-09: \"BTC dumped to 80.3k ... all the\n"
        "    # alts bounced ... be more active with telegram notifications\"): ONE\n"
        "    # factual message at the first higher close after a >= 2% BTC dump\n"
        "    # (re-printed after a new low, max 3 per dump) with the measured odds\n"
        "    # from that print and the SHORT bells rung into the low. The 13-month\n"
        "    # study (.bottom_study.py) found no entry edge at any confirmation, so\n"
        "    # this is a read, never a bell to enter on. bottom_watch dedupes itself.\n"
        "    def _recent_short_bells(_since):\n"
        "        _out = []\n"
        "        try:\n"
        "            for _a in store.recent_alerts(300):\n"
        '                _aid = str(_a.get("alert_id") or "")\n'
        '                if float(_a.get("last_ts") or 0) < _since:\n'
        "                    continue\n"
        '                if (_aid.startswith(("elitestar:", "eliteagrade:"))\n'
        '                        and _aid.endswith(":SHORT")):\n'
        '                    _out.append(_aid.split(":")[1].replace("USDT", "") + " ⭐")\n'
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            import json as _json_bw\n"
        '            for _stream in ("star_go", "elite_go"):\n'
        "                for _g in store.recent_by_stream(_stream, 60):\n"
        '                    if (float(_g.get("ts") or 0) < _since\n'
        '                            or (_g.get("side") or "").upper() != "SHORT"):\n'
        "                        continue\n"
        "                    try:\n"
        '                        _ex = _json_bw.loads(_g.get("extra") or "{}")\n'
        "                    except Exception:\n"
        "                        _ex = {}\n"
        '                    if str(_ex.get("bell") or "").startswith("sent"):\n'
        '                        _out.append((_g.get("base")\n'
        '                                     or str(_g.get("symbol")).replace("USDT", ""))\n'
        '                                    + " ⚡GO")\n'
        "        except Exception:\n"
        "            pass\n"
        "        _seen, _res = set(), []\n"
        "        for _x in _out:\n"
        "            if _x not in _seen:\n"
        "                _seen.add(_x)\n"
        "                _res.append(_x)\n"
        "        return _res\n"
        "    try:\n"
        "        _bw = bottom_watch.run(binance_client.get_klines, tg.send,\n"
        "                               recent_shorts=_recent_short_bells)\n"
        "        if _bw:\n"
        '            print(f"[bottom] 🌊⬆️ print {_bw.get(\'prints_n\')} · low "\n'
        '                  f"{_bw.get(\'low\'):.0f} · depth {_bw.get(\'depth\', 0) * 100:+.1f}%",\n'
        "                  flush=True)\n"
        "    except Exception as _bw_exc:\n"
        '        print("  bottom_watch error:", _bw_exc, flush=True)\n', "hook")
with open(ROOT + "agent_worker.py", "w", encoding="utf-8", newline="") as f:
    f.write(W)
print("patched: bottom watch hook")

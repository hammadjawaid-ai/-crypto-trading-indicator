"""2026-10-06 — three fixes behind "I haven't heard any GO revived since yesterday":
1. the ignition watch (+ thread memory) survives a redeploy: saved to the state
   disk every cycle, reloaded at start (AAVE 18:57 PKT lost its 1h verdict to
   the 19:50 PKT restart on 10-05).
2. every star_go stamp records what the phone got ("bell": sent-standalone /
   sent-thread / not-buzzed / failed / error) and the ⭐ board chip shows it.
3. every thread send logs its result (Render logs answer the next "did it ring?").
Anchors must match exactly once or nothing is written."""
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

# 1. persistence helpers after the thread memory
W = rep(W, "_TG_THREADS: dict = {}\n",
        "_TG_THREADS: dict = {}\n"
        '_EGO_FILE = config.state_path(".ego_watch.json")\n'
        "\n"
        "\n"
        "def _ego_save() -> None:\n"
        '    """🧵 persist the ignition watch + thread memory so a redeploy never\n'
        "    drops a fire's verdict / GO / freeze (2026-10-05: AAVE lost its 1h\n"
        '    verdict to the 19:50 PKT restart). Called once per cycle."""\n'
        "    try:\n"
        "        import json as _json_eg\n"
        "        _now = time.time()\n"
        '        with open(str(_EGO_FILE), "w", encoding="utf-8") as _fd:\n'
        '            _json_eg.dump({"ts": _now,\n'
        '                           "watch": [w for w in _EGO_WATCH\n'
        '                                     if _now - float(w.get("fired_at") or 0)\n'
        "                                     < 24 * 3600],\n"
        '                           "threads": {f"{k[0]}|{k[1]}": v\n'
        "                                       for k, v in _TG_THREADS.items()\n"
        '                                       if _now - float((v or {}).get("ts")\n'
        "                                                       or 0) < 2 * 3600}},\n"
        "                          _fd, default=str)\n"
        "    except Exception as _eg_exc:\n"
        '        print("  ego save error:", _eg_exc, flush=True)\n'
        "\n"
        "\n"
        "def _ego_load() -> int:\n"
        '    """Restore the watch at start; returns the number of fires restored."""\n'
        "    try:\n"
        "        import json as _json_eg\n"
        '        with open(str(_EGO_FILE), encoding="utf-8") as _fd:\n'
        "            _d = _json_eg.load(_fd)\n"
        "        _now = time.time()\n"
        "        n = 0\n"
        '        for w in _d.get("watch") or []:\n'
        "            try:\n"
        '                if (w.get("symbol") and w.get("stop") and w.get("tp1")\n'
        '                        and _now - float(w.get("fired_at") or 0) < 24 * 3600):\n'
        '                    w["stop"], w["tp1"] = float(w["stop"]), float(w["tp1"])\n'
        '                    w["fired_at"] = float(w["fired_at"])\n'
        "                    _EGO_WATCH.append(w)\n"
        "                    n += 1\n"
        "            except Exception:\n"
        "                continue\n"
        '        for k, v in (_d.get("threads") or {}).items():\n'
        "            try:\n"
        '                sym, side = k.split("|", 1)\n'
        "                _TG_THREADS[(sym, side)] = v\n"
        "            except Exception:\n"
        "                continue\n"
        "        return n\n"
        "    except Exception:\n"
        "        return 0\n", "persistence helpers")

# save after the checker, every cycle
W = rep(W,
        "        except Exception as _ew_exc:\n"
        '            print("  ignition-watch error:", _ew_exc, flush=True)\n',
        "        except Exception as _ew_exc:\n"
        '            print("  ignition-watch error:", _ew_exc, flush=True)\n'
        "        _ego_save()\n", "save per cycle")

# load at start, right before the online ping
W = rep(W,
        "    if tg.enabled():\n"
        '        tg.send("🟢 *24/7 worker online* — watching for ✅🔥 TAKE NOW HOT and "\n',
        "    _n_eg = _ego_load()\n"
        '    print(f"  ignition watch restored: {_n_eg} fire(s)", flush=True)\n'
        "    if tg.enabled():\n"
        '        tg.send("🟢 *24/7 worker online* — watching for ✅🔥 TAKE NOW HOT and "\n',
        "load at start")

# 2. GO block: bell status, record after the send
W = rep(W,
        '                        _ew["go"] = ("FAST" if _age <= 4 * 3600\n'
        '                                     else "LATE")\n'
        '                        store.record_signal("star_go", {\n'
        '                            "symbol": _ew["symbol"],\n'
        '                            "base": _ew["base"],\n'
        '                            "side": _ew["side"],\n'
        '                            "tier": _ew["go"],\n'
        '                            "score": round(_age / 60.0, 1),\n'
        '                            "entry": _e0, "stop": _ew["stop"],\n'
        '                            "tp1": _ew["tp1"]})\n',
        '                        _ew["go"] = ("FAST" if _age <= 4 * 3600\n'
        '                                     else "LATE")\n'
        '                        _bell9 = "old-path"   # what the phone got\n',
        "GO record moved")
W = rep(W,
        '                            if (_ew.get("buzzed")\n'
        '                                    and _ew.get("fam", "elite") == "elite"):\n'
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
        "                                except Exception as _go_exc:\n"
        '                                    print("  GO thread error:", _go_exc,\n'
        "                                          flush=True)\n",
        '                            _bell9 = "not-buzzed (fire not on the phone)"\n'
        '                            if (_ew.get("buzzed")\n'
        '                                    and _ew.get("fam", "elite") == "elite"):\n'
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
        "                                        _ok9, _m9x = tg.send(_go9)\n"
        '                                        _bell9 = ("sent-standalone" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        "                                    else:\n"
        "                                        _ok9, _m9x, _ = tg.send_thread(\n"
        "                                            _go9,\n"
        '                                            reply_to=_ew.get("tg_ids"))\n'
        '                                        _bell9 = ("sent-thread" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _go_exc:\n"
        '                                    _bell9 = f"error: {_go_exc}"\n'
        '                                    print("  GO thread error:", _go_exc,\n'
        "                                          flush=True)\n"
        "                            print(f\"  [thread] GO {_ew['base']} \"\n"
        "                                  f\"{_ew['side']} {_ew['go']} \"\n"
        "                                  f\"1h={_ew.get('oneh')} bell={_bell9}\",\n"
        "                                  flush=True)\n", "GO bell status")
W = rep(W,
        '                        if _ew["go"] == "FAST":\n'
        "                            # control tier: forward-test that the\n",
        "                        # the stamp carries what the phone got (user\n"
        '                        # 2026-10-06: "I haven\'t heard any GO revived")\n'
        "                        # — the ⭐ board chip shows it.\n"
        '                        store.record_signal("star_go", {\n'
        '                            "symbol": _ew["symbol"],\n'
        '                            "base": _ew["base"],\n'
        '                            "side": _ew["side"],\n'
        '                            "tier": _ew["go"],\n'
        '                            "score": round(_age / 60.0, 1),\n'
        '                            "entry": _e0, "stop": _ew["stop"],\n'
        '                            "tp1": _ew["tp1"], "oneh": _ew.get("oneh"),\n'
        '                            "bell": _bell9})\n'
        '                        if _ew["go"] == "FAST":\n'
        "                            # control tier: forward-test that the\n", "GO record after send")

# 3. verdict + freeze sends log their result
W = rep(W,
        "                                try:\n"
        "                                    tg.send_thread(\n"
        "                                        rung_stats.verdict_text(\n"
        "                                            _ew, _prg, _ew_now),\n"
        '                                        reply_to=_ew.get("tg_ids"))\n'
        "                                    n_alerts += 1\n",
        "                                try:\n"
        "                                    _okv, _mv, _ = tg.send_thread(\n"
        "                                        rung_stats.verdict_text(\n"
        "                                            _ew, _prg, _ew_now),\n"
        '                                        reply_to=_ew.get("tg_ids"))\n'
        "                                    print(f\"  [thread] verdict {_ew['base']} \"\n"
        "                                          f\"{_ew['side']} {_ew['oneh']} \"\n"
        "                                          f\"sent={_okv} {_mv}\", flush=True)\n"
        "                                    n_alerts += 1\n", "verdict log")
W = rep(W,
        "                            try:\n"
        "                                tg.send_thread(\n"
        "                                    rung_stats.freeze_text(_ew, _ew_now),\n"
        '                                    reply_to=_ew.get("tg_ids"))\n'
        "                                n_alerts += 1\n",
        "                            try:\n"
        "                                _okf, _mf, _ = tg.send_thread(\n"
        "                                    rung_stats.freeze_text(_ew, _ew_now),\n"
        '                                    reply_to=_ew.get("tg_ids"))\n'
        "                                print(f\"  [thread] freeze {_ew['base']} \"\n"
        "                                      f\"{_ew['side']} sent={_okf} {_mf}\",\n"
        "                                      flush=True)\n"
        "                                n_alerts += 1\n", "freeze log")

# ⭐ board chip shows the bell status
A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                "SELECT ts, symbol, side, tier FROM signals WHERE "\n'
        '                "stream=\'star_go\' AND ts>=? ORDER BY ts", (_since,)).fetchall()\n',
        '                "SELECT ts, symbol, side, tier, extra FROM signals WHERE "\n'
        '                "stream=\'star_go\' AND ts>=? ORDER BY ts", (_since,)).fetchall()\n',
        "board go query")
A = rep(A,
        "            _gt = [g[3] for g in _go\n"
        '                   if g[1] == _sym and (g[2] or "").upper() == _sd and g[0] >= _ts]\n',
        "            _gt = [(g[3], g[4]) for g in _go\n"
        '                   if g[1] == _sym and (g[2] or "").upper() == _sd and g[0] >= _ts]\n',
        "board go list")
A = rep(A,
        "            if _gt:\n"
        '                _chips.append("⭐⚡ GO " + str(_gt[-1]))\n',
        "            if _gt:\n"
        '                _gb = ""\n'
        "                try:   # what the phone got for this GO (worker stamp)\n"
        '                    _gb = str((json.loads(_gt[-1][1] or "{}") or {}).get("bell") or "")\n'
        "                except Exception:\n"
        '                    _gb = ""\n'
        '                _chips.append("⭐⚡ GO " + str(_gt[-1][0])\n'
        '                              + (" (bell ✓)" if _gb.startswith("sent")\n'
        '                                 else f" (no bell: {_gb})" if _gb else ""))\n',
        "board go chip")

# tests
T = open(ROOT + ".tg_rules_test.py", encoding="utf-8").read()
T = rep(T,
        '                  ("tg.send(_go9)", "GO REVIVED standalone"),\n',
        '                  ("_ok9, _m9x = tg.send(_go9)", "GO REVIVED standalone"),\n'
        '                  (\'_bell9 = "not-buzzed (fire not on the phone)"\', "GO bell status default"),\n'
        '                  (\'"tp1": _ew["tp1"], "oneh": _ew.get("oneh"),\\n                            "bell": _bell9})\', "GO stamp carries the bell status"),\n'
        '                  ("def _ego_save() -> None:", "watch persisted"),\n'
        '                  ("def _ego_load() -> int:", "watch restored"),\n'
        '                  ("        _ego_save()\\n", "save each cycle"),\n'
        '                  ("    _n_eg = _ego_load()\\n", "load at start"),\n'
        '                  ("[thread] verdict", "verdict send logged"),\n'
        '                  ("[thread] freeze", "freeze send logged"),\n',
        "test anchors")
T = rep(T, "# ghost scan of the touched modules\n",
        "# the GO stamp must come AFTER the send (it records what the phone got)\n"
        'if not (0 < W.find("_bell9 = \\"not-buzzed") < W.find(\'"bell": _bell9})\') < W.find(\'if _ew["go"] == "FAST":\')):\n'
        '    fails.append("GO stamp must follow the send and precede the chase tier")\n'
        "# persistence round-trip (the two helpers run standalone)\n"
        "import ast as _ast\n"
        "_ns = {\"time\": time, \"_EGO_WATCH\": [], \"_TG_THREADS\": {}, \"_EGO_FILE\": os.path.join(tmp, \"ego.json\"), \"print\": print}\n"
        "for _n in _ast.parse(W).body:\n"
        '    if isinstance(_n, _ast.FunctionDef) and _n.name in ("_ego_save", "_ego_load"):\n'
        '        exec(compile(_ast.Module(body=[_n], type_ignores=[]), _n.name, "exec"), _ns)\n'
        '_ns["_EGO_WATCH"].extend([{"symbol": "ZECUSDT", "base": "ZEC", "side": "SHORT", "stop": 1371.34, "tp1": 1249.37, "tp2": None, "tier": "HIGH", "star": True, "appr": True,\n'
        '                          "entry0": 1299.5, "go": None, "oneh": "DEAD", "froze": False, "buzzed": True, "fam": "elite", "fired_at": time.time() - 3 * 3600, "tg_ids": {"1": 555}},\n'
        '                         {"symbol": "OLDUSDT", "base": "OLD", "side": "LONG", "stop": 1, "tp1": 2, "fired_at": time.time() - 30 * 3600, "fam": "elite"}])\n'
        '_ns["_TG_THREADS"][("ZECUSDT", "SHORT")] = {"ts": time.time() - 3 * 3600, "ids": {"1": 555}}\n'
        '_ns["_TG_THREADS"][("NEWUSDT", "LONG")] = {"ts": time.time() - 600, "ids": {"1": 777}}\n'
        '_ns["_ego_save"]()\n'
        '_ns["_EGO_WATCH"].clear(); _ns["_TG_THREADS"].clear()\n'
        '_nr = _ns["_ego_load"]()\n'
        '_w = _ns["_EGO_WATCH"]\n'
        'if _nr != 1 or len(_w) != 1 or _w[0]["symbol"] != "ZECUSDT" or _w[0]["tg_ids"] != {"1": 555} or _w[0]["oneh"] != "DEAD" or not _w[0]["buzzed"]:\n'
        '    fails.append(f"watch round-trip wrong: {_nr} {_w}")\n'
        'if _ns["_TG_THREADS"] != {("NEWUSDT", "LONG"): {"ts": _ns["_TG_THREADS"].get(("NEWUSDT", "LONG"), {}).get("ts"), "ids": {"1": 777}}}:\n'
        '    fails.append(f"thread memory round-trip wrong (old entries must drop): {_ns[\'_TG_THREADS\']}")\n'
        "A_ = open(os.path.join(ROOT, \"app.py\"), encoding=\"utf-8\").read()\n"
        'for need in ("SELECT ts, symbol, side, tier, extra FROM signals WHERE ", \'(" (bell ✓)" if _gb.startswith("sent")\'):\n'
        "    if need not in A_:\n"
        '        fails.append(f"board chip missing: {need[:40]}")\n'
        "# ghost scan of the touched modules\n", "persistence test")

for path, s in (("agent_worker.py", W), ("app.py", A), (".tg_rules_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: watch persistence, GO bell status + board chip, thread send logs")

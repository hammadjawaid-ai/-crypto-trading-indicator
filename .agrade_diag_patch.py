"""A-GRADE WATCH diagnostic (user 2026-10-05: "I haven't had an A-grade trade the
whole day ... where does this A-grade lie?"). The worker writes .agrade_status.json
every cycle from the elite desk-tier block: how many Top Conviction seats are in
memory, how many elite cards exist and how many carry conf 65+, which are seated,
which qualified as SEATED-65 / A-GRADE this cycle, and running totals since the
worker started. The Paper Trader page shows it under the elite board, so the next
"is it working?" is answered by the page, not by a guess. Nothing else changes."""
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
W = rep(W, "_SEATS: dict = {}\n",
        "_SEATS: dict = {}\n"
        "_AG_DIAG: dict = {\"cycles\": 0, \"seated65_total\": 0, \"agrade_total\": 0,\n"
        "                  \"last_seated65\": None, \"last_agrade\": None,\n"
        "                  \"started\": time.time()}\n", "diag dict")
W = rep(W,
        "            except Exception as _gq_exc:\n"
        "                print(\"  elite grade error:\", _gq_exc, flush=True)\n"
        "        _tiers = ((\"top_conviction\", _topc),\n",
        "            except Exception as _gq_exc:\n"
        "                print(\"  elite grade error:\", _gq_exc, flush=True)\n"
        "        # \U0001F3C6 A-GRADE WATCH status (user 2026-10-05: \"where does this\n"
        "        # A-grade lie?\") — one small file per cycle the page can show.\n"
        "        try:\n"
        "            _AG_DIAG[\"cycles\"] += 1\n"
        "            _AG_DIAG[\"seated65_total\"] += len(_s65_list)\n"
        "            _AG_DIAG[\"agrade_total\"] += len(_ag_list)\n"
        "            if _s65_list:\n"
        "                _AG_DIAG[\"last_seated65\"] = time.time()\n"
        "            if _ag_list:\n"
        "                _AG_DIAG[\"last_agrade\"] = time.time()\n"
        "\n"
        "            def _cf_ok(_v):\n"
        "                try:\n"
        "                    return 65 <= float(_v) <= 100\n"
        "                except (TypeError, ValueError):\n"
        "                    return False\n"
        "            _seated_now = [f\"{q.get('symbol')} {q.get('side')}\"\n"
        "                           for q in _ec_mh\n"
        "                           if _seat_of(q.get(\"symbol\"), q.get(\"side\"))]\n"
        "            _diag = dict(_AG_DIAG, ts=time.time(),\n"
        "                         seats=sorted(f\"{s} {d}\" for (s, d) in _SEATS),\n"
        "                         elite_cards=len(_ec_mh),\n"
        "                         elite_conf65=sum(1 for q in _ec_mh\n"
        "                                          if _cf_ok(q.get(\"conf\"))),\n"
        "                         elite_seated_now=_seated_now,\n"
        "                         seated65_now=[g[\"symbol\"] for g in _s65_list],\n"
        "                         agrade_now=[g[\"symbol\"] for g in _ag_list])\n"
        "            with open(str(config.state_path(\".agrade_status.json\")), \"w\",\n"
        "                      encoding=\"utf-8\") as _fd:\n"
        "                json.dump(_diag, _fd, default=str)\n"
        "        except Exception as _dg_exc:\n"
        "            print(\"  agrade diag error:\", _dg_exc, flush=True)\n"
        "        _tiers = ((\"top_conviction\", _topc),\n", "diag write")
if "import json" not in W:
    raise SystemExit("agent_worker.py has no json import")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        "                       + \" \" + _warm_caption())\n",
        "                       + \" \" + _warm_caption())\n"
        "            try:   # \U0001F3C6 A-GRADE WATCH — the worker's own status\n"
        "                with open(str(config.state_path(\".agrade_status.json\")),\n"
        "                          encoding=\"utf-8\") as _fa:\n"
        "                    _ags = json.load(_fa)\n"
        "                _age_m = (time.time() - float(_ags.get(\"ts\") or 0)) / 60\n"
        "                _ls = _ags.get(\"last_seated65\")\n"
        "                _la = _ags.get(\"last_agrade\")\n"
        "                _fmt_ago = (lambda t: f\"{(time.time() - float(t)) / 3600:.1f}h ago\"\n"
        "                            if t else \"never since the worker started\")\n"
        "                st.caption(\n"
        "                    f\"\U0001F3C6 A-GRADE WATCH (worker status {_age_m:.0f} min old): \"\n"
        "                    f\"{len(_ags.get('seats') or [])} Top Conviction seats in \"\n"
        "                    f\"memory [{', '.join(_ags.get('seats') or [])[:160]}] · \"\n"
        "                    f\"{_ags.get('elite_cards')} elite cards, \"\n"
        "                    f\"{_ags.get('elite_conf65')} with conf 65+ · seated now: \"\n"
        "                    f\"{', '.join(_ags.get('elite_seated_now') or []) or 'none'} · \"\n"
        "                    f\"SEATED-65 this cycle: {', '.join(_ags.get('seated65_now') or []) or 'none'} · \"\n"
        "                    f\"A-GRADE this cycle: {', '.join(_ags.get('agrade_now') or []) or 'none'} · \"\n"
        "                    f\"since worker start ({_ags.get('cycles')} cycles): \"\n"
        "                    f\"seated-65 {_ags.get('seated65_total')} (last {_fmt_ago(_ls)}), \"\n"
        "                    f\"A-grade {_ags.get('agrade_total')} (last {_fmt_ago(_la)}).\")\n"
        "            except Exception:\n"
        "                st.caption(\"\U0001F3C6 A-GRADE WATCH: no status file yet — the worker \"\n"
        "                           \"has not completed a cycle on the new code.\")\n", "app caption")

T = open(ROOT + ".agrade_test.py", encoding="utf-8").read()
T = rep(T, "print(m)\nprint(\"ELITE A-GRADE:\", \"ALL PASS\" if not fails else fails)\n",
        "for need, lab in (('json.dump(_diag, _fd, default=str)', \"worker writes the status file\"),\n"
        "                  ('elite_conf65=sum(1 for q in _ec_mh', \"conf-65 count\"),\n"
        "                  ('seated65_now=[g[\"symbol\"] for g in _s65_list]', \"seated list\")):\n"
        "    if need not in W:\n"
        "        fails.append(f\"diag missing: {lab}\")\n"
        "if W.find('json.dump(_diag, _fd, default=str)') > W.find('_tiers = ((\"top_conviction\", _topc),'):\n"
        "    fails.append(\"diag must be written before the tiers tuple\")\n"
        "if 'A-GRADE WATCH (worker status' not in A:\n"
        "    fails.append(\"app caption missing\")\n"
        "print(m)\nprint(\"ELITE A-GRADE:\", \"ALL PASS\" if not fails else fails)\n", "test additions")

for path, s in (("agent_worker.py", W), ("app.py", A), (".agrade_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: A-GRADE WATCH status file + page caption")

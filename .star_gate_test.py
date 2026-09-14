"""⭐ Verify the star bell is now independent of the elite gates.

Static check of the restructured _push_elite: the star detection must
precede the gates, the gates must be inside `if not _star9:`, and the
star must use its own alert key.
"""
import ast
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"F:\Trading Indicator\agent_worker.py",
           encoding="utf-8").read()
ast.parse(src)

blk = src.split("def _push_elite")[1].split("\n    tn_hot =")[0]
fails = []

i_star = blk.find("_star9 = (bool(_pmx.get(\"appr\"))")
i_gate = blk.find("if not _star9:")
i_conf = blk.find("if _cf9 is not None and _cf9 < 40:")
i_kron = blk.find("_kr_cache_agree")  # inside the unified gate
i_appr = blk.find("if not _pmx.get(\"appr\") and not _kr_cache_agree(")
i_key = blk.find("_key9 = (\"elitestar\" if _star9 else \"eliteconv\")")

if not (0 < i_star < i_gate < i_conf):
    fails.append("star detection does not precede the gates")
if not (i_gate < i_kron < i_key):
    fails.append("kronos gate not inside the not-star block")
if not (i_gate < i_appr < i_key):
    fails.append("unified appr+kronos gate not inside the "
                 "not-star block")
if i_key < 0:
    fails.append("star alert key missing")

# the three gates must be indented deeper than `if not _star9:`
for name, idx in (("conf", i_conf),
                  ("appr+kronos", i_appr)):
    line = blk[:idx].split("\n")[-1]
    if len(line) - len(line.lstrip()) < 20:
        fails.append(f"{name} gate indentation too shallow "
                     f"({len(line) - len(line.lstrip())}) — may not "
                     f"be inside the not-star block")

# only ONE star detection remains (no duplicate leftover)
if blk.count("_star9 = (bool(_pmx.get(\"appr\"))") != 1:
    fails.append("duplicate star detection block left behind")

# the star RECORDING path still exists. NOTE the ⭐ headline was
# removed from the buzz on 2026-09-14 ("remove what we build with
# elite star") — star fires now buzz as plain elite conviction while
# the desk tier, board and demo feed keep proving the profile, so
# the headline string is deliberately NOT checked any more.
for need in ("store.record_signal(\"elite_star\"",
             "_DEMO_STARS.append(", "_ego_add(dict(_st_sig"):
    if need not in blk:
        fails.append(f"missing star path piece: {need}")

print("star-bell independence:",
      "ALL PASS" if not fails else "FAILS:")
for f in fails:
    print("  ✗", f)

"""Page-speed patch 3 — the warm store must survive Streamlit reruns.
Streamlit re-executes app.py for every script run with a fresh module namespace,
so plain module-level dicts (_WARM_STORE / _WARM_STATUS) were re-created empty on
every page load: the warmer thread wrote into the first run's dicts and every
later run read nothing ("boards computing in the page ... NOT YET" on Render).
Fix: both dicts come from one st.cache_resource singleton (process-global, same
object in every run and in the warmer thread). The caption also falls back to the
status file. The speed check now clears st.cache_data before the warm run and
asserts the pre-computed caption, so the warm-store path is what is measured."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        "WARM_EVERY = 300\n"
        "WARM_MAX_AGE = 3 * WARM_EVERY\n"
        "_WARM_STORE: dict = {}\n"
        "_WARM_STATUS: dict = {\"last_sweep\": None, \"sweep_s\": None, \"jobs\": {},\n"
        "                      \"errors\": {}, \"sweeps\": 0}\n"
        "_WARM_STATUS_FILE = str(config.state_path(\".app_warm.json\"))\n",
        "WARM_EVERY = 300\n"
        "WARM_MAX_AGE = 3 * WARM_EVERY\n"
        "_WARM_STATUS_FILE = str(config.state_path(\".app_warm.json\"))\n"
        "\n"
        "\n"
        "@st.cache_resource(show_spinner=False)\n"
        "def _warm_state() -> dict:\n"
        "    \"\"\"ONE process-global home for the warm results. Streamlit re-runs\n"
        "    this script with a fresh namespace on every page load, so a plain\n"
        "    module dict would be empty again each run; cache_resource hands\n"
        "    back the same object to every run and to the warmer thread.\"\"\"\n"
        "    return {\"store\": {},\n"
        "            \"status\": {\"last_sweep\": None, \"sweep_s\": None, \"jobs\": {},\n"
        "                       \"errors\": {}, \"sweeps\": 0}}\n"
        "\n"
        "\n"
        "_WARM_STORE: dict = _warm_state()[\"store\"]\n"
        "_WARM_STATUS: dict = _warm_state()[\"status\"]\n",
        "warm state singleton")
A = rep(A,
        "def _warm_caption() -> str:\n"
        "    \"\"\"One line for the boards: how fresh the pre-computed scans are.\"\"\"\n"
        "    ls = _WARM_STATUS.get(\"last_sweep\")\n",
        "def _warm_caption() -> str:\n"
        "    \"\"\"One line for the boards: how fresh the pre-computed scans are.\"\"\"\n"
        "    ls = _WARM_STATUS.get(\"last_sweep\")\n"
        "    if not ls:\n"
        "        try:   # fall back to the status file the sweep writes\n"
        "            with open(_WARM_STATUS_FILE, encoding=\"utf-8\") as _f:\n"
        "                _st_f = json.load(_f)\n"
        "            if _st_f.get(\"last_sweep\"):\n"
        "                _WARM_STATUS.update(_st_f)\n"
        "                ls = _WARM_STATUS.get(\"last_sweep\")\n"
        "        except Exception:\n"
        "            pass\n",
        "caption file fallback")

C = open(ROOT + ".pt_speed_check.py", encoding="utf-8").read()
C = rep(C,
        "w = load(\"run 2, warm\")\n",
        "st.cache_data.clear()      # the warm run must come from the warm store, not from run 1's data caches\n"
        "w = load(\"run 2, warm\")\n"
        "cap = [lab for _, _, lab in marks if \"pre-computed\" in lab or \"boards computing\" in lab]\n"
        "print(\"warm caption:\", cap[:1])\n"
        "if not any(\"pre-computed\" in c for c in cap):\n"
        "    print(\"!! WARM STORE NOT USED — the page did not see the warmer's results\")\n",
        "speed check asserts the warm caption")

T = open(ROOT + ".pt_speed_test.py", encoding="utf-8").read()
T = rep(T,
        "want = {\"_warm_get\", \"_warm_put\", \"WARM_EVERY\", \"WARM_MAX_AGE\", \"_WARM_STORE\"}\n",
        "for need in (\"def _warm_state() -> dict:\", \"_WARM_STORE: dict = _warm_state()[\\\"store\\\"]\", \"_WARM_STATUS: dict = _warm_state()[\\\"status\\\"]\"):\n"
        "    if need not in A:\n"
        "        fails.append(f\"warm state singleton missing: {need}\")\n"
        "if \"_WARM_STORE: dict = {}\" in A:\n"
        "    fails.append(\"warm store is still a per-run module dict\")\n"
        "want = {\"_warm_get\", \"_warm_put\", \"WARM_EVERY\", \"WARM_MAX_AGE\"}\n",
        "test: singleton checks")
T = rep(T,
        "import copy\nns = {\"time\": time, \"_copy\": copy}\n",
        "import copy\nns = {\"time\": time, \"_copy\": copy, \"_WARM_STORE\": {}}\n",
        "test: store in namespace")

for path, s in (("app.py", A), (".pt_speed_check.py", C), (".pt_speed_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched app.py, .pt_speed_check.py, .pt_speed_test.py")

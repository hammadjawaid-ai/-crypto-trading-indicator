"""Guard — one thread per numeric library, and the scan below the web app (2026-11-18, the server-down fix).
launch.py must cap the native thread pools before anything imports numpy / torch and before the Streamlit
subprocess starts, without overriding a value set in the environment; the forecast module must cap torch itself.
No network. Run: .venv/Scripts/python.exe .server_threads_test.py
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("  ✅", name)
    else:
        FAIL.append(name)
        print("  ❌", name, detail)


KEYS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
CODE = ("import os, sys; sys.path.insert(0, r'%s'); import launch; "
        "print('|'.join(str(os.environ.get(k)) for k in %r + ('TOKENIZERS_PARALLELISM',))); "
        "print('numpy' in sys.modules, 'torch' in sys.modules, launch.BRAIN_NICE)") % (ROOT, KEYS)
env = {k: v for k, v in os.environ.items() if k not in KEYS and k != "TOKENIZERS_PARALLELISM"}
out = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, env=env).stdout.strip().splitlines()
check("launch.py caps every native pool to one thread when nothing is set", out and out[0] == "1|1|1|1|1|false", out)
check("launch.py does it before numpy or torch is imported, and the scan's priority is lowered", len(out) > 1 and out[1] == "False False 10", out)
env2 = dict(env, OMP_NUM_THREADS="3")
out2 = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, env=env2).stdout.strip().splitlines()
check("a value set in the environment (the Render dashboard) still wins", out2 and out2[0].startswith("3|1|1|1|1"), out2)
L = io.open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
i_cap, i_brain, i_sub = L.index('os.environ.setdefault(_k, "1")'), L.index("def _brain()"), L.index("subprocess.run(cmd)")
check("the cap sits at module level, above the brain thread and the Streamlit subprocess", i_cap < i_brain < i_sub)
i_nice, i_imp = L.index("os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), BRAIN_NICE)"), L.index("    import agent_worker")
check("the brain lowers its own priority before it imports the worker, inside a try", i_brain < i_nice < i_imp and "except Exception as _nice_exc" in L)
K = io.open(os.path.join(ROOT, "kronos_forecast.py"), encoding="utf-8").read()
check("the forecast module caps torch before the model is built",
      "torch.set_num_threads(THREADS)" in K and "torch.set_num_interop_threads(THREADS)" in K
      and K.index("    _cap_threads()\n    if _predictor is None:") > K.index("def _get_predictor():"))
try:
    import torch
    import kronos_forecast as kf
    kf._threads_set[0] = False
    kf._cap_threads()
    check("torch runs on one thread after the cap", torch.get_num_threads() == kf.THREADS == 1, torch.get_num_threads())
except ImportError:
    print("  (torch not installed here: the live cap is not exercised)")

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)

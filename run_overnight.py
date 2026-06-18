"""Validation orchestrator (v2 — live-streaming, fast-first, monitorable).

Runs every backtest SEQUENTIALLY (no API contention). Each job's output
streams LIVE to .overnight/<slug>.txt (no buffering), and .overnight/
STATUS.txt is rewritten before/after every job so progress is always
visible. Survives any individual job crashing or timing out.

Order: fast vectorized jobs first (results within minutes), the slow
per-bar score_from_data jobs (sst1/elite/tiers) last.
"""
from __future__ import annotations
import os, sys, io, time, subprocess
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
OUT = os.path.join(HERE, ".overnight")
os.makedirs(OUT, exist_ok=True)
STATUS = os.path.join(OUT, "STATUS.txt")

# (slug, script, args, timeout_sec) — FAST first, SLOW last
JOBS = [
    ("grind",           "backtest_grind.py",           [], 1800),
    ("velocity_burst",  "backtest_velocity_burst.py",  [], 1800),
    ("early_burst_15m", "backtest_early_burst.py",     [], 1800),
    ("components",      "backtest_components.py",       [], 2400),
    ("phase_cef",       "backtest_phase_cef.py",       [], 2400),
    ("recovery",        "backtest_recovery.py",         [], 2400),
    ("long_patterns",   "backtest_long_patterns.py",    [], 2400),
    ("rebound_breakout","backtest_rebound_breakout.py", [], 2400),
    ("convergence",     "backtest_convergence.py",      [], 3600),
    ("predictor",       "backtest_predict.py",          [], 3600),
    ("elite_by_tier",   "backtest_elite.py",            ["--coins", "15", "--bars", "800"], 4500),
    ("tiers_with_costs","backtest_tiers_with_costs.py", [], 5400),
    ("sst1",            "backtest_sst1.py",             [], 9000),
]

def write_status(done, current, results):
    with open(STATUS, "w", encoding="utf-8") as f:
        f.write(f"OVERNIGHT SUITE — {done}/{len(JOBS)} done\n")
        f.write(f"current: {current}\n")
        f.write("=" * 60 + "\n")
        for slug, status, dur, tail in results:
            f.write(f"[{status:8}] {slug}  ({dur:.0f}s)\n")

results = []
t_all = time.time()
print(f"=== SUITE v2 START === {len(JOBS)} jobs", flush=True)
write_status(0, JOBS[0][0], results)

for i, (slug, script, args, timeout) in enumerate(JOBS):
    path = os.path.join(HERE, script)
    write_status(i, f"{slug} ({script})", results)
    if not os.path.exists(path):
        print(f"[SKIP] {slug}: not found", flush=True)
        results.append((slug, "MISSING", 0.0, "file not found"))
        continue
    print(f"\n[RUN ] {slug}: {script} {' '.join(args)}", flush=True)
    t0 = time.time()
    outfile = os.path.join(OUT, f"{slug}.txt")
    try:
        with open(outfile, "w", encoding="utf-8") as fout:
            proc = subprocess.run(
                [PY, script, *args], cwd=HERE,
                stdout=fout, stderr=subprocess.STDOUT,
                timeout=timeout)
        dur = time.time() - t0
        status = "OK" if proc.returncode == 0 else f"EXIT{proc.returncode}"
        try:
            tail = "\n".join(open(outfile, encoding="utf-8",
                              errors="replace").read().strip().splitlines()[-3:])
        except Exception:
            tail = ""
        print(f"[DONE] {slug}: {status} in {dur:.0f}s", flush=True)
        results.append((slug, status, dur, tail))
    except subprocess.TimeoutExpired:
        dur = time.time() - t0
        print(f"[TIME] {slug}: TIMEOUT after {dur:.0f}s", flush=True)
        results.append((slug, "TIMEOUT", dur, "timed out"))
    except Exception as exc:
        dur = time.time() - t0
        print(f"[ERR ] {slug}: {type(exc).__name__}: {exc}", flush=True)
        results.append((slug, "ERROR", dur, str(exc)))
    write_status(i + 1, "(next)", results)

write_status(len(JOBS), "COMPLETE", results)
print(f"\n=== SUITE COMPLETE === {time.time()-t_all:.0f}s", flush=True)
for slug, status, dur, _ in results:
    print(f"  {status:8} {slug} ({dur:.0f}s)", flush=True)

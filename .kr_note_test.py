"""Kronos one-glance line: renders for agree / disagree / flat / no read, + markdown safety."""
import ast, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_kr_note")
class _KF:
    @staticmethod
    def available(): return False
ns = {"time": time, "KR_TTL": 7200, "kf": _KF}
def run(cache):
    ns["_KR_CACHE"] = cache
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "kr", "exec"), ns)
    return ns["_kr_note"]
now = time.time(); fails = []
cases = [
    ({"X": {"t": now, "s": {"direction": "UP", "exp_move_pct": 2.1}}}, "LONG", "🔮 ✅ Kronos agrees · UP +2.1%/24h"),
    ({"X": {"t": now, "s": {"direction": "DOWN", "exp_move_pct": -1.8}}}, "LONG", "🔮 ❌ Kronos disagrees · DOWN -1.8%/24h"),
    ({"X": {"t": now, "s": {"direction": "DOWN", "exp_move_pct": -1.8}}}, "SHORT", "🔮 ✅ Kronos agrees · DOWN -1.8%/24h"),
    ({"X": {"t": now, "s": {"direction": "FLAT", "exp_move_pct": 0.3}}}, "LONG", "🔮 ➖ Kronos flat · +0.3%/24h"),
    ({}, "LONG", "🔮 ❔ Kronos: no read"),
    ({"X": {"t": now - 99999, "s": {"direction": "UP", "exp_move_pct": 2.1}}}, "LONG", "🔮 ❔ Kronos: no read"),
]
for cache, side, want in cases:
    got = run(cache)({"symbol": "X", "side": side})
    if got != "\n" + want: fails.append(f"{side}/{cache and cache['X']['s']['direction']}: got {got!r}")
    if any(ch in got for ch in "*_`[]"): fails.append(f"markdown char in {got!r}")
    print(" ", got.strip())
print("KRONOS LINE:", "ALL PASS" if not fails else fails)

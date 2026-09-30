"""APEX V2 bell - formatter render + wiring checks."""
import ast, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_fmt_apex_v2")
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "fmt", "exec"), ns)
f = ns["_fmt_apex_v2"]
fails = []
L = f({"symbol": "LDOUSDT", "base": "LDO", "side": "LONG", "entry": 1.10, "stop": 1.06, "tp1": 1.135, "tp2": 1.165, "score": 92, "heat": 58},
      1.101, {"tier": "apex_v2", "n": 30, "win_pct": 53.3, "net_r": 3.63})
S = f({"symbol": "OPUSDT", "base": "OP", "side": "SHORT", "entry": 0.80, "stop": 0.83, "tp1": 0.775, "tp2": 0.755, "score": 91, "heat": 40}, None, None)
N = f({"symbol": "XUSDT", "base": "X", "side": "LONG", "entry": 2.0, "stop": 1.9, "tp1": 2.1, "tp2": None, "score": 90, "heat": 70}, 2.0, None)
for m in (L, S, N):
    if "\ufffd" in m or m.count("*") % 2 or m.count("`") % 2 or "_" in m.replace("`", ""):
        fails.append("markdown/encoding issue")
if "(+0.8R)" not in L or "TP2 `1.165` (+1.6R)" not in L or "30 closed · 53% win · +3.6R" not in L:
    fails.append("LONG plan/R/desk line wrong")
if "(+0.8R)" not in S or "TP2 `0.755` (+1.5R)" not in S:
    fails.append("SHORT R multiples wrong")
if "TP2" in N or "trail 1.2R" not in N:
    fails.append("no-TP2 variant wrong")
blk = src[src.index('shadow_trader.open_from_signal("apex_v2"'):][:900]
for need in ("_bstock_quiet(_sym2)", "_fmt_apex_v2(_sig2, _px2, _rv2)", "_kr_note(_sig2)", "tg.send("):
    if need not in blk:
        fails.append(f"hook missing {need}")
if src.index('store.should_alert(f"apexv2:') > src.index('_fmt_apex_v2(_sig2, _px2, _rv2)'):
    fails.append("bell must sit after the 2h dedup gate")
print(L, "\n\n" + S, "\n")
print("APEX V2 bell:", "ALL PASS" if not fails else fails)

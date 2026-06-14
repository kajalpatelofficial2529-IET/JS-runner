import sys
import io
import math
import re
import datetime
import random
import contextlib
from flask import Flask, request, jsonify, render_template

try:
    from pyjsparser import parse
except ImportError:
    raise ImportError("Install pyjsparser: pip install pyjsparser flask")

# ─── JS ENGINE ────────────────────────────────────────────────────────────────

class Environment:
    def __init__(self, parent=None):
        self.variables = {}
        self.parent = parent
    def set_var(self, name, value):
        self.variables[name] = value
    def get_var(self, name):
        if name in self.variables: return self.variables[name]
        if self.parent is not None: return self.parent.get_var(name)
        return None

class ReturnException(Exception):
    def __init__(self, value): self.value = value
class BreakException(Exception): pass
class ContinueException(Exception): pass

def js_str(val):
    if val is None: return "undefined"
    if isinstance(val, bool): return str(val).lower()
    if isinstance(val, float):
        if math.isnan(val): return "NaN"
        if math.isinf(val): return "Infinity" if val > 0 else "-Infinity"
        if val.is_integer(): return str(int(val))
    return str(val)

def safe_math(op, l, r):
    if op == "+" and (isinstance(l, str) or isinstance(r, str)):
        return js_str(l) + js_str(r)
    try:
        lf = float(l) if l is not None and not isinstance(l, (list, dict)) else math.nan
        rf = float(r) if r is not None and not isinstance(r, (list, dict)) else math.nan
        if op == "+": return lf + rf
        if op == "-": return lf - rf
        if op == "*": return lf * rf
        if op == "/": return lf / rf if rf != 0 else (math.inf if lf > 0 else -math.inf)
        if op == "%": return lf % rf if rf != 0 else math.nan
    except:
        return math.nan

def call_js_func(func_node, args_list, env):
    if not isinstance(func_node, dict) or "body" not in func_node: return None
    local_env = Environment(parent=env)
    for i, param in enumerate(func_node.get("params", [])):
        p_name = param.get("name")
        local_env.set_var(p_name, args_list[i] if i < len(args_list) else None)
    body = func_node.get("body")
    try:
        if isinstance(body, dict) and body.get("type") == "BlockStatement":
            evaluate(body, local_env)
        elif body:
            return evaluate(body, local_env)
    except ReturnException as ret:
        return ret.value
    return None

def evaluate(node, env):
    if not isinstance(node, dict): return None
    node_type = node.get("type")

    if node_type in ("Program", "BlockStatement"):
        res = None
        for stmt in node.get("body", []): res = evaluate(stmt, env)
        return res
    elif node_type == "EmptyStatement": return None
    elif node_type == "ExpressionStatement": return evaluate(node.get("expression"), env)
    elif node_type == "ReturnStatement": raise ReturnException(evaluate(node.get("argument"), env))
    elif node_type == "BreakStatement": raise BreakException()
    elif node_type == "ContinueStatement": raise ContinueException()

    elif node_type == "Literal": return node.get("value")
    elif node_type == "Identifier":
        name = node.get("name")
        if name in ("undefined", "null"): return None
        if name == "NaN": return math.nan
        return env.get_var(name)
    elif node_type == "VariableDeclaration":
        for decl in node.get("declarations", []):
            env.set_var(decl.get("id").get("name"), evaluate(decl.get("init"), env))
        return None

    elif node_type == "ArrayExpression":
        return [evaluate(el, env) for el in node.get("elements", [])]
    elif node_type == "ObjectExpression":
        obj = {}
        for prop in node.get("properties", []):
            k_node = prop.get("key")
            k = k_node.get("name") if k_node.get("type") == "Identifier" else k_node.get("value")
            obj[k] = evaluate(prop.get("value"), env)
        return obj
    elif node_type == "MemberExpression":
        obj = evaluate(node.get("object"), env)
        prop = evaluate(node.get("property"), env) if node.get("computed") else node.get("property").get("name")
        if isinstance(obj, (list, str)) and prop == "length": return len(obj)
        try:
            if isinstance(obj, (list, str)) and str(prop).lstrip('-').isdigit(): return obj[int(prop)]
            if isinstance(obj, dict): return obj.get(prop)
        except: pass
        return None

    elif node_type == "AssignmentExpression":
        left = node.get("left")
        op = node.get("operator")
        r_val = evaluate(node.get("right"), env)
        if left.get("type") == "Identifier":
            v_name = left.get("name")
            if op == "=": env.set_var(v_name, r_val)
            else: env.set_var(v_name, safe_math(op[0], env.get_var(v_name), r_val))
            return env.get_var(v_name)
        elif left.get("type") == "MemberExpression":
            obj = evaluate(left.get("object"), env)
            prop = evaluate(left.get("property"), env) if left.get("computed") else left.get("property").get("name")
            if isinstance(obj, (list, dict)):
                idx = int(prop) if isinstance(obj, list) else prop
                if op == "=": obj[idx] = r_val
                else: obj[idx] = safe_math(op[0], obj.get(idx, 0), r_val)
                return obj[idx]

    elif node_type == "UpdateExpression":
        var_name = node.get("argument").get("name")
        op = node.get("operator")
        cur = env.get_var(var_name)
        cur_val = float(cur) if cur is not None else 0
        new_val = cur_val + 1 if op == "++" else cur_val - 1
        env.set_var(var_name, new_val)
        return new_val if node.get("prefix") else cur_val

    elif node_type == "UnaryExpression":
        op = node.get("operator")
        arg = evaluate(node.get("argument"), env)
        if op == "!": return not arg
        if op == "-":
            try: return -float(arg)
            except: return math.nan
        if op == "typeof":
            if arg is None: return "undefined"
            if isinstance(arg, bool): return "boolean"
            if isinstance(arg, (int, float)): return "number"
            if isinstance(arg, str): return "string"
            return "object"

    elif node_type == "LogicalExpression":
        l = evaluate(node.get("left"), env)
        op = node.get("operator")
        if op == "&&": return l and evaluate(node.get("right"), env)
        if op == "||": return l or evaluate(node.get("right"), env)

    elif node_type == "ConditionalExpression":
        return evaluate(node.get("consequent"), env) if evaluate(node.get("test"), env) else evaluate(node.get("alternate"), env)

    elif node_type == "BinaryExpression":
        l = evaluate(node.get("left"), env)
        r = evaluate(node.get("right"), env)
        op = node.get("operator")
        if op in ("+", "-", "*", "/", "%"): return safe_math(op, l, r)
        if op == "in": return l in r if isinstance(r, (list, dict, str)) else False
        if op == "===": return type(l) == type(r) and l == r
        if op == "!==": return type(l) != type(r) or l != r
        if op == "==": return str(l).lower() == str(r).lower() if type(l) != type(r) else l == r
        if op == "!=": return str(l).lower() != str(r).lower() if type(l) != type(r) else l != r
        try:
            if op == ">": return float(l) > float(r)
            if op == "<": return float(l) < float(r)
            if op == ">=": return float(l) >= float(r)
            if op == "<=": return float(l) <= float(r)
        except: return False

    elif node_type == "IfStatement":
        if evaluate(node.get("test"), env): return evaluate(node.get("consequent"), env)
        elif node.get("alternate"): return evaluate(node.get("alternate"), env)

    elif node_type == "SwitchStatement":
        disc = evaluate(node.get("discriminant"), env)
        matched = False
        for case in node.get("cases", []):
            if not matched and case.get("test"):
                if evaluate(case.get("test"), env) == disc: matched = True
            elif not case.get("test"): matched = True
            if matched:
                try:
                    for stmt in case.get("consequent", []): evaluate(stmt, env)
                except BreakException: break
        return None

    elif node_type == "ForStatement":
        if node.get("init"): evaluate(node.get("init"), env)
        while not node.get("test") or evaluate(node.get("test"), env):
            try: evaluate(node.get("body"), env)
            except BreakException: break
            except ContinueException: pass
            if node.get("update"): evaluate(node.get("update"), env)

    elif node_type == "WhileStatement":
        while evaluate(node.get("test"), env):
            try: evaluate(node.get("body"), env)
            except BreakException: break
            except ContinueException: pass

    elif node_type in ("FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"):
        if node.get("id"): env.set_var(node.get("id").get("name"), node)
        return node

    elif node_type == "NewExpression":
        if node.get("callee").get("name") == "Date": return datetime.datetime.now().isoformat()

    elif node_type == "CallExpression":
        callee = node.get("callee")
        args = []
        for a in node.get("arguments", []):
            ev = evaluate(a, env)
            if isinstance(ev, dict) and ev.get("__is_spread"): args.extend(ev["val"])
            else: args.append(ev)

        if callee.get("type") == "MemberExpression":
            obj_node = callee.get("object")
            prop = callee.get("property").get("name")
            if obj_node.get("type") == "Identifier" and obj_node.get("name") in ("console", "Math"):
                obj_name = obj_node.get("name")
                if obj_name == "console" and prop == "log": print(" ".join([js_str(a) for a in args]))
                elif obj_name == "Math":
                    arg0 = args[0] if len(args) > 0 else 0
                    if prop == "floor": return math.floor(float(arg0))
                    if prop == "pow": return float(arg0) ** float(args[1] if len(args) > 1 else 1)
                    if prop == "random": return random.random()
                    if prop == "max": return max(args) if args else -math.inf
                    if prop == "min": return min(args) if args else math.inf
            else:
                eval_obj = evaluate(obj_node, env)
                arg0 = args[0] if len(args) > 0 else None
                arg1 = args[1] if len(args) > 1 else None
                if isinstance(eval_obj, str):
                    if prop == "split": return list(eval_obj) if arg0 in ("", None) else eval_obj.split(js_str(arg0))
                    if prop == "replace": return eval_obj.replace(js_str(arg0), js_str(arg1), 1)
                    if prop == "replaceAll": return eval_obj.replace(js_str(arg0), js_str(arg1))
                    if prop == "substring" or prop == "slice":
                        s = int(float(arg0)) if arg0 is not None else 0
                        e = int(float(arg1)) if arg1 is not None else len(eval_obj)
                        return eval_obj[s:e]
                    if prop == "trim": return eval_obj.strip()
                    if prop == "toLowerCase": return eval_obj.lower()
                    if prop == "toUpperCase": return eval_obj.upper()
                    if prop == "includes": return js_str(arg0) in eval_obj
                    if prop == "indexOf": return eval_obj.find(js_str(arg0))
                    if prop == "startsWith": return eval_obj.startswith(js_str(arg0))
                    if prop == "endsWith": return eval_obj.endswith(js_str(arg0))
                elif isinstance(eval_obj, list):
                    if prop == "reverse": eval_obj.reverse(); return eval_obj
                    if prop == "join": return (js_str(arg0) if args else ",").join([js_str(x) for x in eval_obj])
                    if prop == "push": eval_obj.extend(args); return len(eval_obj)
                    if prop == "pop": return eval_obj.pop() if eval_obj else None
                    if prop == "shift": return eval_obj.pop(0) if eval_obj else None
                    if prop == "unshift":
                        for a in reversed(args): eval_obj.insert(0, a)
                        return len(eval_obj)
                    if prop == "slice":
                        s = int(float(arg0)) if arg0 is not None else 0
                        e = int(float(arg1)) if arg1 is not None else len(eval_obj)
                        return eval_obj[s:e]
                    if prop == "concat": return eval_obj + (arg0 if isinstance(arg0, list) else [arg0])
                    if prop == "includes": return arg0 in eval_obj
                    if prop == "indexOf": return eval_obj.index(arg0) if arg0 in eval_obj else -1
                    if prop == "sort": eval_obj.sort(); return eval_obj
                    if prop == "splice":
                        if not args: return []
                        s = int(float(arg0))
                        del_c = int(float(arg1)) if arg1 is not None else len(eval_obj) - s
                        removed = eval_obj[s:s + del_c]
                        eval_obj[s:s + del_c] = args[2:]
                        return removed
                    if prop in ("map", "filter", "reduce", "find", "some", "every"):
                        cb = arg0
                        if prop == "map": return [call_js_func(cb, [x, i, eval_obj], env) for i, x in enumerate(eval_obj)]
                        if prop == "filter": return [x for i, x in enumerate(eval_obj) if call_js_func(cb, [x, i, eval_obj], env)]
                        if prop == "some": return any(call_js_func(cb, [x, i, eval_obj], env) for i, x in enumerate(eval_obj))
                        if prop == "every": return all(call_js_func(cb, [x, i, eval_obj], env) for i, x in enumerate(eval_obj))
                        if prop == "find":
                            for i, x in enumerate(eval_obj):
                                if call_js_func(cb, [x, i, eval_obj], env): return x
                            return None
                        if prop == "reduce":
                            acc = arg1 if len(args) > 1 else eval_obj[0]
                            start = 0 if len(args) > 1 else 1
                            for i in range(start, len(eval_obj)):
                                acc = call_js_func(cb, [acc, eval_obj[i], i, eval_obj], env)
                            return acc

        elif callee.get("type") == "Identifier":
            func_name = callee.get("name")
            if func_name == "__spread_arg": return {"__is_spread": True, "val": list(args[0]) if args else []}
            if func_name == "parseInt":
                try: return int(float(args[0])) if args else math.nan
                except: return math.nan
            if func_name == "Number":
                if not args: return 0
                try: return float(args[0]) if '.' in str(args[0]) else int(args[0])
                except: return math.nan
            if func_name == "String": return js_str(args[0]) if args else ""
            func_node = env.get_var(func_name)
            return call_js_func(func_node, args, env)

def process_js_code(code):
    try:
        code = re.sub(r'\(([a-zA-Z0-9_,\s]*)\)\s*=>\s*\{', r'function(\1) {', code)
        code = re.sub(r'([a-zA-Z0-9_]+)\s*=>\s*\{', r'function(\1) {', code)
        code = re.sub(r'\(([a-zA-Z0-9_,\s]*)\)\s*=>\s*([^,;\]\)\n]+)', r'function(\1) { return \2; }', code)
        code = re.sub(r'([a-zA-Z0-9_]+)\s*=>\s*([^,;\]\)\n]+)', r'function(\1) { return \2; }', code)
        code = re.sub(r'([\w\.]+)\s*\*\*\s*([\w\.]+)', r'Math.pow(\1, \2)', code)
        code = re.sub(r'\.\.\.\s*([a-zA-Z0-9_]+)', r'__spread_arg(\1)', code)
    except: pass
    return code

# ─── FLASK APP ────────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/execute", methods=["POST"])
def execute():
    data = request.get_json(force=True)
    code = data.get("code", "")

    stdout_capture = io.StringIO()
    error_output = None

    try:
        processed = process_js_code(code)
        ast = parse(processed)
        env = Environment()
        with contextlib.redirect_stdout(stdout_capture):
            evaluate(ast, env)
    except Exception as e:
        error_output = f"Error: {type(e).__name__}: {e}"

    output = stdout_capture.getvalue()
    if error_output:
        output = (output + "\n" + error_output).strip()

    return jsonify({"output": output or "(no output)"})

if __name__ == "__main__":
    app.run(debug=True)

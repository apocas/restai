import ast
import operator
from typing import Optional


# The calculator runs UNSANDBOXED in the RESTai worker, so `**` must be bounded:
# an int base >1 with a large integer exponent (e.g. 9**9**9 → ~369M digits)
# would pin CPU and consume gigabytes computing one giant integer — a DoS
# reachable from any agent/chat/`/v1` call. Refuse when base**exp would exceed
# this many decimal digits (still allows generously large legitimate results).
_MAX_POW_RESULT_DIGITS = 5000


def _bounded_pow(base, exp):
    import math
    # Fractional exponents (roots) produce small results; just reject inf/nan.
    if isinstance(exp, float) and not exp.is_integer():
        if math.isinf(exp) or math.isnan(exp):
            raise ValueError("Invalid exponent")
        return operator.pow(base, exp)
    base_abs = abs(base)
    exp_i = abs(int(exp))
    # base==1/0 and |base|<1 can't blow up an integer; only |base|>1 with a
    # positive exponent grows. Estimate digits = exp * log10(|base|); the mul
    # itself overflows float for astronomically large operands → also "too large".
    if base_abs > 1 and exp_i > 0:
        try:
            digits = exp_i * math.log10(base_abs)
        except OverflowError:
            # base/exponent already too big to even convert to float.
            raise ValueError("Result too large")
        if digits > _MAX_POW_RESULT_DIGITS:
            raise ValueError(
                f"Result too large: ~{int(digits)} digits exceeds the {_MAX_POW_RESULT_DIGITS}-digit limit"
            )
    return operator.pow(base, exp)


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _bounded_pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        # Allow a limited set of math functions
        import math
        allowed = {"abs": abs, "round": round, "min": min, "max": max,
                   "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
                   "sin": math.sin, "cos": math.cos, "tan": math.tan,
                   "pi": math.pi, "e": math.e, "ceil": math.ceil, "floor": math.floor}
        if isinstance(node.func, ast.Name) and node.func.id in allowed:
            func = allowed[node.func.id]
            args = [_safe_eval(a) for a in node.args]
            return func(*args)
        raise ValueError(f"Function not allowed: {ast.dump(node.func)}")
    elif isinstance(node, ast.Name):
        import math
        constants = {"pi": math.pi, "e": math.e}
        if node.id in constants:
            return constants[node.id]
        raise ValueError(f"Unknown variable: {node.id}")
    else:
        raise ValueError(f"Unsupported expression: {type(node).__name__}")


def calculator(expression: str) -> str:
    """
    Safely evaluate a mathematical expression and return the result.
    Supports: +, -, *, /, //, %, ** and functions: abs, round, min, max, sqrt, log, log10, sin, cos, tan, ceil, floor.
    Constants: pi, e.

    Args:
        expression (str): The math expression to evaluate, e.g. "2 * (3 + 4)", "sqrt(144)", "round(pi * 2, 2)".
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree)
        return str(result)
    except Exception as ex:
        return f"Error: {ex}"

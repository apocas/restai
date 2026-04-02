import ast
import operator
from typing import Optional


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
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

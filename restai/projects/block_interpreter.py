"""Server-side Blockly workspace interpreter.

Walks a Blockly JSON tree and executes each block in Python. Supports the
RESTai custom blocks (Get Input, Set Output, Call Project, Classifier, Log)
plus the Blockly 12 general-purpose built-in blocks matching MIT App
Inventor's breadth (Logic, Control, Math, Text, Lists, Variables,
Procedures).

Dispatch is via two tables built in `__init__` (`_stmt_handlers`,
`_value_handlers`) keyed by the block's `type` string. Unknown types fall
back to best-effort value evaluation (for side-effect-only custom blocks)
or return `None`, matching the pre-refactor behavior.

Flow control:
- `_BlockBreak` / `_BlockContinue` propagate out of statement handlers and
  are caught by the enclosing loop handler.
- `_BlockReturn(value)` propagates out until caught by a procedure call
  handler.
"""
import inspect
import logging
import math
import random
import statistics
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10000


class _BlockBreak(Exception):
    """Raised by `controls_flow_statements(BREAK)` to exit the nearest loop."""


class _BlockContinue(Exception):
    """Raised by `controls_flow_statements(CONTINUE)` to skip to the next iteration."""


class _BlockReturn(Exception):
    """Raised by `procedures_ifreturn` to unwind to the enclosing procedure call."""

    def __init__(self, value):
        self.value = value


class BlockInterpreter:
    """Walks a Blockly workspace JSON tree and interprets each block in Python."""

    def __init__(self, workspace_json: dict, input_text: str, brain, user, db, image=None, chat_id=None, context=None):
        self.workspace = workspace_json
        self.input_text = input_text
        self.image = image
        self.output_text = ""
        self.variables: dict[str, Any] = {}
        self.brain = brain
        self.user = user
        self.db = db
        self.logs: list[str] = []
        self._iterations = 0
        self.chat_id = chat_id
        self.context = context  # Verified context dict (from widget JWT or playground)
        self._fake_request = type("_FakeRequest", (), {
            "app": type("App", (), {"state": type("State", (), {"brain": brain})()})()
        })()
        # Procedure registry: name -> {"block": def_block, "params": [{"id": ..., "name": ...}], "has_return": bool}
        self.procedures: dict[str, dict] = {}
        # Frame stack for procedure-local variables. The top frame is checked
        # first by variables_get / variables_set before falling through to
        # self.variables (globals).
        self._scope_stack: list[dict] = []

        self._stmt_handlers = {
            "variables_set": self._stmt_variables_set,
            "restai_set_output": self._stmt_set_output,
            "restai_log": self._stmt_log,
            "controls_if": self._stmt_controls_if,
            "controls_repeat_ext": self._stmt_repeat,
            "controls_whileUntil": self._stmt_while_until,
            "controls_for": self._stmt_for,
            "controls_forEach": self._stmt_for_each,
            "controls_flow_statements": self._stmt_flow,
            "text_append": self._stmt_text_append,
            "text_print": self._stmt_text_print,
            "lists_setIndex": self._stmt_lists_setIndex,
            "lists_getIndex": self._stmt_lists_getIndex_remove,
            # Procedure definitions are registered at execute() start and are
            # a no-op when encountered in the statement stream.
            "procedures_defnoreturn": self._stmt_noop,
            "procedures_defreturn": self._stmt_noop,
            "procedures_callnoreturn": self._stmt_procedures_call,
            "procedures_ifreturn": self._stmt_procedures_ifreturn,
        }

        self._value_handlers = {
            # --- Literals ---
            "text": lambda b: b.get("fields", {}).get("TEXT", ""),
            "math_number": lambda b: b.get("fields", {}).get("NUM", 0),
            "logic_boolean": lambda b: b.get("fields", {}).get("BOOL", "TRUE") == "TRUE",
            "logic_null": lambda b: None,
            "math_constant": self._eval_math_constant,
            # --- Variables ---
            "variables_get": self._eval_variables_get,
            # --- Logic ---
            "logic_compare": self._eval_logic_compare,
            "logic_operation": self._eval_logic_operation,
            "logic_negate": self._eval_logic_negate,
            "logic_ternary": self._eval_logic_ternary,
            # --- Math ---
            "math_arithmetic": self._eval_math_arithmetic,
            "math_single": self._eval_math_single,
            "math_trig": self._eval_math_trig,
            "math_number_property": self._eval_math_number_property,
            "math_round": self._eval_math_round,
            "math_on_list": self._eval_math_on_list,
            "math_modulo": self._eval_math_modulo,
            "math_constrain": self._eval_math_constrain,
            "math_random_int": self._eval_math_random_int,
            "math_random_float": self._eval_math_random_float,
            "math_atan2": self._eval_math_atan2,
            # --- Text ---
            "text_join": self._eval_text_join,
            "text_length": self._eval_text_length,
            "text_isEmpty": self._eval_text_isEmpty,
            "text_indexOf": self._eval_text_indexOf,
            "text_charAt": self._eval_text_charAt,
            "text_changeCase": self._eval_text_changeCase,
            "text_trim": self._eval_text_trim,
            "text_contains": self._eval_text_contains,
            "text_getSubstring": self._eval_text_getSubstring,
            "text_count": self._eval_text_count,
            "text_replace": self._eval_text_replace,
            "text_reverse": self._eval_text_reverse,
            # --- Lists ---
            "lists_create_with": self._eval_lists_create_with,
            "lists_create_empty": lambda b: [],
            "lists_repeat": self._eval_lists_repeat,
            "lists_length": self._eval_lists_length,
            "lists_isEmpty": self._eval_lists_isEmpty,
            "lists_indexOf": self._eval_lists_indexOf,
            "lists_getIndex": self._eval_lists_getIndex,
            "lists_getSublist": self._eval_lists_getSublist,
            "lists_split": self._eval_lists_split,
            "lists_sort": self._eval_lists_sort,
            "lists_reverse": self._eval_lists_reverse,
            # --- Procedures ---
            "procedures_callreturn": self._eval_procedures_callreturn,
            # --- RESTai custom ---
            "restai_get_input": lambda b: self.input_text,
            "restai_call_project": self._eval_call_project,
            "restai_classifier": self._eval_classifier,
        }

    def _tick(self):
        self._iterations += 1
        if self._iterations > MAX_ITERATIONS:
            raise HTTPException(
                status_code=400,
                detail="Block execution exceeded maximum iterations.",
            )

    # ------------------------------------------------------------------
    # Variable scope helpers
    # ------------------------------------------------------------------

    def _get_var(self, var_id: str) -> Any:
        """Look up a variable: top procedure frame first, then globals."""
        if self._scope_stack:
            frame = self._scope_stack[-1]
            if var_id in frame:
                return frame[var_id]
        return self.variables.get(var_id, "")

    def _set_var(self, var_id: str, value: Any) -> None:
        """Write to the top procedure frame if the var is scoped there (a
        parameter of the current procedure), else to globals."""
        if self._scope_stack:
            frame = self._scope_stack[-1]
            if var_id in frame:
                frame[var_id] = value
                return
        self.variables[var_id] = value

    # ------------------------------------------------------------------
    # Procedure registration
    # ------------------------------------------------------------------

    def _register_procedures(self):
        """Scan top-level + next-chained blocks, register every procedure def
        into `self.procedures`. Called once at the start of `execute()`."""
        def _walk(block):
            if block is None:
                return
            btype = block.get("type", "")
            if btype in ("procedures_defnoreturn", "procedures_defreturn"):
                extra = block.get("extraState", {}) or {}
                # Blockly 12 procedure def blocks carry:
                #   fields.NAME = proc name
                #   extraState.params = [{name, id}, ...]  (or 'arguments' in older versions)
                name = block.get("fields", {}).get("NAME", "") or extra.get("name", "")
                params = extra.get("params") or extra.get("arguments") or []
                # Normalise: ensure each has name + id
                norm_params = []
                for p in params:
                    if isinstance(p, dict):
                        norm_params.append({
                            "name": p.get("name", ""),
                            "id": p.get("id") or p.get("varid") or p.get("name", ""),
                        })
                if name:
                    self.procedures[name] = {
                        "block": block,
                        "params": norm_params,
                        "has_return": btype == "procedures_defreturn",
                    }
            nxt = block.get("next", {}).get("block")
            _walk(nxt)

        for block in self.workspace.get("blocks", {}).get("blocks", []):
            _walk(block)

    async def execute(self) -> str:
        blocks = self.workspace.get("blocks", {}).get("blocks", [])
        # Initialise declared variables
        for var in self.workspace.get("variables", []):
            self.variables[var["id"]] = ""
        # Pre-register procedure definitions so calls can resolve them
        # regardless of lexical order in the workspace.
        self._register_procedures()
        for block in blocks:
            try:
                await self._exec_statement(block)
            except (_BlockBreak, _BlockContinue, _BlockReturn):
                # Stray flow-control outside any loop/procedure — swallow.
                pass
        return self.output_text

    # ------------------------------------------------------------------
    # Statement execution
    # ------------------------------------------------------------------

    async def _exec_statement(self, block: dict):
        self._tick()
        btype = block.get("type", "")

        handler = self._stmt_handlers.get(btype)
        if handler is not None:
            await handler(block)
        else:
            # Unknown statement — try evaluating as a value (side-effect blocks
            # like restai_call_project can be dropped into the statement stream).
            try:
                await self._eval_value(block)
            except (_BlockBreak, _BlockContinue, _BlockReturn):
                raise
            except Exception:
                pass

        # Follow the next chain.
        nxt = block.get("next", {}).get("block")
        if nxt:
            await self._exec_statement(nxt)

    async def _stmt_noop(self, block: dict):
        """For procedure definitions: body is only executed via calls."""
        return

    async def _stmt_variables_set(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        val = await self._eval_input(block, "VALUE")
        self._set_var(var_id, val)

    async def _stmt_set_output(self, block: dict):
        val = await self._eval_input(block, "VALUE")
        self.output_text = str(val) if val is not None else ""

    async def _stmt_log(self, block: dict):
        val = await self._eval_input(block, "TEXT")
        msg = str(val) if val is not None else ""
        self.logs.append(msg)
        logger.info("Block log: %s", msg)

    async def _stmt_text_print(self, block: dict):
        # text_print behaves like restai_log for our server-side interpreter.
        val = await self._eval_input(block, "TEXT")
        msg = str(val) if val is not None else ""
        self.logs.append(msg)
        logger.info("Block print: %s", msg)

    async def _stmt_text_append(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        val = await self._eval_input(block, "TEXT")
        current = self._get_var(var_id)
        self._set_var(var_id, str(current) + (str(val) if val is not None else ""))

    async def _stmt_flow(self, block: dict):
        flow = block.get("fields", {}).get("FLOW", "BREAK")
        if flow == "CONTINUE":
            raise _BlockContinue()
        raise _BlockBreak()

    async def _stmt_controls_if(self, block: dict):
        # Blockly if/elseif/else: inputs IF0, DO0, IF1, DO1, ... ELSE
        i = 0
        executed = False
        while True:
            cond_input = block.get("inputs", {}).get(f"IF{i}")
            do_input = block.get("inputs", {}).get(f"DO{i}")
            if cond_input is None:
                break
            cond = await self._eval_value(cond_input.get("block")) if cond_input.get("block") else False
            if cond:
                if do_input and do_input.get("block"):
                    await self._exec_statement(do_input["block"])
                executed = True
                break
            i += 1

        if not executed:
            else_input = block.get("inputs", {}).get("ELSE")
            if else_input and else_input.get("block"):
                await self._exec_statement(else_input["block"])

    async def _stmt_repeat(self, block: dict):
        times = await self._eval_input(block, "TIMES")
        try:
            times = int(times)
        except (TypeError, ValueError):
            times = 0
        do_input = block.get("inputs", {}).get("DO")
        for _ in range(min(times, MAX_ITERATIONS)):
            self._tick()
            if do_input and do_input.get("block"):
                try:
                    await self._exec_statement(do_input["block"])
                except _BlockContinue:
                    continue
                except _BlockBreak:
                    break

    async def _stmt_while_until(self, block: dict):
        mode = block.get("fields", {}).get("MODE", "WHILE")
        do_input = block.get("inputs", {}).get("DO")
        for _ in range(MAX_ITERATIONS):
            self._tick()
            cond = await self._eval_input(block, "BOOL")
            if mode == "WHILE" and not cond:
                break
            if mode == "UNTIL" and cond:
                break
            if do_input and do_input.get("block"):
                try:
                    await self._exec_statement(do_input["block"])
                except _BlockContinue:
                    continue
                except _BlockBreak:
                    break

    async def _stmt_for(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        from_val = await self._eval_input(block, "FROM")
        to_val = await self._eval_input(block, "TO")
        by_val = await self._eval_input(block, "BY")
        try:
            from_val, to_val, by_val = int(from_val), int(to_val), int(by_val)
        except (TypeError, ValueError):
            return
        if by_val == 0:
            return
        do_input = block.get("inputs", {}).get("DO")
        if from_val <= to_val:
            rng = range(from_val, to_val + 1, abs(by_val))
        else:
            rng = range(from_val, to_val - 1, -abs(by_val))
        for i in rng:
            self._tick()
            self._set_var(var_id, i)
            if do_input and do_input.get("block"):
                try:
                    await self._exec_statement(do_input["block"])
                except _BlockContinue:
                    continue
                except _BlockBreak:
                    break

    async def _stmt_for_each(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return
        do_input = block.get("inputs", {}).get("DO")
        for item in lst:
            self._tick()
            self._set_var(var_id, item)
            if do_input and do_input.get("block"):
                try:
                    await self._exec_statement(do_input["block"])
                except _BlockContinue:
                    continue
                except _BlockBreak:
                    break

    async def _stmt_lists_setIndex(self, block: dict):
        """lists_setIndex: mutate the list at an index (SET or INSERT)."""
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return
        mode = block.get("fields", {}).get("MODE", "SET")
        where = block.get("fields", {}).get("WHERE", "FROM_START")
        val = await self._eval_input(block, "TO")
        at_val = None
        if where in ("FROM_START", "FROM_END"):
            at_val = await self._eval_input(block, "AT")

        idx = self._resolve_list_index(len(lst), where, at_val, for_insert=(mode == "INSERT"))
        if idx is None:
            return
        if mode == "SET":
            if 0 <= idx < len(lst):
                lst[idx] = val
        elif mode == "INSERT":
            if 0 <= idx <= len(lst):
                lst.insert(idx, val)

    async def _stmt_lists_getIndex_remove(self, block: dict):
        """lists_getIndex in statement position — only MODE=REMOVE lands here."""
        mode = block.get("fields", {}).get("MODE", "GET")
        if mode != "REMOVE":
            # GET / GET_REMOVE are values; if they appear as statements they'd be
            # a side-effect-only evaluation. Fall through silently.
            await self._eval_lists_getIndex(block)
            return
        lst = await self._eval_input(block, "VALUE")
        if not isinstance(lst, list):
            return
        where = block.get("fields", {}).get("WHERE", "FROM_START")
        at_val = None
        if where in ("FROM_START", "FROM_END"):
            at_val = await self._eval_input(block, "AT")
        idx = self._resolve_list_index(len(lst), where, at_val)
        if idx is not None and 0 <= idx < len(lst):
            del lst[idx]

    async def _stmt_procedures_call(self, block: dict):
        await self._invoke_procedure(block, want_return=False)

    async def _stmt_procedures_ifreturn(self, block: dict):
        cond = await self._eval_input(block, "CONDITION")
        if cond:
            val = await self._eval_input(block, "VALUE")
            raise _BlockReturn(val)

    # ------------------------------------------------------------------
    # Value evaluation
    # ------------------------------------------------------------------

    async def _eval_input(self, block: dict, input_name: str) -> Any:
        inp = block.get("inputs", {}).get(input_name)
        if inp and inp.get("block"):
            return await self._eval_value(inp["block"])
        # Shadow / field fallback
        if inp and inp.get("shadow"):
            return await self._eval_value(inp["shadow"])
        return None

    async def _eval_value(self, block: dict) -> Any:
        if block is None:
            return None
        self._tick()
        btype = block.get("type", "")

        handler = self._value_handlers.get(btype)
        if handler is None:
            return None

        # Handlers may be sync (lambdas for cheap literals) or async.
        result = handler(block)
        if inspect.iscoroutine(result):
            result = await result
        return result

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _eval_variables_get(self, block: dict) -> Any:
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        return self._get_var(var_id)

    # ------------------------------------------------------------------
    # Text helpers (existing + new)
    # ------------------------------------------------------------------

    async def _eval_text_join(self, block: dict) -> str:
        items = block.get("extraState", {}).get("itemCount", 0)
        parts = []
        for i in range(items):
            val = await self._eval_input(block, f"ADD{i}")
            parts.append(str(val) if val is not None else "")
        return "".join(parts)

    async def _eval_text_length(self, block: dict) -> int:
        val = await self._eval_input(block, "VALUE")
        return len(str(val)) if val is not None else 0

    async def _eval_text_isEmpty(self, block: dict) -> bool:
        val = await self._eval_input(block, "VALUE")
        return str(val).strip() == "" if val is not None else True

    async def _eval_text_contains(self, block: dict) -> bool:
        haystack = await self._eval_input(block, "VALUE")
        needle = await self._eval_input(block, "FIND")
        return str(needle) in str(haystack) if haystack is not None else False

    async def _eval_text_indexOf(self, block: dict) -> int:
        val = await self._eval_input(block, "VALUE")
        find = await self._eval_input(block, "FIND")
        end = block.get("fields", {}).get("END", "FIRST")
        s = str(val) if val is not None else ""
        f = str(find) if find is not None else ""
        if end == "FIRST":
            idx = s.find(f)
        else:
            idx = s.rfind(f)
        return idx

    async def _eval_text_charAt(self, block: dict) -> str:
        val = await self._eval_input(block, "VALUE")
        where = block.get("fields", {}).get("WHERE", "FROM_START")
        s = str(val) if val is not None else ""
        if not s:
            return ""
        if where == "FIRST":
            return s[0]
        if where == "LAST":
            return s[-1]
        if where == "FROM_START":
            at = await self._eval_input(block, "AT")
            try:
                return s[int(at)]
            except (TypeError, ValueError, IndexError):
                return ""
        if where == "FROM_END":
            at = await self._eval_input(block, "AT")
            try:
                return s[-(int(at) + 1)]
            except (TypeError, ValueError, IndexError):
                return ""
        if where == "RANDOM":
            return random.choice(s)
        return ""

    async def _eval_text_changeCase(self, block: dict) -> str:
        val = await self._eval_input(block, "TEXT")
        case = block.get("fields", {}).get("CASE", "UPPERCASE")
        s = str(val) if val is not None else ""
        if case == "UPPERCASE":
            return s.upper()
        if case == "LOWERCASE":
            return s.lower()
        if case == "TITLECASE":
            return s.title()
        return s

    async def _eval_text_trim(self, block: dict) -> str:
        val = await self._eval_input(block, "TEXT")
        mode = block.get("fields", {}).get("MODE", "BOTH")
        s = str(val) if val is not None else ""
        if mode == "LEFT":
            return s.lstrip()
        if mode == "RIGHT":
            return s.rstrip()
        return s.strip()

    async def _eval_text_getSubstring(self, block: dict) -> str:
        val = await self._eval_input(block, "STRING")
        s = str(val) if val is not None else ""
        where1 = block.get("fields", {}).get("WHERE1", "FROM_START")
        where2 = block.get("fields", {}).get("WHERE2", "FROM_START")
        at1 = None
        at2 = None
        if where1 in ("FROM_START", "FROM_END"):
            at1 = await self._eval_input(block, "AT1")
        if where2 in ("FROM_START", "FROM_END"):
            at2 = await self._eval_input(block, "AT2")
        start = self._resolve_sequence_slice(len(s), where1, at1, end=False)
        end = self._resolve_sequence_slice(len(s), where2, at2, end=True)
        if start is None or end is None or start > end:
            return ""
        return s[start:end]

    async def _eval_text_count(self, block: dict) -> int:
        sub = await self._eval_input(block, "SUB")
        txt = await self._eval_input(block, "TEXT")
        sub = str(sub) if sub is not None else ""
        txt = str(txt) if txt is not None else ""
        if not sub:
            return 0
        return txt.count(sub)

    async def _eval_text_replace(self, block: dict) -> str:
        find = await self._eval_input(block, "FROM")
        to = await self._eval_input(block, "TO")
        txt = await self._eval_input(block, "TEXT")
        find = str(find) if find is not None else ""
        to = str(to) if to is not None else ""
        txt = str(txt) if txt is not None else ""
        if not find:
            return txt
        return txt.replace(find, to)

    async def _eval_text_reverse(self, block: dict) -> str:
        val = await self._eval_input(block, "TEXT")
        s = str(val) if val is not None else ""
        return s[::-1]

    # ------------------------------------------------------------------
    # Math helpers (existing + new)
    # ------------------------------------------------------------------

    async def _eval_math_arithmetic(self, block: dict):
        a = await self._eval_input(block, "A")
        b = await self._eval_input(block, "B")
        op = block.get("fields", {}).get("OP", "ADD")
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return 0
        if op == "ADD":
            return a + b
        if op == "MINUS":
            return a - b
        if op == "MULTIPLY":
            return a * b
        if op == "DIVIDE":
            return a / b if b != 0 else 0
        if op == "POWER":
            return a**b
        return 0

    async def _eval_math_single(self, block: dict):
        val = await self._eval_input(block, "NUM")
        op = block.get("fields", {}).get("OP", "ROOT")
        try:
            n = float(val)
        except (TypeError, ValueError):
            return 0
        try:
            if op == "ROOT":
                return math.sqrt(n) if n >= 0 else 0
            if op == "ABS":
                return abs(n)
            if op == "NEG":
                return -n
            if op == "LN":
                return math.log(n) if n > 0 else 0
            if op == "LOG10":
                return math.log10(n) if n > 0 else 0
            if op == "EXP":
                return math.exp(n)
            if op == "POW10":
                return 10 ** n
        except (ValueError, OverflowError):
            return 0
        return 0

    async def _eval_math_trig(self, block: dict):
        val = await self._eval_input(block, "NUM")
        op = block.get("fields", {}).get("OP", "SIN")
        try:
            n = float(val)
        except (TypeError, ValueError):
            return 0
        try:
            if op == "SIN":
                return math.sin(math.radians(n))
            if op == "COS":
                return math.cos(math.radians(n))
            if op == "TAN":
                return math.tan(math.radians(n))
            if op == "ASIN":
                return math.degrees(math.asin(n))
            if op == "ACOS":
                return math.degrees(math.acos(n))
            if op == "ATAN":
                return math.degrees(math.atan(n))
        except (ValueError, OverflowError):
            return 0
        return 0

    def _eval_math_constant(self, block: dict):
        c = block.get("fields", {}).get("CONSTANT", "PI")
        return {
            "PI": math.pi,
            "E": math.e,
            "GOLDEN_RATIO": (1 + math.sqrt(5)) / 2,
            "SQRT2": math.sqrt(2),
            "SQRT1_2": math.sqrt(0.5),
            "INFINITY": math.inf,
        }.get(c, 0)

    async def _eval_math_number_property(self, block: dict):
        val = await self._eval_input(block, "NUMBER_TO_CHECK")
        prop = block.get("fields", {}).get("PROPERTY", "EVEN")
        try:
            n = float(val)
        except (TypeError, ValueError):
            return False
        if prop == "EVEN":
            return n == int(n) and int(n) % 2 == 0
        if prop == "ODD":
            return n == int(n) and int(n) % 2 != 0
        if prop == "PRIME":
            if n != int(n) or int(n) < 2:
                return False
            ni = int(n)
            if ni == 2:
                return True
            if ni % 2 == 0:
                return False
            i = 3
            while i * i <= ni:
                if ni % i == 0:
                    return False
                i += 2
            return True
        if prop == "WHOLE":
            return n == int(n)
        if prop == "POSITIVE":
            return n > 0
        if prop == "NEGATIVE":
            return n < 0
        if prop == "DIVISIBLE_BY":
            divisor = await self._eval_input(block, "DIVISOR")
            try:
                d = float(divisor)
            except (TypeError, ValueError):
                return False
            if d == 0:
                return False
            return n % d == 0
        return False

    async def _eval_math_round(self, block: dict):
        val = await self._eval_input(block, "NUM")
        op = block.get("fields", {}).get("OP", "ROUND")
        try:
            n = float(val)
        except (TypeError, ValueError):
            return 0
        if op == "ROUND":
            return round(n)
        if op == "ROUNDUP":
            return math.ceil(n)
        if op == "ROUNDDOWN":
            return math.floor(n)
        return 0

    async def _eval_math_on_list(self, block: dict):
        lst = await self._eval_input(block, "LIST")
        op = block.get("fields", {}).get("OP", "SUM")
        if not isinstance(lst, list) or not lst:
            return 0
        try:
            nums = [float(x) for x in lst]
        except (TypeError, ValueError):
            nums = []
        try:
            if op == "SUM":
                return sum(nums)
            if op == "MIN":
                return min(nums) if nums else 0
            if op == "MAX":
                return max(nums) if nums else 0
            if op == "AVERAGE":
                return statistics.mean(nums) if nums else 0
            if op == "MEDIAN":
                return statistics.median(nums) if nums else 0
            if op == "MODE":
                if not nums:
                    return []
                # Blockly's "mode" returns a list of all most-frequent values.
                try:
                    return statistics.multimode(nums)
                except AttributeError:  # Python <3.8 fallback
                    return [statistics.mode(nums)]
            if op == "STD_DEV":
                return statistics.pstdev(nums) if len(nums) > 0 else 0
            if op == "RANDOM":
                return random.choice(lst)
        except statistics.StatisticsError:
            return 0
        return 0

    async def _eval_math_modulo(self, block: dict):
        a = await self._eval_input(block, "DIVIDEND")
        b = await self._eval_input(block, "DIVISOR")
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return 0
        if b == 0:
            return 0
        return a % b

    async def _eval_math_constrain(self, block: dict):
        val = await self._eval_input(block, "VALUE")
        lo = await self._eval_input(block, "LOW")
        hi = await self._eval_input(block, "HIGH")
        try:
            v, lo, hi = float(val), float(lo), float(hi)
        except (TypeError, ValueError):
            return 0
        return max(lo, min(hi, v))

    async def _eval_math_random_int(self, block: dict):
        lo = await self._eval_input(block, "FROM")
        hi = await self._eval_input(block, "TO")
        try:
            lo, hi = int(lo), int(hi)
        except (TypeError, ValueError):
            return 0
        if lo > hi:
            lo, hi = hi, lo
        return random.randint(lo, hi)

    def _eval_math_random_float(self, block: dict):
        return random.random()

    async def _eval_math_atan2(self, block: dict):
        x = await self._eval_input(block, "X")
        y = await self._eval_input(block, "Y")
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            return 0
        return math.degrees(math.atan2(y, x))

    # ------------------------------------------------------------------
    # Logic helpers (existing + new)
    # ------------------------------------------------------------------

    async def _eval_logic_compare(self, block: dict):
        a = await self._eval_input(block, "A")
        b = await self._eval_input(block, "B")
        op = block.get("fields", {}).get("OP", "EQ")
        if op == "EQ":
            return a == b
        if op == "NEQ":
            return a != b
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return False
        if op == "LT":
            return a < b
        if op == "LTE":
            return a <= b
        if op == "GT":
            return a > b
        if op == "GTE":
            return a >= b
        return False

    async def _eval_logic_operation(self, block: dict):
        op = block.get("fields", {}).get("OP", "AND")
        a = await self._eval_input(block, "A")
        if op == "AND" and not a:
            return False
        if op == "OR" and a:
            return True
        b = await self._eval_input(block, "B")
        if op == "AND":
            return bool(a) and bool(b)
        if op == "OR":
            return bool(b)
        return False

    async def _eval_logic_negate(self, block: dict):
        val = await self._eval_input(block, "BOOL")
        return not val

    async def _eval_logic_ternary(self, block: dict):
        cond = await self._eval_input(block, "IF")
        if cond:
            return await self._eval_input(block, "THEN")
        return await self._eval_input(block, "ELSE")

    # ------------------------------------------------------------------
    # List helpers
    # ------------------------------------------------------------------

    async def _eval_lists_create_with(self, block: dict) -> list:
        count = block.get("extraState", {}).get("itemCount", 0)
        result = []
        for i in range(count):
            result.append(await self._eval_input(block, f"ADD{i}"))
        return result

    async def _eval_lists_repeat(self, block: dict) -> list:
        item = await self._eval_input(block, "ITEM")
        num = await self._eval_input(block, "NUM")
        try:
            n = int(num)
        except (TypeError, ValueError):
            n = 0
        return [item] * max(0, min(n, MAX_ITERATIONS))

    async def _eval_lists_length(self, block: dict) -> int:
        val = await self._eval_input(block, "VALUE")
        if isinstance(val, (list, str)):
            return len(val)
        return 0

    async def _eval_lists_isEmpty(self, block: dict) -> bool:
        val = await self._eval_input(block, "VALUE")
        if isinstance(val, (list, str)):
            return len(val) == 0
        return True

    async def _eval_lists_indexOf(self, block: dict) -> int:
        lst = await self._eval_input(block, "VALUE")
        find = await self._eval_input(block, "FIND")
        end = block.get("fields", {}).get("END", "FIRST")
        if not isinstance(lst, list):
            return 0
        try:
            if end == "FIRST":
                return lst.index(find) + 1
            # LAST
            for i in range(len(lst) - 1, -1, -1):
                if lst[i] == find:
                    return i + 1
            return 0
        except ValueError:
            return 0

    async def _eval_lists_getIndex(self, block: dict):
        mode = block.get("fields", {}).get("MODE", "GET")
        where = block.get("fields", {}).get("WHERE", "FROM_START")
        lst = await self._eval_input(block, "VALUE")
        if not isinstance(lst, list):
            return None
        at_val = None
        if where in ("FROM_START", "FROM_END"):
            at_val = await self._eval_input(block, "AT")
        idx = self._resolve_list_index(len(lst), where, at_val)
        if idx is None or not (0 <= idx < len(lst)):
            return None
        if mode == "GET":
            return lst[idx]
        if mode == "GET_REMOVE":
            return lst.pop(idx)
        if mode == "REMOVE":
            # Typically a statement but return None if used as value
            del lst[idx]
            return None
        return lst[idx]

    async def _eval_lists_getSublist(self, block: dict) -> list:
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return []
        where1 = block.get("fields", {}).get("WHERE1", "FROM_START")
        where2 = block.get("fields", {}).get("WHERE2", "FROM_START")
        at1 = None
        at2 = None
        if where1 in ("FROM_START", "FROM_END"):
            at1 = await self._eval_input(block, "AT1")
        if where2 in ("FROM_START", "FROM_END"):
            at2 = await self._eval_input(block, "AT2")
        start = self._resolve_sequence_slice(len(lst), where1, at1, end=False)
        end = self._resolve_sequence_slice(len(lst), where2, at2, end=True)
        if start is None or end is None or start > end:
            return []
        return list(lst[start:end])

    async def _eval_lists_split(self, block: dict):
        mode = block.get("fields", {}).get("MODE", "SPLIT")
        delim = await self._eval_input(block, "DELIM")
        delim = str(delim) if delim is not None else ""
        inp = await self._eval_input(block, "INPUT")
        if mode == "SPLIT":
            s = str(inp) if inp is not None else ""
            if not delim:
                return list(s)
            return s.split(delim)
        # JOIN
        if not isinstance(inp, list):
            inp = [inp] if inp is not None else []
        return delim.join(str(x) for x in inp)

    async def _eval_lists_sort(self, block: dict) -> list:
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return []
        type_ = block.get("fields", {}).get("TYPE", "NUMERIC")
        direction = block.get("fields", {}).get("DIRECTION", "1")
        reverse = str(direction) == "-1"

        if type_ == "NUMERIC":
            def key(x):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return float("inf")
        elif type_ == "IGNORE_CASE":
            def key(x):
                return str(x).lower()
        else:  # TEXT
            def key(x):
                return str(x)
        try:
            return sorted(list(lst), key=key, reverse=reverse)
        except TypeError:
            return list(lst)

    async def _eval_lists_reverse(self, block: dict) -> list:
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return []
        return list(reversed(lst))

    # ------------------------------------------------------------------
    # Sequence index resolution (1-based Blockly semantics → 0-based Python)
    # ------------------------------------------------------------------

    def _resolve_list_index(self, length: int, where: str, at_val, for_insert: bool = False):
        """Return a 0-based Python index matching Blockly's semantics.

        - FROM_START: 1 → 0, 2 → 1, ...
        - FROM_END: 1 → length-1, 2 → length-2, ...
        - FIRST: 0
        - LAST: length-1 (for insert: length)
        - RANDOM: random valid index, or None on empty list
        """
        if where == "FIRST":
            return 0
        if where == "LAST":
            if for_insert:
                return length
            return length - 1 if length > 0 else None
        if where == "RANDOM":
            if length == 0:
                return None
            return random.randint(0, length - 1)
        try:
            at = int(at_val)
        except (TypeError, ValueError):
            return None
        if where == "FROM_START":
            return at - 1
        if where == "FROM_END":
            return length - at
        return None

    def _resolve_sequence_slice(self, length: int, where: str, at_val, end: bool):
        """Return a 0-based Python slice bound for Blockly's 1-based substring/sublist.

        Used by `text_getSubstring` and `lists_getSublist`. `end=True` means we
        want the exclusive upper bound (so a LAST/FROM_END position should be
        inclusive on the right side — we add 1).
        """
        if where == "FIRST":
            return 0 if not end else (1 if length > 0 else 0)
        if where == "LAST":
            return length
        try:
            at = int(at_val)
        except (TypeError, ValueError):
            return None
        if where == "FROM_START":
            # 1-based start (WHERE1) or inclusive end (WHERE2)
            return (at - 1) if not end else at
        if where == "FROM_END":
            return (length - at) if not end else (length - at + 1)
        return None

    # ------------------------------------------------------------------
    # Procedures
    # ------------------------------------------------------------------

    async def _invoke_procedure(self, call_block: dict, want_return: bool):
        extra = call_block.get("extraState", {}) or {}
        name = extra.get("name") or call_block.get("fields", {}).get("NAME", "")
        proc = self.procedures.get(name)
        if proc is None:
            logger.warning("Procedure '%s' not found", name)
            return None

        # Collect arg values: call block inputs are ARG0, ARG1, ... in the
        # order of the def's params.
        params = proc["params"]
        frame: dict = {}
        for i, p in enumerate(params):
            arg_val = await self._eval_input(call_block, f"ARG{i}")
            frame[p["id"]] = arg_val

        self._scope_stack.append(frame)
        try:
            # Execute body statements (STACK input on the def block).
            stack_input = proc["block"].get("inputs", {}).get("STACK")
            if stack_input and stack_input.get("block"):
                try:
                    await self._exec_statement(stack_input["block"])
                except _BlockReturn as e:
                    return e.value if want_return else None

            if want_return:
                # Evaluate the RETURN input after a clean body fall-through.
                return await self._eval_input(proc["block"], "RETURN")
            return None
        finally:
            self._scope_stack.pop()

    async def _eval_procedures_callreturn(self, block: dict):
        return await self._invoke_procedure(block, want_return=True)

    # ------------------------------------------------------------------
    # RESTai custom blocks
    # ------------------------------------------------------------------

    async def _eval_call_project(self, block: dict) -> str:
        project_name = block.get("fields", {}).get("PROJECT_NAME", "")
        text = await self._eval_input(block, "TEXT")
        if not project_name:
            return ""

        project_db = self.db.get_project_by_name(project_name)
        if project_db is None:
            logger.warning("Call Project: project '%s' not found", project_name)
            return ""

        project = self.brain.find_project(project_db.id, self.db)
        if project is None:
            logger.warning("Call Project: project '%s' could not be loaded", project_name)
            return ""

        # Propagate context to the sub-project's system prompt
        if self.context:
            project = project.with_context(self.context)

        from fastapi import BackgroundTasks
        background_tasks = BackgroundTasks()

        try:
            if self.chat_id:
                from restai.models.models import ChatModel
                from restai.helper import chat_main
                q = ChatModel(question=str(text) if text else "", id=self.chat_id, image=self.image)
                result = await chat_main(
                    self._fake_request, self.brain, project, q,
                    self.user, self.db, background_tasks,
                )
            else:
                from restai.models.models import QuestionModel
                from restai.helper import question_main
                q = QuestionModel(question=str(text) if text else "", image=self.image)
                result = await question_main(
                    self._fake_request, self.brain, project, q,
                    self.user, self.db, background_tasks,
                )

            # Execute queued background tasks (inference logging) since we're
            # not inside a FastAPI response lifecycle that would run them.
            for task in background_tasks.tasks:
                try:
                    if inspect.iscoroutinefunction(task.func):
                        await task.func(*task.args, **task.kwargs)
                    else:
                        task.func(*task.args, **task.kwargs)
                except Exception:
                    pass

            if isinstance(result, dict):
                return result.get("answer", "")
            return str(result)
        except Exception as e:
            logger.exception("Call Project '%s' failed: %s", project_name, e)
            return ""

    async def _eval_classifier(self, block: dict) -> str:
        text = await self._eval_input(block, "TEXT")
        labels_raw = await self._eval_input(block, "LABELS")
        if not text or not labels_raw:
            return ""

        labels = [l.strip() for l in str(labels_raw).split(",") if l.strip()]
        if not labels:
            return ""

        model = block.get("fields", {}).get("MODEL")

        try:
            from restai.models.models import ClassifierModel

            classifier_input = ClassifierModel(sequence=str(text), labels=labels, model=model)
            result = self.brain.classify(classifier_input)

            if isinstance(result, dict) and result.get("labels"):
                return result["labels"][0]
            if hasattr(result, "labels") and result.labels:
                return result.labels[0]
            return str(result)
        except Exception as e:
            logger.exception("Classifier block failed: %s", e)
            return ""

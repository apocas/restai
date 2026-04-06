import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10000


class BlockInterpreter:
    """Walks a Blockly workspace JSON tree and interprets each block in Python."""

    def __init__(self, workspace_json: dict, input_text: str, brain, user, db, image=None):
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

    def _tick(self):
        self._iterations += 1
        if self._iterations > MAX_ITERATIONS:
            raise HTTPException(
                status_code=400,
                detail="Block execution exceeded maximum iterations.",
            )

    async def execute(self) -> str:
        blocks = self.workspace.get("blocks", {}).get("blocks", [])
        # Initialise declared variables
        for var in self.workspace.get("variables", []):
            self.variables[var["id"]] = ""
        for block in blocks:
            await self._exec_statement(block)
        return self.output_text

    # ------------------------------------------------------------------
    # Statement execution
    # ------------------------------------------------------------------

    async def _exec_statement(self, block: dict):
        self._tick()
        btype = block.get("type", "")

        if btype == "variables_set":
            await self._stmt_variables_set(block)
        elif btype == "restai_set_output":
            await self._stmt_set_output(block)
        elif btype == "restai_log":
            await self._stmt_log(block)
        elif btype == "controls_if":
            await self._stmt_controls_if(block)
        elif btype == "controls_repeat_ext":
            await self._stmt_repeat(block)
        elif btype == "controls_whileUntil":
            await self._stmt_while_until(block)
        elif btype == "controls_for":
            await self._stmt_for(block)
        elif btype == "controls_forEach":
            await self._stmt_for_each(block)
        else:
            # Unknown statement – try evaluating as a value (side-effects)
            try:
                await self._eval_value(block)
            except Exception:
                pass

        # Follow the next chain
        nxt = block.get("next", {}).get("block")
        if nxt:
            await self._exec_statement(nxt)

    async def _stmt_variables_set(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        val = await self._eval_input(block, "VALUE")
        self.variables[var_id] = val

    async def _stmt_set_output(self, block: dict):
        val = await self._eval_input(block, "VALUE")
        self.output_text = str(val) if val is not None else ""

    async def _stmt_log(self, block: dict):
        val = await self._eval_input(block, "TEXT")
        msg = str(val) if val is not None else ""
        self.logs.append(msg)
        logger.info("Block log: %s", msg)

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
                await self._exec_statement(do_input["block"])

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
                await self._exec_statement(do_input["block"])

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
            self.variables[var_id] = i
            if do_input and do_input.get("block"):
                await self._exec_statement(do_input["block"])

    async def _stmt_for_each(self, block: dict):
        var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
        lst = await self._eval_input(block, "LIST")
        if not isinstance(lst, list):
            return
        do_input = block.get("inputs", {}).get("DO")
        for item in lst:
            self._tick()
            self.variables[var_id] = item
            if do_input and do_input.get("block"):
                await self._exec_statement(do_input["block"])

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

        # --- Literals ---
        if btype == "text":
            return block.get("fields", {}).get("TEXT", "")
        if btype == "math_number":
            return block.get("fields", {}).get("NUM", 0)
        if btype == "logic_boolean":
            return block.get("fields", {}).get("BOOL", "TRUE") == "TRUE"

        # --- Variables ---
        if btype == "variables_get":
            var_id = block.get("fields", {}).get("VAR", {}).get("id", "")
            return self.variables.get(var_id, "")

        # --- Text ---
        if btype == "text_join":
            return await self._eval_text_join(block)
        if btype == "text_length":
            val = await self._eval_input(block, "VALUE")
            return len(str(val)) if val is not None else 0
        if btype == "text_isEmpty":
            val = await self._eval_input(block, "VALUE")
            return str(val).strip() == "" if val is not None else True
        if btype == "text_indexOf":
            return await self._eval_text_indexOf(block)
        if btype == "text_charAt":
            return await self._eval_text_charAt(block)
        if btype == "text_changeCase":
            return await self._eval_text_changeCase(block)
        if btype == "text_trim":
            return await self._eval_text_trim(block)
        if btype == "text_contains":
            haystack = await self._eval_input(block, "VALUE")
            needle = await self._eval_input(block, "FIND")
            return str(needle) in str(haystack) if haystack is not None else False

        # --- Math ---
        if btype == "math_arithmetic":
            return await self._eval_math_arithmetic(block)

        # --- Logic ---
        if btype == "logic_compare":
            return await self._eval_logic_compare(block)
        if btype == "logic_operation":
            return await self._eval_logic_operation(block)
        if btype == "logic_negate":
            val = await self._eval_input(block, "BOOL")
            return not val

        # --- RESTai custom ---
        if btype == "restai_get_input":
            return self.input_text
        if btype == "restai_call_project":
            return await self._eval_call_project(block)
        if btype == "restai_classifier":
            return await self._eval_classifier(block)

        return None

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    async def _eval_text_join(self, block: dict) -> str:
        items = block.get("extraState", {}).get("itemCount", 0)
        parts = []
        for i in range(items):
            val = await self._eval_input(block, f"ADD{i}")
            parts.append(str(val) if val is not None else "")
        return "".join(parts)

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
            import random
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

    # ------------------------------------------------------------------
    # Math helpers
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

    # ------------------------------------------------------------------
    # Logic helpers
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
        a = await self._eval_input(block, "A")
        b = await self._eval_input(block, "B")
        op = block.get("fields", {}).get("OP", "AND")
        if op == "AND":
            return bool(a) and bool(b)
        if op == "OR":
            return bool(a) or bool(b)
        return False

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

        from restai.models.models import QuestionModel
        from restai.helper import question_main
        from fastapi import BackgroundTasks, Request

        q = QuestionModel(question=str(text) if text else "", image=self.image)
        background_tasks = BackgroundTasks()

        # Create a minimal request-like object
        class _FakeRequest:
            app = type("App", (), {"state": type("State", (), {"brain": self.brain})()})()

        try:
            result = await question_main(
                _FakeRequest(),
                self.brain,
                project,
                q,
                self.user,
                self.db,
                background_tasks,
            )
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

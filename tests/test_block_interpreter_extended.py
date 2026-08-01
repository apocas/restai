"""Extended unit tests for the Blockly workspace interpreter.

Complements tests/test_block_interpreter.py — covers the block handlers,
flow-control paths, error paths and the brain/db-wired blocks
(restai_call_project / restai_classifier) that the base file leaves out.
Same fixture style: hand-crafted workspace JSON, no HTTP required.
"""
import asyncio
import math
import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from restai.projects.block_interpreter import (
    MAX_ITERATIONS,
    BlockInterpreter,
    _fmt_value,
)


def _interp(workspace, input_text="hello", brain=None, user=None, db=None):
    return BlockInterpreter(
        workspace_json=workspace,
        input_text=input_text,
        brain=brain,
        user=user,
        db=db,
    )


def _run(workspace, input_text="hello", **kw):
    return asyncio.run(_interp(workspace, input_text, **kw).execute())


def _set_output(value_block):
    return {
        "blocks": {
            "blocks": [
                {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": value_block}},
                }
            ]
        },
        "variables": [],
    }


def _num(n):
    return {"type": "math_number", "fields": {"NUM": n}}


def _text(s):
    return {"type": "text", "fields": {"TEXT": s}}


def _bool(b):
    return {"type": "logic_boolean", "fields": {"BOOL": "TRUE" if b else "FALSE"}}


def _list(*items):
    return {
        "type": "lists_create_with",
        "extraState": {"itemCount": len(items)},
        "inputs": {f"ADD{i}": {"block": item} for i, item in enumerate(items)},
    }


def _var_get(var_id):
    return {"type": "variables_get", "fields": {"VAR": {"id": var_id}}}


def _join_list(list_block, delim=","):
    return {
        "type": "lists_split",
        "fields": {"MODE": "JOIN"},
        "inputs": {
            "INPUT": {"block": list_block},
            "DELIM": {"block": _text(delim)},
        },
    }


# ─── _fmt_value ─────────────────────────────────────────────────────────

def test_fmt_value_whole_float():
    assert _fmt_value(5.0) == "5"


def test_fmt_value_fractional_float():
    assert _fmt_value(2.5) == "2.5"


def test_fmt_value_none_is_empty():
    assert _fmt_value(None) == ""


def test_fmt_value_string_passthrough():
    assert _fmt_value("abc") == "abc"


# ─── Basic I/O blocks ───────────────────────────────────────────────────

def test_restai_get_input():
    workspace = _set_output({"type": "restai_get_input"})
    assert _run(workspace, input_text="the input") == "the input"


def test_restai_log_appends_to_logs():
    workspace = {
        "blocks": {"blocks": [{
            "type": "restai_log",
            "inputs": {"TEXT": {"block": _text("logged!")}},
        }]},
        "variables": [],
    }
    interp = _interp(workspace)
    asyncio.run(interp.execute())
    assert interp.logs == ["logged!"]


def test_text_print_appends_to_logs():
    workspace = {
        "blocks": {"blocks": [{
            "type": "text_print",
            "inputs": {"TEXT": {"block": _num(3.0)}},
        }]},
        "variables": [],
    }
    interp = _interp(workspace)
    asyncio.run(interp.execute())
    assert interp.logs == ["3"]


def test_unknown_value_block_yields_empty_output():
    workspace = _set_output({"type": "some_unknown_block"})
    assert _run(workspace) == ""


def test_unknown_statement_block_is_tolerated():
    workspace = {
        "blocks": {"blocks": [
            {"type": "totally_bogus_statement",
             "next": {"block": {
                 "type": "restai_set_output",
                 "inputs": {"VALUE": {"block": _text("still ran")}},
             }}},
        ]},
        "variables": [],
    }
    assert _run(workspace) == "still ran"


def test_stray_break_at_top_level_does_not_stop_other_blocks():
    workspace = {
        "blocks": {"blocks": [
            {"type": "controls_flow_statements", "fields": {"FLOW": "BREAK"}},
            {"type": "restai_set_output",
             "inputs": {"VALUE": {"block": _text("ok")}}},
        ]},
        "variables": [],
    }
    assert _run(workspace) == "ok"


def test_variables_initialized_empty_and_unknown_var_empty():
    workspace = {
        "blocks": {"blocks": [{
            "type": "restai_set_output",
            "inputs": {"VALUE": {"block": _var_get("never_set")}},
        }]},
        "variables": [{"id": "V", "name": "v"}],
    }
    interp = _interp(workspace)
    out = asyncio.run(interp.execute())
    assert out == ""
    assert interp.variables["V"] == ""


# ─── Text blocks ────────────────────────────────────────────────────────

def test_text_join():
    workspace = _set_output({
        "type": "text_join",
        "extraState": {"itemCount": 3},
        "inputs": {
            "ADD0": {"block": _text("a")},
            "ADD1": {"block": _num(2.0)},
            "ADD2": {"block": _text("c")},
        },
    })
    assert _run(workspace) == "a2c"


def test_text_length():
    workspace = _set_output({
        "type": "text_length",
        "inputs": {"VALUE": {"block": _text("hello")}},
    })
    assert _run(workspace) == "5"


def test_text_isEmpty_whitespace_true():
    workspace = _set_output({
        "type": "text_isEmpty",
        "inputs": {"VALUE": {"block": _text("   ")}},
    })
    assert _run(workspace) == "True"


def test_text_isEmpty_missing_input_true():
    workspace = _set_output({"type": "text_isEmpty"})
    assert _run(workspace) == "True"


def test_text_indexOf_first_and_last():
    first = _set_output({
        "type": "text_indexOf",
        "fields": {"END": "FIRST"},
        "inputs": {
            "VALUE": {"block": _text("banana")},
            "FIND": {"block": _text("a")},
        },
    })
    assert _run(first) == "1"
    last = _set_output({
        "type": "text_indexOf",
        "fields": {"END": "LAST"},
        "inputs": {
            "VALUE": {"block": _text("banana")},
            "FIND": {"block": _text("a")},
        },
    })
    assert _run(last) == "5"


@pytest.mark.parametrize("where,at,expected", [
    ("FIRST", None, "h"),
    ("LAST", None, "o"),
    ("FROM_START", 2, "e"),
    ("FROM_END", 1, "o"),
])
def test_text_charAt(where, at, expected):
    block = {
        "type": "text_charAt",
        "fields": {"WHERE": where},
        "inputs": {"VALUE": {"block": _text("hello")}},
    }
    if at is not None:
        block["inputs"]["AT"] = {"block": _num(at)}
    assert _run(_set_output(block)) == expected


def test_text_charAt_empty_string():
    workspace = _set_output({
        "type": "text_charAt",
        "fields": {"WHERE": "FIRST"},
        "inputs": {"VALUE": {"block": _text("")}},
    })
    assert _run(workspace) == ""


@pytest.mark.parametrize("case,expected", [
    ("UPPERCASE", "HELLO WORLD"),
    ("LOWERCASE", "hello world"),
    ("TITLECASE", "Hello World"),
])
def test_text_changeCase(case, expected):
    workspace = _set_output({
        "type": "text_changeCase",
        "fields": {"CASE": case},
        "inputs": {"TEXT": {"block": _text("hello WORLD")}},
    })
    assert _run(workspace) == expected


@pytest.mark.parametrize("mode,expected", [
    ("LEFT", "x  "),
    ("RIGHT", "  x"),
    ("BOTH", "x"),
])
def test_text_trim(mode, expected):
    workspace = _set_output({
        "type": "text_trim",
        "fields": {"MODE": mode},
        "inputs": {"TEXT": {"block": _text("  x  ")}},
    })
    assert _run(workspace) == expected


def test_text_contains_true_false():
    def contains(hay, needle):
        return _run(_set_output({
            "type": "text_contains",
            "inputs": {
                "VALUE": {"block": _text(hay)},
                "FIND": {"block": _text(needle)},
            },
        }))
    assert contains("hello world", "world") == "True"
    assert contains("hello world", "zebra") == "False"


def test_text_replace_empty_find_is_noop():
    workspace = _set_output({
        "type": "text_replace",
        "inputs": {
            "FROM": {"block": _text("")},
            "TO": {"block": _text("X")},
            "TEXT": {"block": _text("abc")},
        },
    })
    assert _run(workspace) == "abc"


def test_text_count_empty_sub_is_zero():
    workspace = _set_output({
        "type": "text_count",
        "inputs": {
            "SUB": {"block": _text("")},
            "TEXT": {"block": _text("abc")},
        },
    })
    assert _run(workspace) == "0"


def test_text_getSubstring_from_end():
    workspace = _set_output({
        "type": "text_getSubstring",
        "fields": {"WHERE1": "FROM_END", "WHERE2": "LAST"},
        "inputs": {
            "STRING": {"block": _text("hello world")},
            "AT1": {"block": _num(5)},
        },
    })
    assert _run(workspace) == "world"


def test_text_getSubstring_inverted_range_empty():
    workspace = _set_output({
        "type": "text_getSubstring",
        "fields": {"WHERE1": "FROM_START", "WHERE2": "FROM_START"},
        "inputs": {
            "STRING": {"block": _text("hello")},
            "AT1": {"block": _num(4)},
            "AT2": {"block": _num(2)},
        },
    })
    assert _run(workspace) == ""


# ─── Math blocks ────────────────────────────────────────────────────────

@pytest.mark.parametrize("op,a,b,expected", [
    ("ADD", 2, 3, 5.0),
    ("MINUS", 10, 4, 6.0),
    ("MULTIPLY", 6, 7, 42.0),
    ("DIVIDE", 10, 4, 2.5),
    ("POWER", 2, 10, 1024.0),
])
def test_math_arithmetic_ops(op, a, b, expected):
    workspace = _set_output({
        "type": "math_arithmetic",
        "fields": {"OP": op},
        "inputs": {"A": {"block": _num(a)}, "B": {"block": _num(b)}},
    })
    assert float(_run(workspace)) == expected


def test_math_arithmetic_divide_by_zero_is_zero():
    workspace = _set_output({
        "type": "math_arithmetic",
        "fields": {"OP": "DIVIDE"},
        "inputs": {"A": {"block": _num(5)}, "B": {"block": _num(0)}},
    })
    assert _run(workspace) == "0"


def test_math_arithmetic_non_numeric_is_zero():
    workspace = _set_output({
        "type": "math_arithmetic",
        "fields": {"OP": "ADD"},
        "inputs": {"A": {"block": _text("abc")}, "B": {"block": _num(1)}},
    })
    assert _run(workspace) == "0"


@pytest.mark.parametrize("op,n,expected", [
    ("LN", math.e, 1.0),
    ("LOG10", 100, 2.0),
    ("EXP", 0, 1.0),
])
def test_math_single_log_exp(op, n, expected):
    workspace = _set_output({
        "type": "math_single",
        "fields": {"OP": op},
        "inputs": {"NUM": {"block": _num(n)}},
    })
    assert abs(float(_run(workspace)) - expected) < 1e-9


def test_math_single_ln_of_negative_is_zero():
    workspace = _set_output({
        "type": "math_single",
        "fields": {"OP": "LN"},
        "inputs": {"NUM": {"block": _num(-5)}},
    })
    assert _run(workspace) == "0"


def test_math_trig_asin_out_of_range_is_zero():
    workspace = _set_output({
        "type": "math_trig",
        "fields": {"OP": "ASIN"},
        "inputs": {"NUM": {"block": _num(2)}},
    })
    assert _run(workspace) == "0"


def test_math_trig_atan():
    workspace = _set_output({
        "type": "math_trig",
        "fields": {"OP": "ATAN"},
        "inputs": {"NUM": {"block": _num(1)}},
    })
    assert abs(float(_run(workspace)) - 45.0) < 1e-9


@pytest.mark.parametrize("const,expected", [
    ("E", math.e),
    ("GOLDEN_RATIO", (1 + math.sqrt(5)) / 2),
    ("SQRT2", math.sqrt(2)),
    ("SQRT1_2", math.sqrt(0.5)),
])
def test_math_constants(const, expected):
    workspace = _set_output({
        "type": "math_constant",
        "fields": {"CONSTANT": const},
    })
    assert abs(float(_run(workspace)) - expected) < 1e-12


def test_math_constant_infinity():
    workspace = _set_output({
        "type": "math_constant",
        "fields": {"CONSTANT": "INFINITY"},
    })
    assert _run(workspace) == "inf"


@pytest.mark.parametrize("prop,n,expected", [
    ("ODD", 3, "True"),
    ("ODD", 4, "False"),
    ("WHOLE", 4.0, "True"),
    ("WHOLE", 4.5, "False"),
    ("POSITIVE", 1, "True"),
    ("NEGATIVE", -1, "True"),
    ("NEGATIVE", 1, "False"),
])
def test_math_number_property(prop, n, expected):
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": prop},
        "inputs": {"NUMBER_TO_CHECK": {"block": _num(n)}},
    })
    assert _run(workspace) == expected


def test_math_number_property_divisible_by():
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": "DIVISIBLE_BY"},
        "inputs": {
            "NUMBER_TO_CHECK": {"block": _num(10)},
            "DIVISOR": {"block": _num(5)},
        },
    })
    assert _run(workspace) == "True"


def test_math_number_property_divisible_by_zero_false():
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": "DIVISIBLE_BY"},
        "inputs": {
            "NUMBER_TO_CHECK": {"block": _num(10)},
            "DIVISOR": {"block": _num(0)},
        },
    })
    assert _run(workspace) == "False"


def test_math_number_property_non_numeric_false():
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": "EVEN"},
        "inputs": {"NUMBER_TO_CHECK": {"block": _text("abc")}},
    })
    assert _run(workspace) == "False"


def test_math_round_default():
    workspace = _set_output({
        "type": "math_round",
        "fields": {"OP": "ROUND"},
        "inputs": {"NUM": {"block": _num(2.6)}},
    })
    assert _run(workspace) == "3"


@pytest.mark.parametrize("op,expected", [
    ("MEDIAN", 3.0),
    ("STD_DEV", 1.4142135623730951),
])
def test_math_on_list_median_stddev(op, expected):
    lst = _list(_num(1), _num(2), _num(3), _num(4), _num(5))
    workspace = _set_output({
        "type": "math_on_list",
        "fields": {"OP": op},
        "inputs": {"LIST": {"block": lst}},
    })
    assert abs(float(_run(workspace)) - expected) < 1e-9


def test_math_on_list_mode_returns_multimode():
    lst = _list(_num(1), _num(2), _num(2), _num(3))
    workspace = _set_output(_join_list({
        "type": "math_on_list",
        "fields": {"OP": "MODE"},
        "inputs": {"LIST": {"block": lst}},
    }))
    assert _run(workspace) == "2.0"


def test_math_on_list_non_list_is_zero():
    workspace = _set_output({
        "type": "math_on_list",
        "fields": {"OP": "SUM"},
        "inputs": {"LIST": {"block": _text("nope")}},
    })
    assert _run(workspace) == "0"


def test_math_modulo_divisor_zero_is_zero():
    workspace = _set_output({
        "type": "math_modulo",
        "inputs": {
            "DIVIDEND": {"block": _num(10)},
            "DIVISOR": {"block": _num(0)},
        },
    })
    assert _run(workspace) == "0"


def test_math_random_int_bounds_and_swap():
    # lo > hi is swapped internally; lo == hi is deterministic.
    workspace = _set_output({
        "type": "math_random_int",
        "inputs": {"FROM": {"block": _num(7)}, "TO": {"block": _num(7)}},
    })
    assert _run(workspace) == "7"
    workspace = _set_output({
        "type": "math_random_int",
        "inputs": {"FROM": {"block": _num(5)}, "TO": {"block": _num(1)}},
    })
    assert 1 <= int(_run(workspace)) <= 5


def test_math_random_float_in_unit_interval():
    workspace = _set_output({"type": "math_random_float"})
    assert 0.0 <= float(_run(workspace)) < 1.0


def test_math_atan2():
    workspace = _set_output({
        "type": "math_atan2",
        "inputs": {"X": {"block": _num(1)}, "Y": {"block": _num(1)}},
    })
    assert abs(float(_run(workspace)) - 45.0) < 1e-9


def test_math_constrain_below_low():
    workspace = _set_output({
        "type": "math_constrain",
        "inputs": {
            "VALUE": {"block": _num(-5)},
            "LOW": {"block": _num(0)},
            "HIGH": {"block": _num(10)},
        },
    })
    assert _run(workspace) == "0"


# ─── Logic blocks ───────────────────────────────────────────────────────

@pytest.mark.parametrize("op,a,b,expected", [
    ("LT", 1, 2, "True"),
    ("GT", 2, 1, "True"),
    ("NEQ", 1, 2, "True"),
    ("LT", 2, 1, "False"),
])
def test_logic_compare_ops(op, a, b, expected):
    workspace = _set_output({
        "type": "logic_compare",
        "fields": {"OP": op},
        "inputs": {"A": {"block": _num(a)}, "B": {"block": _num(b)}},
    })
    assert _run(workspace) == expected


def test_logic_compare_loose_equality_string_number():
    workspace = _set_output({
        "type": "logic_compare",
        "fields": {"OP": "EQ"},
        "inputs": {"A": {"block": _text("5")}, "B": {"block": _num(5)}},
    })
    assert _run(workspace) == "True"


def test_logic_compare_lt_non_numeric_false():
    workspace = _set_output({
        "type": "logic_compare",
        "fields": {"OP": "LT"},
        "inputs": {"A": {"block": _text("a")}, "B": {"block": _text("b")}},
    })
    assert _run(workspace) == "False"


def test_logic_operation_and_or():
    def op(kind, a, b):
        return _run(_set_output({
            "type": "logic_operation",
            "fields": {"OP": kind},
            "inputs": {"A": {"block": _bool(a)}, "B": {"block": _bool(b)}},
        }))
    assert op("AND", True, True) == "True"
    assert op("AND", True, False) == "False"
    assert op("AND", False, True) == "False"  # short-circuit
    assert op("OR", False, True) == "True"
    assert op("OR", True, False) == "True"  # short-circuit
    assert op("OR", False, False) == "False"


def test_logic_negate():
    workspace = _set_output({
        "type": "logic_negate",
        "inputs": {"BOOL": {"block": _bool(True)}},
    })
    assert _run(workspace) == "False"


# ─── List blocks ────────────────────────────────────────────────────────

def test_lists_repeat():
    workspace = _set_output(_join_list({
        "type": "lists_repeat",
        "inputs": {"ITEM": {"block": _text("x")}, "NUM": {"block": _num(3)}},
    }))
    assert _run(workspace) == "x,x,x"


def test_lists_isEmpty():
    empty = _set_output({
        "type": "lists_isEmpty",
        "inputs": {"VALUE": {"block": {"type": "lists_create_empty"}}},
    })
    assert _run(empty) == "True"
    nonlist = _set_output({
        "type": "lists_isEmpty",
        "inputs": {"VALUE": {"block": _num(3)}},
    })
    assert _run(nonlist) == "True"


def test_lists_getSublist():
    lst = _list(_text("a"), _text("b"), _text("c"), _text("d"))
    workspace = _set_output(_join_list({
        "type": "lists_getSublist",
        "fields": {"WHERE1": "FROM_START", "WHERE2": "FROM_START"},
        "inputs": {
            "LIST": {"block": lst},
            "AT1": {"block": _num(2)},
            "AT2": {"block": _num(3)},
        },
    }))
    assert _run(workspace) == "b,c"


def test_lists_getSublist_first_to_last():
    lst = _list(_text("a"), _text("b"))
    workspace = _set_output(_join_list({
        "type": "lists_getSublist",
        "fields": {"WHERE1": "FIRST", "WHERE2": "LAST"},
        "inputs": {"LIST": {"block": lst}},
    }))
    assert _run(workspace) == "a,b"


def test_lists_getIndex_from_end():
    workspace = _set_output({
        "type": "lists_getIndex",
        "fields": {"MODE": "GET", "WHERE": "FROM_END"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))},
            "AT": {"block": _num(1)},
        },
    })
    assert _run(workspace) == "c"


def test_lists_getIndex_out_of_range_none():
    workspace = _set_output({
        "type": "lists_getIndex",
        "fields": {"MODE": "GET", "WHERE": "FROM_START"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"))},
            "AT": {"block": _num(9)},
        },
    })
    assert _run(workspace) == ""


def test_lists_getIndex_remove_statement():
    """MODE=REMOVE in statement position deletes from the variable list."""
    workspace = {
        "blocks": {"blocks": [{
            "type": "variables_set",
            "fields": {"VAR": {"id": "L"}},
            "inputs": {"VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))}},
            "next": {"block": {
                "type": "lists_getIndex",
                "fields": {"MODE": "REMOVE", "WHERE": "FIRST"},
                "inputs": {"VALUE": {"block": _var_get("L")}},
                "next": {"block": {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": _join_list(_var_get("L"))}},
                }},
            }},
        }]},
        "variables": [{"id": "L", "name": "lst"}],
    }
    assert _run(workspace) == "b,c"


def test_lists_setIndex_insert_last():
    workspace = {
        "blocks": {"blocks": [{
            "type": "variables_set",
            "fields": {"VAR": {"id": "L"}},
            "inputs": {"VALUE": {"block": _list(_text("a"), _text("b"))}},
            "next": {"block": {
                "type": "lists_setIndex",
                "fields": {"MODE": "INSERT", "WHERE": "LAST"},
                "inputs": {
                    "LIST": {"block": _var_get("L")},
                    "TO": {"block": _text("z")},
                },
                "next": {"block": {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": _join_list(_var_get("L"))}},
                }},
            }},
        }]},
        "variables": [{"id": "L", "name": "lst"}],
    }
    assert _run(workspace) == "a,b,z"


def test_lists_indexOf_last():
    workspace = _set_output({
        "type": "lists_indexOf",
        "fields": {"END": "LAST"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"), _text("b"), _text("a"))},
            "FIND": {"block": _text("a")},
        },
    })
    assert _run(workspace) == "3"


def test_lists_sort_text_descending():
    lst = _list(_text("b"), _text("a"), _text("c"))
    workspace = _set_output(_join_list({
        "type": "lists_sort",
        "fields": {"TYPE": "TEXT", "DIRECTION": "-1"},
        "inputs": {"LIST": {"block": lst}},
    }))
    assert _run(workspace) == "c,b,a"


def test_lists_sort_ignore_case():
    lst = _list(_text("Banana"), _text("apple"))
    workspace = _set_output(_join_list({
        "type": "lists_sort",
        "fields": {"TYPE": "IGNORE_CASE", "DIRECTION": "1"},
        "inputs": {"LIST": {"block": lst}},
    }))
    assert _run(workspace) == "apple,Banana"


def test_lists_split_empty_delim_chars():
    workspace = _set_output(_join_list({
        "type": "lists_split",
        "fields": {"MODE": "SPLIT"},
        "inputs": {
            "INPUT": {"block": _text("abc")},
            "DELIM": {"block": _text("")},
        },
    }, delim="-"))
    assert _run(workspace) == "a-b-c"


def test_lists_join_non_list_input():
    workspace = _set_output({
        "type": "lists_split",
        "fields": {"MODE": "JOIN"},
        "inputs": {
            "INPUT": {"block": _text("solo")},
            "DELIM": {"block": _text(",")},
        },
    })
    assert _run(workspace) == "solo"


# ─── Control flow ───────────────────────────────────────────────────────

def _counter_loop(loop_block):
    """Wrap: C = 0; <loop>; output C. Loop's DO increments C."""
    return {
        "blocks": {"blocks": [{
            "type": "variables_set",
            "fields": {"VAR": {"id": "C"}},
            "inputs": {"VALUE": {"block": _num(0)}},
            "next": {"block": {
                **loop_block,
                "next": {"block": {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": _var_get("C")}},
                }},
            }},
        }]},
        "variables": [{"id": "C", "name": "c"}],
    }


def _increment_c():
    return {
        "type": "variables_set",
        "fields": {"VAR": {"id": "C"}},
        "inputs": {"VALUE": {"block": {
            "type": "math_arithmetic",
            "fields": {"OP": "ADD"},
            "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(1)}},
        }}},
    }


def test_controls_whileUntil_while():
    # while C < 3: C += 1
    loop = {
        "type": "controls_whileUntil",
        "fields": {"MODE": "WHILE"},
        "inputs": {
            "BOOL": {"block": {
                "type": "logic_compare",
                "fields": {"OP": "LT"},
                "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(3)}},
            }},
            "DO": {"block": _increment_c()},
        },
    }
    assert _run(_counter_loop(loop)) == "3"


def test_controls_whileUntil_until():
    # until C >= 4: C += 1
    loop = {
        "type": "controls_whileUntil",
        "fields": {"MODE": "UNTIL"},
        "inputs": {
            "BOOL": {"block": {
                "type": "logic_compare",
                "fields": {"OP": "GTE"},
                "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(4)}},
            }},
            "DO": {"block": _increment_c()},
        },
    }
    assert _run(_counter_loop(loop)) == "4"


def test_controls_for_ascending():
    loop = {
        "type": "controls_for",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "FROM": {"block": _num(1)},
            "TO": {"block": _num(4)},
            "BY": {"block": _num(1)},
            "DO": {"block": _increment_c()},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    assert _run(ws) == "4"


def test_controls_for_descending():
    loop = {
        "type": "controls_for",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "FROM": {"block": _num(5)},
            "TO": {"block": _num(1)},
            "BY": {"block": _num(2)},
            "DO": {"block": _increment_c()},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    # 5, 3, 1 → 3 iterations
    assert _run(ws) == "3"


def test_controls_for_by_zero_is_noop():
    loop = {
        "type": "controls_for",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "FROM": {"block": _num(1)},
            "TO": {"block": _num(5)},
            "BY": {"block": _num(0)},
            "DO": {"block": _increment_c()},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    assert _run(ws) == "0"


def test_controls_for_non_numeric_bounds_noop():
    loop = {
        "type": "controls_for",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "FROM": {"block": _text("a")},
            "TO": {"block": _num(3)},
            "BY": {"block": _num(1)},
            "DO": {"block": _increment_c()},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    assert _run(ws) == "0"


def test_controls_if_elseif_else():
    def classify(n):
        return _run({
            "blocks": {"blocks": [{
                "type": "controls_if",
                "inputs": {
                    "IF0": {"block": {
                        "type": "logic_compare",
                        "fields": {"OP": "LT"},
                        "inputs": {"A": {"block": _num(n)}, "B": {"block": _num(0)}},
                    }},
                    "DO0": {"block": {
                        "type": "restai_set_output",
                        "inputs": {"VALUE": {"block": _text("neg")}},
                    }},
                    "IF1": {"block": {
                        "type": "logic_compare",
                        "fields": {"OP": "EQ"},
                        "inputs": {"A": {"block": _num(n)}, "B": {"block": _num(0)}},
                    }},
                    "DO1": {"block": {
                        "type": "restai_set_output",
                        "inputs": {"VALUE": {"block": _text("zero")}},
                    }},
                    "ELSE": {"block": {
                        "type": "restai_set_output",
                        "inputs": {"VALUE": {"block": _text("pos")}},
                    }},
                },
            }]},
            "variables": [],
        })
    assert classify(-1) == "neg"
    assert classify(0) == "zero"
    assert classify(9) == "pos"


def test_infinite_while_raises_clean_400():
    loop = {
        "type": "controls_whileUntil",
        "fields": {"MODE": "WHILE"},
        "inputs": {"BOOL": {"block": _bool(True)}},
    }
    workspace = {"blocks": {"blocks": [loop]}, "variables": []}
    with pytest.raises(HTTPException) as exc:
        _run(workspace)
    assert exc.value.status_code == 400
    assert "maximum iterations" in exc.value.detail


def test_max_iterations_constant_sane():
    assert MAX_ITERATIONS == 10000


def test_repeat_with_non_numeric_times_noop():
    loop = {
        "type": "controls_repeat_ext",
        "inputs": {
            "TIMES": {"block": _text("many")},
            "DO": {"block": _increment_c()},
        },
    }
    assert _run(_counter_loop(loop)) == "0"


def test_for_each_non_list_noop():
    loop = {
        "type": "controls_forEach",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "LIST": {"block": _text("not a list")},
            "DO": {"block": _increment_c()},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    assert _run(ws) == "0"


def test_break_in_for_loop():
    # for i in 1..10: C += 1; if C >= 2: break
    loop = {
        "type": "controls_for",
        "fields": {"VAR": {"id": "I"}},
        "inputs": {
            "FROM": {"block": _num(1)},
            "TO": {"block": _num(10)},
            "BY": {"block": _num(1)},
            "DO": {"block": {
                **_increment_c(),
                "next": {"block": {
                    "type": "controls_if",
                    "inputs": {
                        "IF0": {"block": {
                            "type": "logic_compare",
                            "fields": {"OP": "GTE"},
                            "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(2)}},
                        }},
                        "DO0": {"block": {
                            "type": "controls_flow_statements",
                            "fields": {"FLOW": "BREAK"},
                        }},
                    },
                }},
            }},
        },
    }
    ws = _counter_loop(loop)
    ws["variables"].append({"id": "I", "name": "i"})
    assert _run(ws) == "2"


def test_continue_in_while_loop():
    # while C < 5: C += 1; if C == 3: continue (still terminates)
    loop = {
        "type": "controls_whileUntil",
        "fields": {"MODE": "WHILE"},
        "inputs": {
            "BOOL": {"block": {
                "type": "logic_compare",
                "fields": {"OP": "LT"},
                "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(5)}},
            }},
            "DO": {"block": {
                **_increment_c(),
                "next": {"block": {
                    "type": "controls_if",
                    "inputs": {
                        "IF0": {"block": {
                            "type": "logic_compare",
                            "fields": {"OP": "EQ"},
                            "inputs": {"A": {"block": _var_get("C")}, "B": {"block": _num(3)}},
                        }},
                        "DO0": {"block": {
                            "type": "controls_flow_statements",
                            "fields": {"FLOW": "CONTINUE"},
                        }},
                    },
                }},
            }},
        },
    }
    assert _run(_counter_loop(loop)) == "5"


# ─── Procedures ─────────────────────────────────────────────────────────

def test_call_unknown_procedure_is_tolerated():
    workspace = {
        "blocks": {"blocks": [
            {"type": "procedures_callnoreturn",
             "extraState": {"name": "nope"},
             "next": {"block": {
                 "type": "restai_set_output",
                 "inputs": {"VALUE": {"block": _text("ok")}},
             }}},
        ]},
        "variables": [],
    }
    assert _run(workspace) == "ok"


def test_callreturn_unknown_procedure_yields_empty():
    workspace = _set_output({
        "type": "procedures_callreturn",
        "extraState": {"name": "ghost"},
    })
    assert _run(workspace) == ""


def test_procedure_registered_via_legacy_arguments_key():
    workspace = {
        "blocks": {"blocks": [
            {
                "type": "procedures_defreturn",
                "fields": {"NAME": "id"},
                "extraState": {"arguments": [{"name": "x", "id": "px"}]},
                "inputs": {"RETURN": {"block": _var_get("px")}},
            },
            {
                "type": "restai_set_output",
                "inputs": {"VALUE": {"block": {
                    "type": "procedures_callreturn",
                    "extraState": {"name": "id"},
                    "inputs": {"ARG0": {"block": _text("echoed")}},
                }}},
            },
        ]},
        "variables": [],
    }
    assert _run(workspace) == "echoed"


def test_procedure_registered_when_chained_via_next():
    """Defs reachable only through `next` chains are still registered."""
    dfn = {
        "type": "procedures_defreturn",
        "fields": {"NAME": "hi"},
        "extraState": {"params": []},
        "inputs": {"RETURN": {"block": _text("hello!")}},
    }
    workspace = {
        "blocks": {"blocks": [{
            "type": "restai_set_output",
            "inputs": {"VALUE": {"block": {
                "type": "procedures_callreturn",
                "extraState": {"name": "hi"},
            }}},
            "next": {"block": dfn},
        }]},
        "variables": [],
    }
    assert _run(workspace) == "hello!"


# ─── restai_call_project ────────────────────────────────────────────────

def _call_project_ws(name="target"):
    return _set_output({
        "type": "restai_call_project",
        "fields": {"PROJECT_NAME": name},
        "inputs": {"TEXT": {"block": _text("hi there")}},
    })


def test_call_project_empty_name_returns_empty():
    assert _run(_call_project_ws(name="")) == ""


def test_call_project_not_found_returns_empty():
    db = types.SimpleNamespace(get_project_by_name=lambda name: None)
    assert _run(_call_project_ws(), db=db) == ""


def test_call_project_unauthorized_returns_empty():
    project_db = types.SimpleNamespace(id=42)
    db = types.SimpleNamespace(get_project_by_name=lambda name: project_db)
    user = types.SimpleNamespace(username="mallory")
    with patch("restai.auth.user_can_access_project", return_value=False) as gate:
        out = _run(_call_project_ws(), db=db, user=user)
    assert out == ""
    gate.assert_called_once()


def test_call_project_success_returns_answer():
    project_db = types.SimpleNamespace(id=42)
    db = types.SimpleNamespace(get_project_by_name=lambda name: project_db)
    user = types.SimpleNamespace(username="alice")
    target = types.SimpleNamespace()
    brain = types.SimpleNamespace(find_project=lambda pid, _db: target)
    with patch("restai.auth.user_can_access_project", return_value=True), \
         patch("restai.helper.chat_main", new=AsyncMock(return_value={"answer": "pong"})) as cm:
        out = _run(_call_project_ws(), db=db, user=user, brain=brain)
    assert out == "pong"
    q = cm.call_args.args[3]
    assert q.question == "hi there"


def test_call_project_load_failure_returns_empty():
    project_db = types.SimpleNamespace(id=42)
    db = types.SimpleNamespace(get_project_by_name=lambda name: project_db)
    brain = types.SimpleNamespace(find_project=lambda pid, _db: None)
    with patch("restai.auth.user_can_access_project", return_value=True):
        assert _run(_call_project_ws(), db=db, brain=brain) == ""


def test_call_project_chat_main_exception_returns_empty():
    project_db = types.SimpleNamespace(id=42)
    db = types.SimpleNamespace(get_project_by_name=lambda name: project_db)
    brain = types.SimpleNamespace(find_project=lambda pid, _db: types.SimpleNamespace())
    with patch("restai.auth.user_can_access_project", return_value=True), \
         patch("restai.helper.chat_main", new=AsyncMock(side_effect=RuntimeError("boom"))):
        assert _run(_call_project_ws(), db=db, brain=brain) == ""


# ─── restai_classifier ──────────────────────────────────────────────────

def _classifier_ws(text="great product", labels="positive,negative"):
    return _set_output({
        "type": "restai_classifier",
        "inputs": {
            "TEXT": {"block": _text(text)},
            "LABELS": {"block": _text(labels)},
        },
    })


def test_classifier_returns_top_label():
    brain = types.SimpleNamespace(
        classify=lambda inp: {"labels": ["positive", "negative"], "scores": [0.9, 0.1]},
    )
    assert _run(_classifier_ws(), brain=brain) == "positive"


def test_classifier_empty_text_returns_empty():
    brain = types.SimpleNamespace(classify=lambda inp: {"labels": ["x"]})
    assert _run(_classifier_ws(text=""), brain=brain) == ""


def test_classifier_blank_labels_returns_empty():
    brain = types.SimpleNamespace(classify=lambda inp: {"labels": ["x"]})
    assert _run(_classifier_ws(labels=" , , "), brain=brain) == ""


def test_classifier_brain_error_returns_empty():
    def _boom(inp):
        raise RuntimeError("model offline")
    brain = types.SimpleNamespace(classify=_boom)
    assert _run(_classifier_ws(), brain=brain) == ""

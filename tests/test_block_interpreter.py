"""Unit tests for the Blockly workspace interpreter.

Constructs a BlockInterpreter directly (no HTTP / DB / brain required for most
blocks — we only need the real wiring for restai_call_project / restai_classifier,
which these tests don't exercise). Each test hand-crafts a minimal workspace JSON
and asserts the resulting output or a specific log entry.
"""
import asyncio

import pytest

from restai.projects.block_interpreter import BlockInterpreter


def _interp(workspace, input_text="hello"):
    return BlockInterpreter(
        workspace_json=workspace,
        input_text=input_text,
        brain=None,
        user=None,
        db=None,
    )


def _run(workspace, input_text="hello"):
    return asyncio.run(_interp(workspace, input_text).execute())


def _set_output(value_block):
    """Wrap a value block in the usual restai_set_output so execute() returns it."""
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


# ---------------------------------------------------------------- Logic


def test_logic_null_returns_empty_string():
    # logic_null returns None; restai_set_output converts to ""
    workspace = _set_output({"type": "logic_null"})
    assert _run(workspace) == ""


def test_logic_ternary_true_branch():
    workspace = _set_output({
        "type": "logic_ternary",
        "inputs": {
            "IF": {"block": _bool(True)},
            "THEN": {"block": _text("yes")},
            "ELSE": {"block": _text("no")},
        },
    })
    assert _run(workspace) == "yes"


def test_logic_ternary_false_branch():
    workspace = _set_output({
        "type": "logic_ternary",
        "inputs": {
            "IF": {"block": _bool(False)},
            "THEN": {"block": _text("yes")},
            "ELSE": {"block": _text("no")},
        },
    })
    assert _run(workspace) == "no"


# ---------------------------------------------------------------- Math


@pytest.mark.parametrize("op,expected", [
    ("ROOT", 3.0),  # sqrt(9)
    ("ABS", 9.0),
    ("NEG", -9.0),
    ("POW10", 1e9),
])
def test_math_single_ops(op, expected):
    workspace = _set_output({
        "type": "math_single",
        "fields": {"OP": op},
        "inputs": {"NUM": {"block": _num(9)}},
    })
    # output is str() of the result
    assert _run(workspace) == str(expected)


def test_math_trig_sin_90_is_one():
    workspace = _set_output({
        "type": "math_trig",
        "fields": {"OP": "SIN"},
        "inputs": {"NUM": {"block": _num(90)}},
    })
    # sin(90°) == 1
    assert abs(float(_run(workspace)) - 1.0) < 1e-9


def test_math_constant_pi():
    import math
    workspace = _set_output({
        "type": "math_constant",
        "fields": {"CONSTANT": "PI"},
    })
    assert abs(float(_run(workspace)) - math.pi) < 1e-12


def test_math_round_up_down():
    up = _set_output({
        "type": "math_round",
        "fields": {"OP": "ROUNDUP"},
        "inputs": {"NUM": {"block": _num(2.1)}},
    })
    assert _run(up) == "3"
    down = _set_output({
        "type": "math_round",
        "fields": {"OP": "ROUNDDOWN"},
        "inputs": {"NUM": {"block": _num(2.9)}},
    })
    assert _run(down) == "2"


@pytest.mark.parametrize("op,expected", [
    ("SUM", 15.0),
    ("MIN", 1.0),
    ("MAX", 5.0),
    ("AVERAGE", 3.0),
])
def test_math_on_list_ops(op, expected):
    lst = _list(_num(1), _num(2), _num(3), _num(4), _num(5))
    workspace = _set_output({
        "type": "math_on_list",
        "fields": {"OP": op},
        "inputs": {"LIST": {"block": lst}},
    })
    assert float(_run(workspace)) == expected


def test_math_modulo():
    workspace = _set_output({
        "type": "math_modulo",
        "inputs": {
            "DIVIDEND": {"block": _num(10)},
            "DIVISOR": {"block": _num(3)},
        },
    })
    assert float(_run(workspace)) == 1.0


def test_math_constrain():
    workspace = _set_output({
        "type": "math_constrain",
        "inputs": {
            "VALUE": {"block": _num(100)},
            "LOW": {"block": _num(0)},
            "HIGH": {"block": _num(10)},
        },
    })
    assert float(_run(workspace)) == 10.0


def test_math_number_property_even():
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": "EVEN"},
        "inputs": {"NUMBER_TO_CHECK": {"block": _num(4)}},
    })
    assert _run(workspace) == "True"


def test_math_number_property_prime():
    workspace = _set_output({
        "type": "math_number_property",
        "fields": {"PROPERTY": "PRIME"},
        "inputs": {"NUMBER_TO_CHECK": {"block": _num(7)}},
    })
    assert _run(workspace) == "True"


# ---------------------------------------------------------------- Text


def test_text_getSubstring_first_last():
    """substring from first to last == whole string"""
    workspace = _set_output({
        "type": "text_getSubstring",
        "fields": {"WHERE1": "FIRST", "WHERE2": "LAST"},
        "inputs": {"STRING": {"block": _text("hello world")}},
    })
    assert _run(workspace) == "hello world"


def test_text_getSubstring_from_start_from_start():
    """substring 1-5 of 'hello world' → 'hello'"""
    workspace = _set_output({
        "type": "text_getSubstring",
        "fields": {"WHERE1": "FROM_START", "WHERE2": "FROM_START"},
        "inputs": {
            "STRING": {"block": _text("hello world")},
            "AT1": {"block": _num(1)},
            "AT2": {"block": _num(5)},
        },
    })
    assert _run(workspace) == "hello"


def test_text_replace():
    workspace = _set_output({
        "type": "text_replace",
        "inputs": {
            "FROM": {"block": _text("foo")},
            "TO": {"block": _text("bar")},
            "TEXT": {"block": _text("foo baz foo")},
        },
    })
    assert _run(workspace) == "bar baz bar"


def test_text_count():
    workspace = _set_output({
        "type": "text_count",
        "inputs": {
            "SUB": {"block": _text("a")},
            "TEXT": {"block": _text("banana")},
        },
    })
    assert _run(workspace) == "3"


def test_text_reverse():
    workspace = _set_output({
        "type": "text_reverse",
        "inputs": {"TEXT": {"block": _text("abc")}},
    })
    assert _run(workspace) == "cba"


def test_text_append_statement():
    """text_append mutates a variable — set a var, append, then output it."""
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "variables_set",
                    "fields": {"VAR": {"id": "V1"}},
                    "inputs": {"VALUE": {"block": _text("Hello, ")}},
                    "next": {"block": {
                        "type": "text_append",
                        "fields": {"VAR": {"id": "V1"}},
                        "inputs": {"TEXT": {"block": _text("world")}},
                        "next": {"block": {
                            "type": "restai_set_output",
                            "inputs": {"VALUE": {"block": {
                                "type": "variables_get",
                                "fields": {"VAR": {"id": "V1"}},
                            }}},
                        }},
                    }},
                }
            ]
        },
        "variables": [{"id": "V1", "name": "greeting"}],
    }
    assert _run(workspace) == "Hello, world"


# ---------------------------------------------------------------- Lists


def test_lists_create_and_length():
    workspace = _set_output({
        "type": "lists_length",
        "inputs": {"VALUE": {"block": _list(_num(1), _num(2), _num(3))}},
    })
    assert _run(workspace) == "3"


def test_lists_getIndex_first():
    workspace = _set_output({
        "type": "lists_getIndex",
        "fields": {"MODE": "GET", "WHERE": "FIRST"},
        "inputs": {"VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))}},
    })
    assert _run(workspace) == "a"


def test_lists_getIndex_last():
    workspace = _set_output({
        "type": "lists_getIndex",
        "fields": {"MODE": "GET", "WHERE": "LAST"},
        "inputs": {"VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))}},
    })
    assert _run(workspace) == "c"


def test_lists_getIndex_from_start():
    workspace = _set_output({
        "type": "lists_getIndex",
        "fields": {"MODE": "GET", "WHERE": "FROM_START"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))},
            "AT": {"block": _num(2)},
        },
    })
    # 1-based: index 2 → 'b'
    assert _run(workspace) == "b"


def test_lists_indexOf_found():
    workspace = _set_output({
        "type": "lists_indexOf",
        "fields": {"END": "FIRST"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))},
            "FIND": {"block": _text("b")},
        },
    })
    # 1-based, found at position 2
    assert _run(workspace) == "2"


def test_lists_indexOf_missing():
    workspace = _set_output({
        "type": "lists_indexOf",
        "fields": {"END": "FIRST"},
        "inputs": {
            "VALUE": {"block": _list(_text("a"), _text("b"))},
            "FIND": {"block": _text("z")},
        },
    })
    assert _run(workspace) == "0"


def test_lists_sort_numeric_ascending():
    lst = _list(_num(3), _num(1), _num(2))
    workspace = _set_output({
        "type": "lists_split",
        "fields": {"MODE": "JOIN"},
        "inputs": {
            "INPUT": {"block": {
                "type": "lists_sort",
                "fields": {"TYPE": "NUMERIC", "DIRECTION": "1"},
                "inputs": {"LIST": {"block": lst}},
            }},
            "DELIM": {"block": _text(",")},
        },
    })
    assert _run(workspace) == "1,2,3"


def test_lists_split_and_join_roundtrip():
    workspace = _set_output({
        "type": "lists_split",
        "fields": {"MODE": "JOIN"},
        "inputs": {
            "INPUT": {"block": {
                "type": "lists_split",
                "fields": {"MODE": "SPLIT"},
                "inputs": {
                    "INPUT": {"block": _text("a,b,c")},
                    "DELIM": {"block": _text(",")},
                },
            }},
            "DELIM": {"block": _text("-")},
        },
    })
    assert _run(workspace) == "a-b-c"


def test_lists_reverse():
    lst = _list(_num(1), _num(2), _num(3))
    workspace = _set_output({
        "type": "lists_split",
        "fields": {"MODE": "JOIN"},
        "inputs": {
            "INPUT": {"block": {
                "type": "lists_reverse",
                "inputs": {"LIST": {"block": lst}},
            }},
            "DELIM": {"block": _text(",")},
        },
    })
    assert _run(workspace) == "3,2,1"


def test_lists_setIndex_set_statement():
    """Build a list, SET index 2 to 'X', then join + output."""
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "variables_set",
                    "fields": {"VAR": {"id": "L"}},
                    "inputs": {"VALUE": {"block": _list(_text("a"), _text("b"), _text("c"))}},
                    "next": {"block": {
                        "type": "lists_setIndex",
                        "fields": {"MODE": "SET", "WHERE": "FROM_START"},
                        "inputs": {
                            "LIST": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "L"}}}},
                            "AT": {"block": _num(2)},
                            "TO": {"block": _text("X")},
                        },
                        "next": {"block": {
                            "type": "restai_set_output",
                            "inputs": {"VALUE": {"block": {
                                "type": "lists_split",
                                "fields": {"MODE": "JOIN"},
                                "inputs": {
                                    "INPUT": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "L"}}}},
                                    "DELIM": {"block": _text(",")},
                                },
                            }}},
                        }},
                    }},
                }
            ]
        },
        "variables": [{"id": "L", "name": "lst"}],
    }
    assert _run(workspace) == "a,X,c"


# ---------------------------------------------------------------- Flow control


def test_controls_flow_break_in_repeat():
    """Counter-var increments inside a repeat-10 loop but breaks at iteration 3."""
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "variables_set",
                    "fields": {"VAR": {"id": "C"}},
                    "inputs": {"VALUE": {"block": _num(0)}},
                    "next": {"block": {
                        "type": "controls_repeat_ext",
                        "inputs": {
                            "TIMES": {"block": _num(10)},
                            "DO": {"block": {
                                "type": "variables_set",
                                "fields": {"VAR": {"id": "C"}},
                                "inputs": {"VALUE": {"block": {
                                    "type": "math_arithmetic",
                                    "fields": {"OP": "ADD"},
                                    "inputs": {
                                        "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "C"}}}},
                                        "B": {"block": _num(1)},
                                    },
                                }}},
                                "next": {"block": {
                                    "type": "controls_if",
                                    "inputs": {
                                        "IF0": {"block": {
                                            "type": "logic_compare",
                                            "fields": {"OP": "GTE"},
                                            "inputs": {
                                                "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "C"}}}},
                                                "B": {"block": _num(3)},
                                            },
                                        }},
                                        "DO0": {"block": {
                                            "type": "controls_flow_statements",
                                            "fields": {"FLOW": "BREAK"},
                                        }},
                                    },
                                }},
                            }},
                        },
                        "next": {"block": {
                            "type": "restai_set_output",
                            "inputs": {"VALUE": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "C"}}}}},
                        }},
                    }},
                }
            ]
        },
        "variables": [{"id": "C", "name": "counter"}],
    }
    # math_arithmetic coerces to float, so 0 + 1 + 1 + 1 = 3.0
    assert _run(workspace) == "3.0"


def test_controls_flow_continue_in_for_each():
    """Sum 1+2+...+5 but skip 3 via continue."""
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "variables_set",
                    "fields": {"VAR": {"id": "S"}},
                    "inputs": {"VALUE": {"block": _num(0)}},
                    "next": {"block": {
                        "type": "controls_forEach",
                        "fields": {"VAR": {"id": "I"}},
                        "inputs": {
                            "LIST": {"block": _list(_num(1), _num(2), _num(3), _num(4), _num(5))},
                            "DO": {"block": {
                                "type": "controls_if",
                                "inputs": {
                                    "IF0": {"block": {
                                        "type": "logic_compare",
                                        "fields": {"OP": "EQ"},
                                        "inputs": {
                                            "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "I"}}}},
                                            "B": {"block": _num(3)},
                                        },
                                    }},
                                    "DO0": {"block": {
                                        "type": "controls_flow_statements",
                                        "fields": {"FLOW": "CONTINUE"},
                                    }},
                                },
                                "next": {"block": {
                                    "type": "variables_set",
                                    "fields": {"VAR": {"id": "S"}},
                                    "inputs": {"VALUE": {"block": {
                                        "type": "math_arithmetic",
                                        "fields": {"OP": "ADD"},
                                        "inputs": {
                                            "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "S"}}}},
                                            "B": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "I"}}}},
                                        },
                                    }}},
                                }},
                            }},
                        },
                        "next": {"block": {
                            "type": "restai_set_output",
                            "inputs": {"VALUE": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "S"}}}}},
                        }},
                    }},
                }
            ]
        },
        "variables": [{"id": "S", "name": "sum"}, {"id": "I", "name": "i"}],
    }
    # 1 + 2 + 4 + 5 = 12 (float because math_arithmetic coerces)
    assert _run(workspace) == "12.0"


# ---------------------------------------------------------------- Procedures


def _proc_double():
    """procedures_defreturn double(x) = x * 2"""
    return {
        "type": "procedures_defreturn",
        "fields": {"NAME": "double"},
        "extraState": {"params": [{"name": "x", "id": "param_x"}]},
        "inputs": {
            "RETURN": {"block": {
                "type": "math_arithmetic",
                "fields": {"OP": "MULTIPLY"},
                "inputs": {
                    "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "param_x"}}}},
                    "B": {"block": _num(2)},
                },
            }},
        },
    }


def test_procedure_return_value():
    workspace = {
        "blocks": {
            "blocks": [
                _proc_double(),
                {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": {
                        "type": "procedures_callreturn",
                        "extraState": {"name": "double", "params": ["param_x"]},
                        "inputs": {"ARG0": {"block": _num(7)}},
                    }}},
                },
            ]
        },
        "variables": [],
    }
    # math_arithmetic returns float
    assert _run(workspace) == "14.0"


def test_procedure_scope_isolation():
    """A global variable named the same as a param is unchanged by the call."""
    # Global `x` = 100. Define `bump(x)` that sets x = 999 (the param, not global).
    # After the call, global x is still 100.
    workspace = {
        "blocks": {
            "blocks": [
                # global x = 100
                {
                    "type": "variables_set",
                    "fields": {"VAR": {"id": "global_x"}},
                    "inputs": {"VALUE": {"block": _num(100)}},
                },
                # def bump(x): x = 999 (this writes to the param frame, not global_x)
                {
                    "type": "procedures_defnoreturn",
                    "fields": {"NAME": "bump"},
                    "extraState": {"params": [{"name": "x", "id": "param_x"}]},
                    "inputs": {"STACK": {"block": {
                        "type": "variables_set",
                        "fields": {"VAR": {"id": "param_x"}},
                        "inputs": {"VALUE": {"block": _num(999)}},
                    }}},
                },
                # Call bump(50)
                {
                    "type": "procedures_callnoreturn",
                    "extraState": {"name": "bump", "params": ["param_x"]},
                    "inputs": {"ARG0": {"block": _num(50)}},
                    "next": {"block": {
                        "type": "restai_set_output",
                        "inputs": {"VALUE": {"block": {
                            "type": "variables_get", "fields": {"VAR": {"id": "global_x"}},
                        }}},
                    }},
                },
            ]
        },
        "variables": [
            {"id": "global_x", "name": "x"},
            {"id": "param_x", "name": "x"},  # param has its own id
        ],
    }
    # The global_x was set with math_number (int 100), never touched since.
    assert _run(workspace) == "100"


def test_procedure_ifreturn_early_exit():
    """A procedure that returns 'big' if x >= 10 else falls through to 'small'."""
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "procedures_defreturn",
                    "fields": {"NAME": "classify"},
                    "extraState": {"params": [{"name": "x", "id": "px"}]},
                    "inputs": {
                        "STACK": {"block": {
                            "type": "procedures_ifreturn",
                            "inputs": {
                                "CONDITION": {"block": {
                                    "type": "logic_compare",
                                    "fields": {"OP": "GTE"},
                                    "inputs": {
                                        "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "px"}}}},
                                        "B": {"block": _num(10)},
                                    },
                                }},
                                "VALUE": {"block": _text("big")},
                            },
                        }},
                        "RETURN": {"block": _text("small")},
                    },
                },
                {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": {
                        "type": "procedures_callreturn",
                        "extraState": {"name": "classify", "params": ["px"]},
                        "inputs": {"ARG0": {"block": _num(42)}},
                    }}},
                },
            ]
        },
        "variables": [],
    }
    assert _run(workspace) == "big"


def test_procedure_ifreturn_fallthrough():
    workspace = {
        "blocks": {
            "blocks": [
                {
                    "type": "procedures_defreturn",
                    "fields": {"NAME": "classify"},
                    "extraState": {"params": [{"name": "x", "id": "px"}]},
                    "inputs": {
                        "STACK": {"block": {
                            "type": "procedures_ifreturn",
                            "inputs": {
                                "CONDITION": {"block": {
                                    "type": "logic_compare",
                                    "fields": {"OP": "GTE"},
                                    "inputs": {
                                        "A": {"block": {"type": "variables_get", "fields": {"VAR": {"id": "px"}}}},
                                        "B": {"block": _num(10)},
                                    },
                                }},
                                "VALUE": {"block": _text("big")},
                            },
                        }},
                        "RETURN": {"block": _text("small")},
                    },
                },
                {
                    "type": "restai_set_output",
                    "inputs": {"VALUE": {"block": {
                        "type": "procedures_callreturn",
                        "extraState": {"name": "classify", "params": ["px"]},
                        "inputs": {"ARG0": {"block": _num(3)}},
                    }}},
                },
            ]
        },
        "variables": [],
    }
    assert _run(workspace) == "small"

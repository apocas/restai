"""Unit tests for restai/llms/tools/data_parser.py — JSON dot-path queries,
wildcard expansion, CSV column extraction and filtering."""
import json

from restai.llms.tools.data_parser import data_parser

USERS_JSON = json.dumps({
    "users": [
        {"name": "Ada", "age": 36},
        {"name": "Bob", "age": 41},
    ],
    "count": 2,
})

CSV = "name,age,city\nAda,36,London\nBob,41,Paris\nCara,29,London\n"


# ─── JSON: summaries (no query) ─────────────────────────────────────────

def test_json_object_summary():
    out = data_parser(USERS_JSON)
    assert out == "Object with keys: ['users', 'count']"


def test_json_array_summary():
    out = data_parser(json.dumps([{"a": 1}, {"a": 2}]))
    assert out == "2 items. Keys: ['a']"


def test_json_array_of_scalars_summary():
    assert data_parser(json.dumps([1, 2, 3])) == "3 items. Keys: N/A"


def test_json_scalar_dumped():
    assert data_parser("42") == "42"


# ─── JSON: dot-path queries ─────────────────────────────────────────────

def test_json_nested_path_and_index():
    assert data_parser(USERS_JSON, query="users.0.name") == "Ada"
    assert data_parser(USERS_JSON, query="users.1.age") == "41"
    assert data_parser(USERS_JSON, query="count") == "2"


def test_json_path_returns_structure_as_json():
    out = data_parser(USERS_JSON, query="users.0")
    assert json.loads(out) == {"name": "Ada", "age": 36}


def test_json_index_out_of_range():
    assert data_parser(USERS_JSON, query="users.9") == "Error: Index 9 out of range"


def test_json_missing_key_lists_available():
    out = data_parser(USERS_JSON, query="nope")
    assert out.startswith("Error: Key 'nope' not found.")
    assert "'users'" in out


def test_json_cannot_traverse_scalar():
    out = data_parser(USERS_JSON, query="count.deeper")
    assert out == "Error: Cannot access 'deeper' on int"


def test_json_wildcard_with_remaining_path():
    out = data_parser(USERS_JSON, query="users.*.name")
    assert out == "Ada\nBob"


def test_json_wildcard_terminal_dumps_array():
    out = data_parser(USERS_JSON, query="users.*")
    assert json.loads(out) == [{"name": "Ada", "age": 36}, {"name": "Bob", "age": 41}]


def test_json_wildcard_on_non_array():
    out = data_parser(json.dumps({"a": {"b": 1}}), query="a.*")
    assert out == "Error: '*' only works on arrays, got dict"


def test_json_parse_error():
    assert data_parser("{not json", format="json").startswith("Error parsing JSON:")


def test_generic_exception_becomes_error_string():
    # Non-string data raises TypeError inside json.loads → generic handler.
    assert data_parser(None, format="json").startswith("Error: ")


def test_unknown_format():
    assert data_parser("x", format="xml") == "Error: Unknown format 'xml'. Use 'json' or 'csv'."


# ─── CSV ────────────────────────────────────────────────────────────────

def test_csv_summary():
    assert data_parser(CSV, format="csv") == "3 rows. Columns: ['name', 'age', 'city']"


def test_csv_empty():
    assert data_parser("name,age\n", format="csv") == "Empty CSV (no rows)"


def test_csv_column_extraction():
    assert data_parser(CSV, format="csv", query="name") == "Ada\nBob\nCara"


def test_csv_missing_column():
    out = data_parser(CSV, format="csv", query="salary")
    assert out.startswith("Error: Column 'salary' not found.")
    assert "'city'" in out


def test_csv_filter_rows():
    out = data_parser(CSV, format="csv", query="city=London")
    lines = out.split("\n")
    assert lines[0] == "name,age,city"
    assert lines[1] == "Ada,36,London"
    assert lines[2] == "Cara,29,London"
    assert len(lines) == 3


def test_csv_filter_no_match():
    assert data_parser(CSV, format="csv", query="city=Tokyo") == "No rows where city = Tokyo"


def test_csv_filter_missing_column():
    out = data_parser(CSV, format="csv", query="salary=10")
    assert out.startswith("Error: Column 'salary' not found.")


def test_csv_filter_value_with_equals_sign():
    csv_data = "key,value\nurl,a=b\n"
    out = data_parser(csv_data, format="csv", query="value=a=b")
    assert "url,a=b" in out

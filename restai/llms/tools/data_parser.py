from typing import Optional


def data_parser(
    data: str,
    format: str = "json",
    query: Optional[str] = None,
) -> str:
    """
    Parse and query JSON or CSV data. Extract specific fields, filter rows, or summarize structured data.

    Args:
        data (str): The raw JSON or CSV string to parse.
        format (str): Data format — "json" or "csv". Default: "json".
        query (Optional[str]): Dot-path query for JSON (e.g. "users.0.name", "items.*.price") or column name for CSV (e.g. "name" to extract that column, "name=John" to filter rows where name equals John).
    """
    import json
    import csv
    from io import StringIO

    try:
        if format == "json":
            return _query_json(json.loads(data), query)
        elif format == "csv":
            return _query_csv(data, query)
        else:
            return f"Error: Unknown format '{format}'. Use 'json' or 'csv'."
    except json.JSONDecodeError as e:
        return f"Error parsing JSON: {e}"
    except Exception as e:
        return f"Error: {e}"


def _query_json(data, query):
    import json

    if not query:
        if isinstance(data, list):
            return f"{len(data)} items. Keys: {list(data[0].keys()) if data and isinstance(data[0], dict) else 'N/A'}"
        elif isinstance(data, dict):
            return f"Object with keys: {list(data.keys())}"
        return json.dumps(data, indent=2, default=str)

    parts = query.split(".")
    current = data
    for part in parts:
        if part == "*":
            if isinstance(current, list):
                remaining = ".".join(parts[parts.index(part) + 1:])
                if remaining:
                    results = []
                    for item in current:
                        r = _query_json(item, remaining)
                        results.append(r)
                    return "\n".join(results)
                return json.dumps(current, indent=2, default=str)
            return f"Error: '*' only works on arrays, got {type(current).__name__}"
        elif part.isdigit():
            idx = int(part)
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return f"Error: Index {idx} out of range"
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, dict):
            return f"Error: Key '{part}' not found. Available: {list(current.keys())}"
        else:
            return f"Error: Cannot access '{part}' on {type(current).__name__}"

    if isinstance(current, (dict, list)):
        return json.dumps(current, indent=2, default=str)
    return str(current)


def _query_csv(data, query):
    import csv
    from io import StringIO

    reader = csv.DictReader(StringIO(data))
    rows = list(reader)

    if not rows:
        return "Empty CSV (no rows)"

    if not query:
        return f"{len(rows)} rows. Columns: {list(rows[0].keys())}"

    # Filter: column=value
    if "=" in query:
        col, val = query.split("=", 1)
        col = col.strip()
        val = val.strip()
        if col not in rows[0]:
            return f"Error: Column '{col}' not found. Available: {list(rows[0].keys())}"
        filtered = [r for r in rows if r.get(col, "").strip() == val]
        if not filtered:
            return f"No rows where {col} = {val}"
        lines = [",".join(filtered[0].keys())]
        for r in filtered:
            lines.append(",".join(r.values()))
        return "\n".join(lines)

    # Extract column
    col = query.strip()
    if col not in rows[0]:
        return f"Error: Column '{col}' not found. Available: {list(rows[0].keys())}"
    values = [r[col] for r in rows]
    return "\n".join(values)

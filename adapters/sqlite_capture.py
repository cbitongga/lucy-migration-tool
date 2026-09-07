"""Read-only SQLite schema/data observation adapter. Does not migrate a database."""
import argparse
import base64
import json
import sqlite3
from pathlib import Path


def cell(value):
    if value is None: return {"type": "null"}
    if type(value) is int: return {"type": "integer", "value": str(value)}
    if type(value) is float: return {"type": "real", "value": value.hex()}
    if type(value) is str: return {"type": "text", "value": value}
    if type(value) is bytes: return {"type": "blob", "value": base64.b64encode(value).decode()}
    raise ValueError("Unsupported SQLite value")


def capture(path, tables=None, max_rows=10000):
    p = Path(path).resolve(strict=True)
    connection = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        objects = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        table_names = [r[1] for r in objects if r[0] == "table"]
        if tables:
            if not set(tables) <= set(table_names): raise ValueError("Requested table does not exist")
            table_names = sorted(set(tables))
        observations = {"schema": [list(row) for row in objects if not tables or row[2] in tables], "tables": {}}
        total = 0
        for table in table_names:
            quoted = '"' + table.replace('"', '""') + '"'
            rows = []
            for row in connection.execute("SELECT * FROM " + quoted):
                total += 1
                if total > max_rows: raise ValueError("Snapshot exceeds max_rows; narrow scope explicitly, never truncate")
                rows.append([cell(v) for v in row])
            # Physical table order has no contract; duplicates and typed values remain.
            rows.sort(key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=True))
            observations["tables"][table] = {
                "columns": [list(r) for r in connection.execute("PRAGMA table_xinfo(" + quoted + ")")],
                "rows": rows, "row_count": len(rows)}
        if not table_names: raise ValueError("Empty database cannot establish declared data parity")
        return {"schema_version": 1, "dimension": "database", "observations": observations}
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--table", action="append")
    parser.add_argument("--max-rows", type=int, default=10000)
    args = parser.parse_args()
    if args.max_rows < 1: parser.error("max-rows must be positive")
    print(json.dumps(capture(args.database, args.table, args.max_rows), ensure_ascii=True, sort_keys=True))

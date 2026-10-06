"""Load Annex C CSVs from a folder into SQLite (judges use this). Owner: A3 account-data.

Usage: python scripts/load_accounts.py --dir test_accounts/

Reads whichever of accounts.csv, plan_limits.csv, usage.csv, invoices.csv, platform_status.csv and
policy_registry.csv exist (missing files are skipped), validates them WITHOUT the reserved-ID check
(judge data uses A9000-A9999 and INV-J...), skips rows with hard violations, upserts the rest.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # lets the CLI import app.*

from app import db  # noqa: E402
from scripts.validate_accounts import MODELS, columns, find_problems, read_tables  # noqa: E402


# Read whichever Annex C CSVs exist in `path`, validate them (no reserved-ID check) and upsert.
# Returns {"loaded": {table: rows}, "violations": [rows refused], "warnings": [loaded anyway], "skipped_files": [...]}.
def load_dir(path: str) -> dict:
    db.init_db()
    tables, missing = read_tables(path)
    with db.connect() as conn:  # judges may load usage/invoices for accounts that are already in the DB
        existing = {row["account_id"] for row in conn.execute("SELECT account_id FROM accounts")}
    problems = find_problems(tables, check_reserved=False, known_accounts=existing)
    refused = {(p["table"], p["index"]) for p in problems if p["hard"]}

    loaded = {}
    with db.connect() as conn:
        for table, rows in tables.items():  # read_tables keeps the safe order (plans, accounts, usage, ...)
            cols = columns(table)
            good = [MODELS[table].model_validate(row).model_dump()  # also turns "10000" into 10000
                    for i, row in enumerate(rows) if (table, i) not in refused]
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [[row[c] for c in cols] for row in good])
            loaded[table] = len(good)
    return {"loaded": loaded,
            "violations": [p["message"] + " -> row not loaded" for p in problems if p["hard"]],
            "warnings": [p["message"] for p in problems if not p["hard"]],
            "skipped_files": missing}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Annex C CSV files into the InsightDesk SQLite database.")
    parser.add_argument("--dir", required=True, help="folder containing accounts.csv, usage.csv, ...")
    folder = parser.parse_args().dir
    if not pathlib.Path(folder).is_dir():
        sys.exit(f"folder not found: {folder}")
    print(json.dumps(load_dir(folder), indent=2))

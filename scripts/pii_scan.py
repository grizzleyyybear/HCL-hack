"""PII / secret leak scanner (R9 evidence for gate G4). Owner: A14 red-team.

Runs app.safety.redact over every line of every text file, every CSV cell and every text value in
SQLite tables, and prints each hit with its location and a masked preview (the redacted text, so the
scan itself never prints the raw value). Exit code 1 when any leak is found.

    python scripts/pii_scan.py logs/ insightdesk.db data/accounts data/kb

owner_email in the accounts table / accounts.csv is synthetic @example.com PII by design (Annex C):
it is reported separately as expected PII, not as a leak.
"""
import argparse
import collections
import csv
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import ROOT  # noqa: E402
from app.safety import redact  # noqa: E402

# Folders skipped unless --include-all, and why.
EXCLUDED = {
    ROOT / "data" / "raw": "gitignored raw public downloads (real third-party text, never committed)",
    ROOT / "data" / "generation" / "accounts_batches": "raw LLM output that keeps its planted mistakes for the data card",
}
SQLITE_HEADER = b"SQLite format 3\x00"


class Report:
    """Collects leaks (location, preview) and a count of expected owner_email PII per source."""

    # Start with empty hit lists.
    def __init__(self):
        self.leaks: list[tuple[str, str]] = []
        self.expected: collections.Counter = collections.Counter()  # source -> count

    # Redact one text value; record it as a leak, or as expected PII when it is a synthetic owner_email.
    def check(self, source, where: str, text, owner_email: bool = False) -> None:
        if not isinstance(text, str) or not text:
            return
        redacted, found = redact(text)
        if not found:
            return
        if owner_email and text.strip().lower().endswith("@example.com") and redacted.strip() == "[EMAIL]":
            self.expected[str(source)] += 1
        else:
            self.leaks.append((f"{source}:{where}", _preview(text, redacted)))


# Show ~100 characters of the redacted text around the first change, so a human can find the hit.
def _preview(text: str, redacted: str) -> str:
    start = next((i for i, (a, b) in enumerate(zip(text, redacted)) if a != b), 0)
    snippet = redacted[max(0, start - 40): start + 60].replace("\n", " ")
    return ("..." if start > 40 else "") + snippet + ("..." if len(redacted) > start + 60 else "")


# True when the path is inside one of the EXCLUDED folders.
def _excluded(path: pathlib.Path) -> bool:
    resolved = path.resolve()
    return any(resolved == folder or folder in resolved.parents for folder in EXCLUDED)


# Scan every text column of every table; accounts.owner_email is checked as expected PII.
def scan_sqlite(path: pathlib.Path, report: Report) -> None:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            cursor = conn.execute(f'SELECT rowid, * FROM "{table}"')
            columns = [c[0] for c in cursor.description][1:]
            for row in cursor:
                for column, value in zip(columns, row[1:]):
                    report.check(path, f"{table}:{row[0]}:{column}", value,
                                 owner_email=(table == "accounts" and column == "owner_email"))
    finally:
        conn.close()


# Scan a CSV cell by cell (file:line:column); accounts.csv owner_email is checked as expected PII.
def scan_csv(path: pathlib.Path, report: Report) -> None:
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for column, value in row.items():
                value = " ".join(value) if isinstance(value, list) else value  # extra cells on a bad row
                report.check(path, f"{reader.line_num}:{column}", value,
                             owner_email=(path.name == "accounts.csv" and column == "owner_email"))


# Scan a text file line by line (file:line); binary files are skipped.
def scan_text(path: pathlib.Path, report: Report) -> None:
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        report.check(path, str(number), line)


# Pick the scanner for one file by its content/extension.
def scan_file(path: pathlib.Path, report: Report) -> None:
    with open(path, "rb") as f:
        is_sqlite = f.read(16) == SQLITE_HEADER
    if is_sqlite:
        scan_sqlite(path, report)
    elif path.suffix.lower() == ".csv":
        scan_csv(path, report)
    else:
        scan_text(path, report)


# Scan files, folders (recursively) and SQLite DBs; returns the filled Report.
def scan(paths: list[str], include_all: bool = False) -> Report:
    report = Report()
    for arg in paths:
        root = pathlib.Path(arg)
        if not root.exists():
            print(f"skip (not found): {arg}")
            continue
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in files:
            if include_all or not _excluded(path):
                scan_file(path, report)
    return report


# CLI: print exclusions, every leak with location + masked preview, the expected-PII count; exit 1 on leaks.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan files, folders and SQLite DBs for PII and secrets.")
    parser.add_argument("paths", nargs="+", help="files, folders or SQLite DB files")
    parser.add_argument("--include-all", action="store_true", help="also scan the excluded folders")
    args = parser.parse_args(argv)

    if not args.include_all:
        for folder, why in EXCLUDED.items():
            print(f"excluded: {folder.relative_to(ROOT).as_posix()}/ - {why} (use --include-all to scan)")
    report = scan(args.paths, args.include_all)

    for location, preview in report.leaks:
        print(f"LEAK {location}: {preview}")
    for source, count in report.expected.items():
        print(f"expected PII (accounts.owner_email): {count} synthetic @example.com value(s) in {source}")
    print(f"{len(report.leaks)} leak(s), {sum(report.expected.values())} expected PII value(s)")
    return 1 if report.leaks else 0


if __name__ == "__main__":
    sys.exit(main())

"""Initial knowledge-base load into Chroma and the sources table; skips when already loaded. Owner: A5 ingest-api.

Usage: python scripts/ingest_kb.py [--force]
Files follow data/generation/cloudflow_facts.md: article/policy/release_note -> data/kb/articles/<ID>.md,
ticket -> data/kb/tickets/<ID>.json, community -> data/kb/community/<ID>.md.
"""
import argparse
import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # so "from app import ..." works as a script

from app import db, retrieval  # noqa: E402
from app.config import settings  # noqa: E402
from app.schemas import SourceMeta  # noqa: E402

FOLDERS = {"ticket": "tickets", "community": "community"}  # every other doc_type lives in kb/articles/


# Where a register row's file lives, relative to DATA_DIR (e.g. kb/articles/KB-ADV-007.md).
def file_for(meta: SourceMeta) -> pathlib.Path:
    extension = ".json" if meta.doc_type == "ticket" else ".md"
    return pathlib.Path("kb", FOLDERS.get(meta.doc_type, "articles"), meta.source_id + extension)


# Load data/source_register.csv and its files into Chroma and the sources table, once.
# Skips everything when Chroma and the sources table already hold every document (restarts are fast).
# ponytail: the skip check looks at IDs only, so an edited file needs --force to be re-indexed.
def ingest_all(force: bool = False) -> dict:
    db.init_db()
    data_dir = pathlib.Path(settings.DATA_DIR)
    summary = {"ingested": 0, "skipped": 0, "missing_files": [], "invalid_rows": []}
    register = data_dir / "source_register.csv"
    if not register.exists():
        return summary

    found = []  # (meta, path relative to DATA_DIR) for every valid row whose file exists
    with open(register, encoding="utf-8-sig", newline="") as f:  # utf-8-sig: tolerate an Excel BOM
        for row in csv.DictReader(f):
            try:
                meta = SourceMeta.model_validate(row)
            except ValueError as exc:  # pydantic ValidationError is a ValueError
                summary["invalid_rows"].append(f"{row.get('source_id')}: {exc.errors()[0]['msg']}")
                continue
            path = file_for(meta)
            if (data_dir / path).exists():
                found.append((meta, path))
            else:
                summary["missing_files"].append(path.as_posix())

    wanted = {meta.source_id for meta, _ in found}
    if not force and wanted <= _indexed_ids() and wanted <= _registered_ids():
        summary["skipped"] = len(found)
        return summary

    for meta, path in found:
        try:
            retrieval.ingest_document((data_dir / path).read_text(encoding="utf-8"), meta)
        except ValueError as exc:  # e.g. a ticket file that is not valid JSON
            summary["invalid_rows"].append(f"{meta.source_id}: {exc}")
            continue
        retrieval.upsert_source(meta, path.as_posix())
        summary["ingested"] += 1
    return summary


# Source IDs that already have chunks in the Chroma collection.
def _indexed_ids() -> set:
    return {m["source_id"] for m in retrieval._collection().get(include=["metadatas"])["metadatas"]}


# Source IDs that already have a row in the sources table.
def _registered_ids() -> set:
    with db.connect() as conn:
        return {row["source_id"] for row in conn.execute("SELECT source_id FROM sources")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load data/source_register.csv and its files into Chroma.")
    parser.add_argument("--force", action="store_true", help="re-ingest every document even if already loaded")
    print(ingest_all(force=parser.parse_args().force))

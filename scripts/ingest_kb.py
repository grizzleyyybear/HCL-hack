"""Initial knowledge-base load into Chroma and the sources table; skips when already loaded. Area: knowledge and retrieval.

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
# Skips documents whose text and register row are unchanged (restarts are fast); --force re-indexes everything.
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

    # Incremental: only documents that are new, whose file text changed (content hash on the chunks), or whose
    # register last_updated changed are (re-)ingested; restarts with an unchanged KB skip everything.
    indexed, stored = _indexed_hashes(), _stored_versions()
    todo = found if force else [(meta, path) for meta, path in found
                                if indexed.get(meta.source_id) != retrieval.content_hash(_read(data_dir / path))
                                or stored.get(meta.source_id) != meta.last_updated]
    summary["skipped"] = len(found) - len(todo)

    for meta, path in todo:
        try:
            retrieval.ingest_document(_read(data_dir / path), meta)
        except ValueError as exc:  # e.g. a ticket file that is not valid JSON
            summary["invalid_rows"].append(f"{meta.source_id}: {exc}")
            continue
        retrieval.upsert_source(meta, path.as_posix())
        summary["ingested"] += 1
    return summary


# A KB file as text (one place, so the hash check and the ingest read it the same way).
def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# {source_id: content_hash} for every source with chunks in Chroma (older chunks without a hash map to None).
def _indexed_hashes() -> dict:
    return {m["source_id"]: m.get("content_hash") for m in retrieval._collection().get(include=["metadatas"])["metadatas"]}


# The last_updated date stored for each source in the sources table, to spot edited documents.
def _stored_versions() -> dict:
    with db.connect() as conn:
        return {row["source_id"]: row["last_updated"] for row in conn.execute("SELECT source_id, last_updated FROM sources")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load data/source_register.csv and its files into Chroma.")
    parser.add_argument("--force", action="store_true", help="re-ingest every document even if already loaded")
    print(ingest_all(force=parser.parse_args().force))

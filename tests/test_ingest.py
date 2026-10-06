"""Tests for live ingestion (POST /ingest, GET /sources) and the initial KB load (scripts/ingest_kb.py).

Every test points CHROMA_DIR, SQLITE_PATH and DATA_DIR at pytest's tmp_path, never the repo's data.
JD- IDs are used on purpose: they simulate judge content, which /ingest must accept.
"""
import csv
import json

import pytest
from fastapi.testclient import TestClient

from app import retrieval
from app.schemas import SourceMeta
from scripts import ingest_kb

ARTICLE = """# Configuring the Zephyr lantern relay

## Overview
The Zephyr lantern relay forwards marmalade telemetry to the orchestration bus.

## Steps
1. Open Settings, then Lantern relays.
2. Click Add relay and paste the marmalade beacon code.
"""

TICKET = {"source_id": "JD-TEST-002", "customer_question": "My quokka webhook signature keeps failing.",
          "intent": "bug", "resolution": "Regenerate the quokka signing secret and update the receiver.",
          "tags": ["webhooks"], "resolved_at": "2026-09-30", "product_version": "4.3"}

DISTRACTOR = "# Exporting workflow run history\n\n## Steps\nOpen Workflows, select a workflow, click Export.\n"


# Point every store at a fresh temp folder (plus MOCK_LLM, so startup never needs Ollama).
@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MOCK_LLM", "true")
    return tmp_path


# A running app (startup seeds policies and calls ingest_all, which finds no register in the temp DATA_DIR).
@pytest.fixture
def client(temp_env):
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


# Metadata JSON fields for an upload, with sensible defaults.
def meta(source_id, doc_type="article", **extra):
    authority = {"article": 1, "policy": 1, "release_note": 2, "ticket": 4, "community": 5}[doc_type]
    return {"source_id": source_id, "doc_type": doc_type, "title": "Test document", "authority_level": authority,
            "product_versions": "ALL", "last_updated": "2026-10-06", **extra}


# POST /ingest with one file and its metadata (a dict, or a raw string to test bad JSON).
def post(client, filename, content, metadata):
    body = metadata if isinstance(metadata, str) else json.dumps(metadata)
    return client.post("/ingest", files={"file": (filename, content)}, data={"metadata": body})


def test_new_article_is_searchable_listed_and_replaceable(client, temp_env):
    retrieval.ingest_document(DISTRACTOR, SourceMeta(**meta("KB-ADV-007")))
    response = post(client, "zephyr.md", ARTICLE, meta("JD-TEST-001", title="Configuring the Zephyr lantern relay"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"] == "JD-TEST-001" and body["status"] == "ingested" and body["chunks_indexed"] > 0

    results = retrieval.search("How do I set up the Zephyr lantern relay for marmalade telemetry?", "4.3", 5)
    assert results[0]["meta"]["source_id"] == "JD-TEST-001"  # usable on the very next request, no restart

    rows = {row["source_id"]: row for row in client.get("/sources").json()}
    assert rows["JD-TEST-001"]["file_path"] == "kb/ingested/JD-TEST-001.md"
    assert rows["JD-TEST-001"]["title"] == "Configuring the Zephyr lantern relay"
    assert (temp_env / "data" / "kb" / "ingested" / "JD-TEST-001.md").exists()

    count = retrieval._collection().count()
    again = post(client, "zephyr.md", ARTICLE, meta("JD-TEST-001")).json()
    assert again["status"] == "replaced" and again["chunks_indexed"] == body["chunks_indexed"]
    assert retrieval._collection().count() == count


def test_json_ticket_is_ingested(client):
    response = post(client, "ticket.json", json.dumps(TICKET), meta("JD-TEST-002", doc_type="ticket"))
    assert response.status_code == 200, response.text
    assert response.json()["chunks_indexed"] == 1
    found = [r["meta"]["source_id"] for r in retrieval.search("quokka webhook signature failing", None, 5)]
    assert "JD-TEST-002" in found
    assert "JD-TEST-002" in [row["source_id"] for row in client.get("/sources").json()]


def test_missing_required_field_is_422_naming_it(client):
    metadata = meta("JD-TEST-003")
    del metadata["title"]
    response = post(client, "a.md", ARTICLE, metadata)
    assert response.status_code == 422
    assert ["title"] in [error["loc"] for error in response.json()["detail"]]


@pytest.mark.parametrize("filename, content, metadata, field", [
    ("a.md", ARTICLE, meta("JD-TEST-004", last_updated="06-10-2026"), "last_updated"),   # bad date
    ("a.md", ARTICLE, "{not json", None),                                                   # bad metadata JSON
    ("a.md", ARTICLE, meta("JD-TEST-005", doc_type="ticket"), "filename"),                 # ticket must be .json
    ("t.json", json.dumps({"customer_question": "q"}), meta("JD-TEST-006", doc_type="ticket"), "resolution"),
    ("a.md", ARTICLE, meta("../../evil"), "source_id"),                                    # no path tricks
    ("a.md", b"\xff\xfe bad bytes", meta("JD-TEST-007"), "content"),                       # not UTF-8
])
def test_bad_uploads_are_422(client, filename, content, metadata, field):
    response = post(client, filename, content, metadata)
    assert response.status_code == 422, response.text
    if field:
        assert field in json.dumps(response.json()["detail"])


# A minimal one-page text PDF (Helvetica, one line per entry), built by hand so the test needs no PDF writer.
def make_pdf(lines):
    stream = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               "/Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    return (out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode("latin-1")


PDF_LINES = ["Configuring the Quokka relay", "Overview", "The Quokka relay forwards walrus events to the bus.",
             "Steps", "1. Open Settings and choose Quokka relays.", "2. Click Save relay."]


# A text PDF article is converted to Markdown sections, indexed, cited by its real headings, and both files kept.
def test_pdf_article_is_parsed_into_sections_and_searchable(client, temp_env):
    response = post(client, "relay.pdf", make_pdf(PDF_LINES),
                    meta("JD-TEST-PDF", title="Configuring the Quokka relay"))
    assert response.status_code == 200, response.text
    assert response.json()["chunks_indexed"] == 2
    results = retrieval.search("quokka relay walrus events", None, 3)
    assert results[0]["meta"]["source_id"] == "JD-TEST-PDF"
    assert {r["meta"]["section"] for r in results if r["meta"]["source_id"] == "JD-TEST-PDF"} == {"Overview", "Steps"}
    stored = temp_env / "data" / "kb" / "ingested"
    assert (stored / "JD-TEST-PDF.pdf").exists()
    assert "## Steps\n1. Open Settings and choose Quokka relays." in (stored / "JD-TEST-PDF.md").read_text("utf-8")
    row = {r["source_id"]: r for r in client.get("/sources").json()}["JD-TEST-PDF"]
    assert row["file_path"] == "kb/ingested/JD-TEST-PDF.md"


@pytest.mark.parametrize("content, message", [
    (make_pdf([]), "no extractable text"),        # e.g. a scanned image: nothing to index
    (b"%PDF-1.4 this is not really a pdf", "could not read the PDF"),
])
def test_unreadable_pdf_is_422(client, content, message):
    response = post(client, "scan.pdf", content, meta("JD-TEST-SCAN"))
    assert response.status_code == 422 and message in response.text


def test_pdf_heading_rules():
    assert retrieval._pdf_heading("Troubleshooting") and retrieval._pdf_heading("Applies to:")
    assert not retrieval._pdf_heading("1. Open Settings") and not retrieval._pdf_heading("Click Save relay.")
    assert not retrieval._pdf_heading("and then choose the workflow you want")


# Write a temp source register (Annex B columns + tags) and the files of the rows listed in `with_files`.
def write_register(data_dir, rows, with_files):
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / "source_register.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(SourceMeta.model_fields))
        writer.writeheader()
        for row in rows:
            writer.writerow(SourceMeta(**row).model_dump())
    for row in rows:
        if row["source_id"] in with_files:
            path = data_dir / ingest_kb.file_for(SourceMeta(**row))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(TICKET) if row["doc_type"] == "ticket" else ARTICLE, encoding="utf-8")


def test_ingest_all_loads_once_then_skips_and_force_reloads(temp_env):
    rows = [meta("KB-GS-001"), meta("KB-GS-002"), meta("TKT-2025-0001", doc_type="ticket"), meta("KB-GS-003")]
    write_register(temp_env / "data", rows, with_files={"KB-GS-001", "KB-GS-002", "TKT-2025-0001"})

    first = ingest_kb.ingest_all()
    assert first["ingested"] == 3 and first["skipped"] == 0
    assert first["missing_files"] == ["kb/articles/KB-GS-003.md"]
    assert {row["source_id"] for row in retrieval.list_sources()} == {"KB-GS-001", "KB-GS-002", "TKT-2025-0001"}

    count = retrieval._collection().count()
    second = ingest_kb.ingest_all()
    assert second["ingested"] == 0 and second["skipped"] == 3

    # An edited file is re-indexed on the next startup even when its last_updated date did not change.
    edited = temp_env / "data" / "kb" / "articles" / "KB-GS-002.md"
    edited.write_text(ARTICLE + "\n\n## Notes\n\nAn extra section.\n", encoding="utf-8")
    third = ingest_kb.ingest_all()
    assert third["ingested"] == 1 and third["skipped"] == 2
    count = retrieval._collection().count()

    forced = ingest_kb.ingest_all(force=True)
    assert forced["ingested"] == 3
    assert retrieval._collection().count() == count  # re-ingest replaces chunks, never duplicates them


def test_ingest_all_without_register_is_not_an_error(temp_env):
    assert ingest_kb.ingest_all() == {"ingested": 0, "skipped": 0, "missing_files": [], "invalid_rows": []}


# ---------------------------------------------------------------- review fixes (2026-10-06)

NEW_ARTICLE = "# Rotating zephyr keys (new)\n\n## Steps\n1. Open Admin, then Zephyr keys.\n2. Select Rotate and confirm.\n"
OLD_ARTICLE = "# Rotating zephyr keys (old)\n\n## Steps\n1. Email support and wait for a new zephyr key.\n"


# A superseded article retrieved WITHOUT its replacement is dropped and the replacement is brought in.
def test_supersession_uses_the_register_and_brings_the_replacement(client):
    from app import precedence
    assert post(client, "old.md", OLD_ARTICLE, meta("JD-OLD", title="Rotating zephyr keys (old)",
                                                    last_updated="2025-01-10")).status_code == 200
    assert post(client, "new.md", NEW_ARTICLE, meta("JD-NEW", title="Rotating zephyr keys (new)", supersedes="JD-OLD",
                                                    effective_from="2026-03-01")).status_code == 200
    retrieved = [{**c, "score": 0.8} for c in retrieval.chunks_of("JD-OLD")]  # the search found only the old one
    result = precedence.apply_precedence(retrieved, "4.3", __import__("datetime").date(2026, 10, 6))
    ids = {c["meta"]["source_id"] for c in result["applicable"]}
    assert ids == {"JD-NEW"} and any(c.loser == "JD-OLD" and c.rule == "supersession" for c in result["conflicts"])


# A customer version written as a major line ("4.x") still finds 4.2+ articles.
def test_major_line_customer_version_overlaps(client):
    post(client, "a.md", ARTICLE, meta("JD-VER", title="Zephyr relay", product_versions="4.2+"))
    assert "JD-VER" in {c["meta"]["source_id"] for c in retrieval.search("zephyr lantern relay", "4.x", 3)}
    assert "JD-VER" not in {c["meta"]["source_id"] for c in retrieval.search("zephyr lantern relay", "3.x", 3)}


# A UTF-8 byte-order mark (PowerShell's UTF8 encoding) does not hide the first heading, and a BOM ticket loads.
def test_bom_does_not_change_the_first_section(client):
    assert post(client, "bom.md", b"\xef\xbb\xbf## Steps\n1. Open the quokka panel.\n", meta("JD-BOM")).status_code == 200
    assert {c["meta"]["section"] for c in retrieval.chunks_of("JD-BOM")} == {"Steps"}
    ticket = b"\xef\xbb\xbf" + json.dumps(TICKET).encode()
    assert post(client, "t.json", ticket, meta("JD-BOMT", doc_type="ticket")).status_code == 200


# In a single-font PDF, a line that only continues a sentence is not a heading.
def test_pdf_wrapped_line_is_not_a_heading(client, temp_env):
    lines = ["Overview", "The quokka relay forwards walrus events in the current plan window, including",
             "Business and Enterprise", "workspaces.", "Steps", "1. Open Settings."]
    assert post(client, "w.pdf", make_pdf(lines), meta("JD-WRAP", title="Quokka relay")).status_code == 200
    markdown = (temp_env / "data" / "kb" / "ingested" / "JD-WRAP.md").read_text("utf-8")
    assert "## Business and Enterprise" not in markdown and "## Steps" in markdown


# A register row edited without touching the file (e.g. a new deprecated_on) is re-indexed; a row removed
# from the register is removed from the index, while live uploads stay.
def test_startup_ingest_follows_register_edits_and_removals(temp_env):
    rows = [meta("KB-GS-001"), meta("KB-GS-002")]
    write_register(temp_env / "data", rows, with_files={"KB-GS-001", "KB-GS-002"})
    assert ingest_kb.ingest_all()["ingested"] == 2
    write_register(temp_env / "data", [meta("KB-GS-001", deprecated_on="2026-10-01")], with_files={"KB-GS-001"})
    second = ingest_kb.ingest_all()
    assert second["ingested"] == 1 and second["removed"] == ["KB-GS-002"]
    assert {c["meta"]["deprecated_on"] for c in retrieval.chunks_of("KB-GS-001")} == {"2026-10-01"}
    assert retrieval.chunks_of("KB-GS-002") == []


# Metadata JSON with null optional fields, a list of tags or a boolean "synthetic" is accepted (not a 422).
def test_ingest_metadata_accepts_common_json_shapes(client):
    metadata = meta("JD-SHAPES", effective_from=None, deprecated_on=None, supersedes=None,
                    tags=["zephyr", "relay"], synthetic=False, product_versions="4.0–4.3")
    assert post(client, "a.md", ARTICLE, metadata).status_code == 200
    row = {r["source_id"]: r for r in client.get("/sources").json()}["JD-SHAPES"]
    assert row["tags"] == "zephyr;relay" and row["synthetic"] == "N" and row["effective_from"] == ""

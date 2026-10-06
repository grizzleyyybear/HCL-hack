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

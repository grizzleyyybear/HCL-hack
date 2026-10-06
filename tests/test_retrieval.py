"""Tests for app/retrieval.py: version parsing, chunking, metadata, ingest and version-filtered search.

Uses a tiny fixture KB written here (not data/kb) and a Chroma folder in pytest's tmp_path.
The embedding model is cached inside app.retrieval, so it loads only once for the whole module.
"""
import json

import pytest

from app import retrieval
from app.schemas import SourceMeta

EXPORT_4X = """# Exporting workflow run history

## Overview
Download the run history of a workflow as a file.

## Steps
1. Open Workflows and select the workflow.
2. Open the Runs tab.
3. Click Export and choose CSV or JSON.

## Applies to
CloudFlow 4.2 and later.
"""

EXPORT_3X = """# Exporting workflow run history in CloudFlow 3.x

## Steps
1. Open Settings in the left sidebar.
2. Open Run history.
3. Click Download CSV (last 30 days).
"""

CF503 = """# Salesforce step fails with CF-503

CF-503 means the Salesforce connector authorisation expired.

## Steps in CloudFlow 4.x
Open Connectors, select Salesforce, then Re-authorise.

## Steps in CloudFlow 3.x
Open Settings, Connections, then Reconnect. Never disable SSL verification.
"""

COMMUNITY = """# Disable SSL verification to fix CF-503

## Question
My Salesforce step fails with CF-503.

## Accepted answer
Turn off SSL verification for the connector.
"""

TICKET = {"source_id": "TKT-2025-0455", "customer_question": "How can I export my workflow run history to CSV?",
          "intent": "how_to", "resolution": "Support emailed the customer a CSV export of their run history.",
          "tags": ["export", "run-history"], "resolved_at": "2025-05-02", "product_version": "4.1"}


# Build SourceMeta with sensible defaults so each fixture document only states what matters.
def make_meta(source_id, doc_type="article", title="Title", versions="ALL", **extra):
    authority = {"article": 1, "policy": 1, "release_note": 2, "ticket": 4, "community": 5}[doc_type]
    return SourceMeta(source_id=source_id, doc_type=doc_type, title=title, authority_level=authority,
                      product_versions=versions, last_updated="2026-09-10", **extra)


FIXTURE = [
    (EXPORT_4X, make_meta("KB-ADV-007", title="Exporting workflow run history", versions="4.2+")),
    (EXPORT_3X, make_meta("KB-ADV-007-3X", title="Exporting workflow run history in CloudFlow 3.x", versions="3.x")),
    (CF503, make_meta("KB-TRB-004", title="Salesforce step fails with CF-503", tags="salesforce;CF-503")),
    (json.dumps(TICKET), make_meta("TKT-2025-0455", doc_type="ticket", title="Exporting run history", versions="ALL")),
    (COMMUNITY, make_meta("COM-0004", doc_type="community", title="Disable SSL verification to fix CF-503")),
]


# Point retrieval at an empty Chroma folder for this test (never the repo's .chroma).
@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))


# An isolated store holding the five fixture documents.
@pytest.fixture
def kb(empty_store):
    for content, meta in FIXTURE:
        retrieval.ingest_document(content, meta)


@pytest.mark.parametrize("text, expected", [
    ("4.2+", (402, 9999)), ("4.2 +", (402, 9999)), ("3.x", (300, 399)), ("3.X", (300, 399)),
    ("4.0-4.3", (400, 403)), ("4.0 - 4.3", (400, 403)), ("ALL", (0, 9999)), ("all", (0, 9999)),
    ("", (0, 9999)), ("4.3", (403, 403)), (" 4.4 ", (404, 404)),
])
def test_parse_versions(text, expected):
    assert retrieval.parse_versions(text) == expected


def test_version_code_orders_minor_numerically():
    assert retrieval.version_code("4.3") == 403
    assert retrieval.version_code("4.10") > retrieval.version_code("4.9")


def test_chunk_article_one_chunk_per_section():
    chunks = retrieval.chunk_article(EXPORT_4X, FIXTURE[0][1])
    assert [c["meta"]["section"] for c in chunks] == ["Overview", "Steps", "Applies to"]
    assert chunks[1]["chunk_id"] == "KB-ADV-007::Steps::0"
    assert chunks[1]["text"].startswith("Exporting workflow run history\n## Steps\n")
    assert not any(c["text"].endswith("# Exporting workflow run history") for c in chunks)


def test_text_before_first_section_becomes_overview_only_when_present():
    sections = [c["meta"]["section"] for c in retrieval.chunk_article(CF503, FIXTURE[2][1])]
    assert sections == ["Overview", "Steps in CloudFlow 4.x", "Steps in CloudFlow 3.x"]
    sections = [c["meta"]["section"] for c in retrieval.chunk_article(EXPORT_3X, FIXTURE[1][1])]
    assert sections == ["Steps"]


def test_long_section_is_split_with_overlap():
    body = " ".join(f"word{i}" for i in range(400))  # ~3,000 characters
    chunks = retrieval.chunk_article(f"# Long\n\n## Details\n{body}\n", make_meta("KB-ADV-099", title="Long"))
    assert len(chunks) >= 4
    assert [c["chunk_id"] for c in chunks[:2]] == ["KB-ADV-099::Details::0", "KB-ADV-099::Details::1"]
    pieces = [c["text"].split("\n", 2)[2] for c in chunks]  # drop the title and heading lines
    assert all(len(p) <= retrieval.CHUNK_SIZE for p in pieces)
    assert pieces[0][-retrieval.CHUNK_OVERLAP:] == pieces[1][:retrieval.CHUNK_OVERLAP]


def test_ticket_is_one_chunk():
    chunks = retrieval.chunk_ticket(TICKET, FIXTURE[3][1])
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "TKT-2025-0455::Ticket::0"
    assert chunks[0]["meta"]["section"] == "Ticket"
    assert chunks[0]["text"].startswith("Customer question: How can I export")
    assert "\nResolution: Support emailed" in chunks[0]["text"]


def test_metadata_has_every_field_and_no_none():
    fields = {"source_id", "doc_type", "title", "section", "authority_level", "product_versions", "version_min",
              "version_max", "last_updated", "effective_from", "deprecated_on", "supersedes", "tags", "synthetic"}
    for content, meta in FIXTURE:
        chunks = (retrieval.chunk_ticket(json.loads(content), meta) if meta.doc_type == "ticket"
                  else retrieval.chunk_article(content, meta))
        for chunk in chunks:
            assert set(chunk["meta"]) == fields
            assert None not in chunk["meta"].values()
            assert all(isinstance(chunk["meta"][k], int) for k in ("authority_level", "version_min", "version_max"))


def test_reingest_replaces_chunks(kb):
    before = retrieval._collection().count()
    assert retrieval.ingest_document(EXPORT_4X, FIXTURE[0][1]) == 3
    assert retrieval._collection().count() == before
    shorter = "# Exporting workflow run history\n\n## Steps\nWorkflows, Runs tab, Export.\n"
    assert retrieval.ingest_document(shorter, FIXTURE[0][1]) == 1
    assert retrieval._collection().count() == before - 2


# Return the source_ids of the search results, in order.
def ids(results):
    return [r["meta"]["source_id"] for r in results]


def test_search_version_3_8_gets_3x_article_only(kb):
    found = ids(retrieval.search("How do I export my workflow run history?", "3.8", 5))
    assert "KB-ADV-007-3X" in found
    assert "KB-ADV-007" not in found


def test_search_version_4_3_gets_4x_article_only(kb):
    found = ids(retrieval.search("How do I export my workflow run history?", "4.3", 5))
    assert "KB-ADV-007" in found
    assert "KB-ADV-007-3X" not in found


def test_search_returns_docs_first_then_tickets(kb):
    results = retrieval.search("Export run history CSV", None, 5)
    types = [r["meta"]["doc_type"] for r in results]
    assert "article" in types and "ticket" in types
    first_other = min(i for i, t in enumerate(types) if t in ("ticket", "community"))
    assert all(t in ("ticket", "community") for t in types[first_other:])  # docs block, then others block
    docs = [r["score"] for r in results[:first_other]]
    assert docs == sorted(docs, reverse=True)
    assert len(results[first_other:]) <= retrieval.OTHER_TOP_K
    assert results[0]["chunk_id"].startswith("KB-ADV-007")


def test_search_empty_collection_returns_empty_list(empty_store):
    assert retrieval.search("anything", "4.3", 5) == []
    assert retrieval.health() is True


def test_collection_name_slug():
    assert retrieval._collection_name("sentence-transformers/all-MiniLM-L6-v2") == "kb_all_minilm_l6_v2"
    assert retrieval._collection_name("BAAI/bge-small-en-v1.5") == "kb_bge_small_en_v1_5"


# A section heading naming a major version ("... 3.x") narrows that chunk to that version (orchestrator fix).
def test_section_heading_narrows_version_range():
    from app.retrieval import chunk_article
    from app.schemas import SourceMeta
    meta = SourceMeta(source_id="KB-TRB-004", doc_type="article", title="Salesforce step fails with CF-503",
                      authority_level=1, product_versions="ALL", last_updated="2026-06-30")
    md = ("# Salesforce step fails with CF-503\n\n## Overview\nWhy it happens.\n\n"
          "## Steps in CloudFlow 4.x\nConnectors, Re-authorise.\n\n## Steps in CloudFlow 3.x\nSettings, Reconnect.\n")
    ranges = {c["meta"]["section"]: (c["meta"]["version_min"], c["meta"]["version_max"]) for c in chunk_article(md, meta)}
    assert ranges["Overview"] == (0, 9999)
    assert ranges["Steps in CloudFlow 4.x"] == (400, 499)
    assert ranges["Steps in CloudFlow 3.x"] == (300, 399)

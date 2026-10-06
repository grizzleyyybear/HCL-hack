"""Knowledge-base retrieval over a persistent ChromaDB collection.

Owners: A4 retrieval-core (parse_versions, version_code, chunk_article, chunk_ticket, ingest_document,
search, health) and A5 ingest-api (ingest_upload, list_sources). Signatures are frozen.

Chunk format (BUILD_PLAN 3.4):
{"chunk_id": "KB-ADV-007::Steps::0", "text": "...", "score": 0.82,
 "meta": {"source_id", "doc_type", "title", "section", "authority_level": int,
          "product_versions", "version_min": int, "version_max": int, "last_updated",
          "effective_from", "deprecated_on", "supersedes", "tags", "synthetic"}}
Version codes are major*100 + minor: "4.3" -> 403, "3.x" -> (300, 399), "4.2+" -> (402, 9999),
"4.0-4.3" -> (400, 403), "ALL" -> (0, 9999).
"""
import json
import pathlib
import re

from pydantic import BaseModel, Field, field_validator

from app import db
from app.config import settings
from app.schemas import SourceMeta

CHUNK_SIZE = 800      # max characters of section text per chunk
CHUNK_OVERLAP = 100   # characters repeated between neighbouring pieces of a long section
DOC_TYPES = ["article", "policy", "release_note"]  # authoritative docs, searched with top_k
OTHER_TYPES = ["ticket", "community"]               # historical / untrusted, searched with top 3
OTHER_TOP_K = 3

_models = {}       # embedding model name -> loaded SentenceTransformer
_collections = {}  # (CHROMA_DIR, EMBED_MODEL) -> Chroma collection


# Parse a product_versions string such as "4.2+", "3.x", "4.0-4.3" or "ALL" into (min, max) codes.
def parse_versions(s: str) -> tuple[int, int]:
    s = (s or "").strip().lower().replace(" ", "").replace("–", "-")  # en dash -> hyphen
    if s in ("", "all"):
        return (0, 9999)
    if s.endswith("+"):
        return (version_code(s[:-1]), 9999)
    if "-" in s:
        low, high = s.split("-", 1)
        return (parse_versions(low)[0], parse_versions(high)[1])
    if s.endswith(".x"):
        major = int(s[:-2])
        return (major * 100, major * 100 + 99)
    code = version_code(s)
    return (code, code)


# Turn a single version like "4.3" into its integer code 403 (so "4.10" -> 410 sorts above "4.9" -> 409).
def version_code(v: str) -> int:
    parts = v.strip().lower().lstrip("v").split(".")
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return int(parts[0]) * 100 + minor


# Split a Markdown article into chunks: one per "## " section, long sections split with overlap.
def chunk_article(markdown: str, meta: SourceMeta) -> list[dict]:
    sections = []  # list of (heading, body lines)
    heading, lines, title_seen = "Overview", [], False
    for line in markdown.splitlines():
        if line.startswith("## "):
            sections.append((heading, lines))
            heading, lines = line[3:].strip(), []
        elif line.startswith("# ") and not title_seen:
            title_seen = True  # the "# Title" line is not content
        else:
            lines.append(line)
    sections.append((heading, lines))

    chunks, seen = [], {}
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue  # e.g. no text before the first "## "
        for piece in _split(body):
            n = seen.get(heading, 0)  # keeps chunk_ids unique even if a heading repeats
            seen[heading] = n + 1
            chunks.append({
                "chunk_id": f"{meta.source_id}::{heading}::{n}",
                "text": f"{meta.title}\n## {heading}\n{piece}",
                "meta": _chunk_meta(meta, heading),
            })
    return chunks


# Cut a long section into ~800-character pieces overlapping by ~100 characters, so nothing is lost at a cut.
def _split(body: str) -> list[str]:
    pieces, start = [], 0
    while True:
        pieces.append(body[start:start + CHUNK_SIZE])
        if start + CHUNK_SIZE >= len(body):
            return pieces
        start += CHUNK_SIZE - CHUNK_OVERLAP


# Turn one ticket (the dict from its JSON file) into a single chunk: the question plus how it was resolved.
def chunk_ticket(ticket: dict, meta: SourceMeta) -> list[dict]:
    text = f"Customer question: {ticket.get('customer_question', '')}\nResolution: {ticket.get('resolution', '')}"
    return [{"chunk_id": f"{meta.source_id}::Ticket::0", "text": text, "meta": _chunk_meta(meta, "Ticket")}]


# A section heading that names one major version, e.g. "Steps in CloudFlow 3.x" -> "3.x".
SECTION_VERSION = re.compile(r"\b(\d+)\.x\b", re.IGNORECASE)


# Build the flat metadata dict Chroma stores for every chunk; no None values (Chroma rejects them).
# A section whose heading names a major version is narrowed to it, so a 4.3 customer never gets
# the "Steps in CloudFlow 3.x" section of an article that covers ALL versions.
def _chunk_meta(meta: SourceMeta, section: str) -> dict:
    version_min, version_max = parse_versions(meta.product_versions)
    named = SECTION_VERSION.findall(section)
    if len(named) == 1:
        major_min, major_max = parse_versions(f"{named[0]}.x")
        version_min, version_max = max(version_min, major_min), min(version_max, major_max)
    return {
        "source_id": meta.source_id, "doc_type": meta.doc_type, "title": meta.title, "section": section,
        "authority_level": int(meta.authority_level), "product_versions": meta.product_versions,
        "version_min": version_min, "version_max": version_max, "last_updated": meta.last_updated,
        "effective_from": meta.effective_from or "", "deprecated_on": meta.deprecated_on or "",
        "supersedes": meta.supersedes or "", "tags": meta.tags or "", "synthetic": meta.synthetic or "",
    }


# Index one document (article Markdown or ticket JSON text) and return how many chunks were stored.
# Does not touch SQLite: the sources table is written by ingest_upload / scripts/ingest_kb.py.
def ingest_document(content: str, meta: SourceMeta) -> int:
    if meta.doc_type == "ticket":
        chunks = chunk_ticket(json.loads(content), meta)
    else:
        chunks = chunk_article(content, meta)  # articles, policies, release notes, community posts
    collection = _collection()
    collection.delete(where={"source_id": meta.source_id})  # re-ingest replaces the old chunks
    if chunks:
        texts = [c["text"] for c in chunks]
        collection.add(ids=[c["chunk_id"] for c in chunks], documents=texts,
                       metadatas=[c["meta"] for c in chunks], embeddings=_embed(texts))
    return len(chunks)


# Rules for an uploaded file. Breaking one raises pydantic.ValidationError, which main.py turns into a 422.
class _Upload(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")  # becomes a file name: no slashes, no ".."
    doc_type: str
    filename: str
    content: str = Field(min_length=1)  # the file as text

    # Tickets must be .json files; articles, policies, release notes and community posts must be .md.
    @field_validator("filename")
    @classmethod
    def _extension_matches_doc_type(cls, filename: str, info):
        doc_type = info.data["doc_type"]
        expected = ".json" if doc_type == "ticket" else ".md"
        if pathlib.Path(filename).suffix.lower() != expected:
            raise ValueError(f"a {doc_type} upload must be a {expected} file")
        return filename

    # The file must be UTF-8 text; ingest_upload decodes with errors="replace", so bad bytes show up as U+FFFD.
    @field_validator("content")
    @classmethod
    def _is_utf8(cls, content: str):
        if "�" in content:
            raise ValueError("file must be UTF-8 text")
        return content


# A ticket JSON file must at least hold the customer's question and how it was resolved.
class _TicketFile(BaseModel):
    customer_question: str
    resolution: str


# Handle the POST /ingest upload: validate metadata, store the file, index it, record it in sources.
def ingest_upload(file_bytes: bytes, filename: str, metadata_json: str) -> dict:
    meta = SourceMeta.model_validate(json.loads(metadata_json))  # bad JSON or fields -> 422 in main.py
    upload = _Upload(source_id=meta.source_id, doc_type=meta.doc_type, filename=filename,
                     content=file_bytes.decode("utf-8", errors="replace"))
    if meta.doc_type == "ticket":
        _TicketFile.model_validate_json(upload.content)
    rel_path = pathlib.Path("kb", "ingested", meta.source_id + pathlib.Path(filename).suffix.lower())
    full_path = pathlib.Path(settings.DATA_DIR) / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(file_bytes)  # keep exactly what was uploaded
    chunks = ingest_document(upload.content, meta)  # searchable from the very next request
    existed = upsert_source(meta, rel_path.as_posix())
    return {"source_id": meta.source_id, "chunks_indexed": chunks, "status": "replaced" if existed else "ingested"}


# Insert or update one sources row (Annex B fields + tags + file_path relative to DATA_DIR).
# Returns True when the source_id was already there. Also used by scripts/ingest_kb.py.
def upsert_source(meta: SourceMeta, file_path: str) -> bool:
    row = {**meta.model_dump(), "file_path": file_path}
    with db.connect() as conn:
        existed = conn.execute("SELECT 1 FROM sources WHERE source_id = ?", (meta.source_id,)).fetchone()
        conn.execute(f"INSERT OR REPLACE INTO sources ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                     list(row.values()))
    return existed is not None


# Return every row of the source register (seeded and live-ingested) for GET /sources.
def list_sources() -> list[dict]:
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY source_id")]


# Search docs (top_k) and tickets/community (top 3), filtered by the customer's version when known.
def search(query: str, customer_version: str | None, top_k: int) -> list[dict]:
    collection = _collection()
    if collection.count() == 0:
        return []
    version_filter = []
    if customer_version:
        try:
            v = version_code(customer_version)
            version_filter = [{"version_min": {"$lte": v}}, {"version_max": {"$gte": v}}]
        except ValueError:
            pass  # unreadable version text: search without a version filter
    embedding = _embed([query])
    docs = _query(collection, embedding, DOC_TYPES, version_filter, top_k)
    others = _query(collection, embedding, OTHER_TYPES, version_filter, OTHER_TOP_K)
    return docs + others


# Run one filtered Chroma query and return chunks in the BUILD_PLAN 3.4 format, best score first.
def _query(collection, embedding: list, doc_types: list[str], version_filter: list[dict], n: int) -> list[dict]:
    conditions = [{"doc_type": {"$in": doc_types}}] + version_filter
    where = conditions[0] if len(conditions) == 1 else {"$and": conditions}
    result = collection.query(query_embeddings=embedding, n_results=n, where=where)
    chunks = [
        {"chunk_id": chunk_id, "text": text, "score": round(1 - distance, 4), "meta": meta}
        for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                                  result["metadatas"][0], result["distances"][0])
    ]
    return sorted(chunks, key=lambda c: c["score"], reverse=True)


# Return True when the Chroma collection can be opened (used by GET /health).
def health() -> bool:
    try:
        _collection().count()
        return True
    except Exception:  # noqa: BLE001 - health must answer, not crash
        return False


# Load the embedding model once per model name (slow, so cached for the life of the process).
def _model():
    name = settings.EMBED_MODEL
    if name not in _models:
        from sentence_transformers import SentenceTransformer  # lazy: torch is slow to import
        _models[name] = SentenceTransformer(name)
    return _models[name]


# Embed texts as unit vectors so cosine distance is meaningful; returns plain lists for Chroma.
def _embed(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True).tolist()


# "sentence-transformers/all-MiniLM-L6-v2" -> "kb_all_minilm_l6_v2": one collection per model, never mixed.
def _collection_name(model_name: str) -> str:
    return "kb_" + re.sub(r"[^a-z0-9]+", "_", model_name.split("/")[-1].lower()).strip("_")


# Open (or create) the persistent cosine collection for the current CHROMA_DIR + EMBED_MODEL, cached per pair.
def _collection():
    key = (settings.CHROMA_DIR, settings.EMBED_MODEL)
    if key not in _collections:
        import chromadb  # lazy: keeps "import app.retrieval" fast for tests that never search
        client = chromadb.PersistentClient(path=settings.CHROMA_DIR,
                                           settings=chromadb.config.Settings(anonymized_telemetry=False))
        _collections[key] = client.get_or_create_collection(
            _collection_name(settings.EMBED_MODEL), metadata={"hnsw:space": "cosine"}, embedding_function=None)
    return _collections[key]

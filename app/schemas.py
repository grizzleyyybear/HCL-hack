"""Pydantic models. Field names here ARE the API contract from the guide: do not rename them."""
import datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Accepted product_versions formats (see retrieval.parse_versions): ALL, 4.3, 3.x, 4.2+, 4.0-4.3.
VERSIONS_FORMAT = re.compile(r"^\s*(?:all|\d+\.(?:\d+|x)\s*\+?(?:\s*[-\u2013]\s*\d+\.(?:\d+|x))?)\s*$", re.IGNORECASE)

AnswerType = Literal["answered", "clarification_needed", "escalated", "not_found", "refused", "out_of_scope"]


class SupportRequest(BaseModel):
    """Body of POST /support. The account never comes from here, only from the X-Account-Id header."""
    message: str
    conversation_id: str | None = None
    channel: str | None = None
    product_version: str | None = None
    as_of_date: datetime.date | None = None

    # A sane date window keeps date arithmetic (look-back windows) from overflowing on "0001-01-01".
    @field_validator("as_of_date")
    @classmethod
    def _sane_date(cls, value):
        if value is not None and not datetime.date(2000, 1, 1) <= value <= datetime.date(2100, 12, 31):
            raise ValueError("as_of_date must be between 2000-01-01 and 2100-12-31")
        return value


class Intent(BaseModel):
    """Classifier output (R1). Defaults make a safe fallback easy to build."""
    type: Literal["how_to", "troubleshooting", "account", "billing", "complaint", "security", "out_of_scope"]
    subtype: str | None = None
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    sentiment: Literal["positive", "neutral", "negative", "angry"] = "neutral"
    product_version: str | None = None
    pii_detected: bool = False
    explicit_human_request: bool = False
    repeated_contact: bool = False
    tools_needed: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    is_vague: bool = False


class Draft(BaseModel):
    """Composer output: the answer text plus the chunk_ids it relies on (code checks they were retrieved)."""
    answer: str
    cited_chunk_ids: list[str] = Field(default_factory=list)


STEP_LINE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
ANNOUNCES_STEPS = re.compile(r"\b(?:these|the following|below)\s+steps\b", re.IGNORECASE)


class LLMDraft(Draft):
    """What the LLM composer must return. A 7B model sometimes writes only "...follow these steps:" and stops;
    rejecting that triggers call_json's retry (with this error) and then the template fallback."""

    @field_validator("answer")
    @classmethod
    def _steps_included(cls, value: str):
        text = value.strip()
        if not text:
            raise ValueError("the answer is empty")
        if (text.endswith(":") or ANNOUNCES_STEPS.search(text)) and not STEP_LINE.search(text):
            raise ValueError("the answer announces steps but does not contain them; put every numbered step "
                             "inside the answer string, separated by \n")
        return value


class Critique(BaseModel):
    """Critic output (R4). Scores only; code makes the final decision."""
    groundedness: float = Field(ge=0, le=1)
    coverage: Literal["complete", "partial", "none"]
    pii_risk: Literal["none", "low", "high"] = "none"
    policy_risk: Literal["none", "promise_made", "unauthorised_action"] = "none"
    decision: Literal["answer", "revise", "escalate"]
    issues: list[str] = Field(default_factory=list)


class DisagreementResult(BaseModel):
    pair_id: str
    disagree: bool


class Disagreements(BaseModel):
    """Output of the one batched yes/no check used by precedence.py."""
    results: list[DisagreementResult] = Field(default_factory=list)


class Citation(BaseModel):
    source_id: str
    doc_type: str
    section: str
    product_versions: str
    last_updated: str


class ToolCall(BaseModel):
    """One tool invocation, as recorded in the audit and in tools_invoked."""
    tool: str
    input: dict = Field(default_factory=dict)
    output: dict | list = Field(default_factory=dict)
    status: Literal["ok", "error"] = "ok"
    ms: int = 0


class Conflict(BaseModel):
    winner: str
    loser: str
    rule: Literal["authority", "supersession", "recency", "deprecation"]


class HandoffBundle(BaseModel):
    """Annex D handoff bundle. Always redacted before it is stored or returned."""
    queue: str
    priority: str
    intent: str
    urgency: str
    sentiment: str
    escalation_reasons: list[str]
    customer_summary: str
    evidence: list[dict] = Field(default_factory=list)
    attempted_answer: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)
    pii_redacted: bool = True


class SupportResponse(BaseModel):
    """Response of POST /support (guide 6.1). Every answer_type returns every field."""
    trace_id: str
    conversation_id: str
    answer_type: AnswerType
    answer: str
    intent: dict = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[dict] = Field(default_factory=list)
    critic: dict | None = None
    conflicts_detected: list[Conflict] = Field(default_factory=list)
    handoff_id: str | None = None
    handoff: HandoffBundle | None = None
    as_of_date: datetime.date


class SourceMeta(BaseModel):
    """Annex B source register fields; also the metadata JSON of POST /ingest. Accepts judge JD- IDs."""
    source_id: str = Field(min_length=1)
    doc_type: Literal["article", "policy", "release_note", "ticket", "community"]
    title: str = Field(min_length=1)
    authority_level: int = Field(ge=1, le=5)
    product_versions: str = Field(min_length=1)
    last_updated: str
    effective_from: str = ""
    deprecated_on: str = ""
    supersedes: str = ""
    provenance: str = ""
    synthetic: str = "Y"
    tags: str = ""  # extra column (allowed): semicolon-separated topic keys, e.g. "salesforce;CF-503"

    # Common JSON shapes for optional fields: null -> "", a list of tags -> "a;b", true/false -> "Y"/"N".
    @field_validator("effective_from", "deprecated_on", "supersedes", "provenance", "synthetic", "tags", mode="before")
    @classmethod
    def _plain_text(cls, value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Y" if value else "N"
        if isinstance(value, (list, tuple)):
            return ";".join(str(v).strip() for v in value)
        return str(value)

    # Dates must be YYYY-MM-DD; optional date fields may be empty.
    @field_validator("last_updated", "effective_from", "deprecated_on")
    @classmethod
    def _check_date(cls, value: str, info):
        if value == "" and info.field_name != "last_updated":
            return value
        datetime.date.fromisoformat(value)
        return value

    # product_versions must be a format retrieval can parse: ALL, 4.3, 3.x, 4.2+ or 4.0-4.3 (else a clear 422).
    @field_validator("product_versions")
    @classmethod
    def _check_versions(cls, value: str):
        if not VERSIONS_FORMAT.match(value):
            raise ValueError("use ALL, a version like 4.3, a major line like 3.x, a minimum like 4.2+ or a range like 4.0-4.3")
        return value.strip()

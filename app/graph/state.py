"""The LangGraph state passed between pipeline nodes (the keys each node reads and writes)."""
import datetime
from typing import Any, TypedDict


class State(TypedDict, total=False):
    # request
    account_id: str | None
    conversation_id: str
    message_redacted: str
    as_of_date: datetime.date
    product_version: str | None
    plan: str | None
    # pipeline results
    intent: Any                 # schemas.Intent
    tool_results: list[dict]    # ToolCall dicts
    retrieved_chunks: list[dict]
    applicable_chunks: list[dict]
    conflicts: list[dict]
    upcoming_changes: list[str]
    unresolved: list
    draft: Any                  # schemas.Draft
    citations: list[dict]
    critique: Any               # schemas.Critique
    revisions: int
    decision: str
    escalation_reasons: list[str]
    answer_type: str
    answer: str
    handoff_id: str | None
    handoff: dict | None
    # observability
    trace: Any                  # audit.Trace
    audit: list[dict]

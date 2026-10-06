"""Handoff tool. Owner: A7 tools-policy."""
import datetime
import json

from app import db, safety


# Redact the bundle, store it in the handoffs table and return {"handoff_id": "H-0001"}.
def create_handoff(conversation_id: str, account_id: str | None, queue: str, priority: str,
                   bundle: dict) -> dict:
    if hasattr(bundle, "model_dump"):  # also accept a schemas.HandoffBundle
        bundle = bundle.model_dump()
    # No fallback on purpose: if redaction is unavailable we refuse to store PII (run_tool reports the error).
    redacted = safety.redact_obj({**bundle, "pii_redacted": True})
    handoff_id = db.next_id("H")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.execute("INSERT INTO handoffs VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (handoff_id, conversation_id, account_id, queue, priority, created_at,
                      json.dumps(redacted, default=str)))
    return {"handoff_id": handoff_id}

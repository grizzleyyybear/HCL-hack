"""Escalation Policy (Annex A.3) in plain code, plus routing and the handoff bundle. Owner: A9 escalation.

The LLM never decides here: the critic only gives scores and these functions apply the policy.
Every threshold (critic minimum, SLA hours, repeat-contact count) is read from policy_registry.
"""
import datetime

from app import db, safety
from app.schemas import Critique, HandoffBundle, Intent

# Intent subtypes that always go to the billing team (refund, credit, billing dispute, duplicate charge).
BILLING_SUBTYPES = ("refund", "credit", "dispute", "duplicate_charge")

_PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
_TEAM_NAMES = {"billing": "billing team", "security": "security team", "legal": "legal team",
               "technical": "technical support team"}


# True when a tool call failed: status "error" or an "error" key in its output.
# account_not_found is a valid answer (unknown header account -> general questions only), not a failure.
def _tool_failed(result: dict) -> bool:
    output = result.get("output")
    has_error_key = isinstance(output, dict) and "error" in output
    if has_error_key and output["error"] == "account_not_found":
        return False
    return result.get("status") == "error" or has_error_key


# Apply every A.3 rule (one `if` each). Returns ("answer" | "revise" | "escalate", reasons).
def decide(intent: Intent, critique: Critique, tool_results: list[dict], revisions: int,
           kb_gap_needs_outcome: bool, unresolved_conflicts: list, answer_text: str,
           as_of_date: datetime.date | None = None) -> tuple[str, list[str]]:
    min_groundedness = float(db.get_policy("critic_min_groundedness", as_of_date=as_of_date)[0])
    weak = critique is not None and critique.groundedness < min_groundedness
    promised = safety.makes_promise(answer_text or "")

    reasons = []
    if intent.subtype in BILLING_SUBTYPES:
        reasons.append("billing_dispute")
    if intent.subtype == "legal":
        reasons.append("legal_matter")
    if intent.subtype == "deletion":
        reasons.append("account_deletion")
    # password_reset is handled by the tool and answered; only a compromise (or other security issue) escalates
    if intent.type == "security" and intent.subtype != "password_reset":
        reasons.append("security_incident")
    if intent.explicit_human_request:
        reasons.append("explicit_human_request")
    if intent.sentiment in ("negative", "angry") and intent.repeated_contact:
        reasons.append("repeated_contact")
    if any(_tool_failed(r) for r in tool_results):
        reasons.append("tool_failure")
    if kb_gap_needs_outcome:
        reasons.append("kb_gap_needs_outcome")
    if unresolved_conflicts:
        reasons.append("unresolved_conflict")
    if revisions >= 1 and weak:
        reasons.append("low_groundedness")
    if revisions >= 1 and promised:
        reasons.append("promise_made")
    if reasons:
        return "escalate", reasons

    # At most one revision: a weak first draft goes back to compose once, never twice.
    needs_revision = (critique is not None and critique.decision == "revise") or weak or promised
    if needs_revision and revisions == 0:
        return "revise", []
    return "answer", []


# True when the account already had >= repeat_contact_threshold conversations in the 30 days up to as_of_date.
# The pipeline OR-s this into intent.repeated_contact; pass the current conversation_id so it is not counted.
def repeated_contact_from_history(account_id: str | None, as_of_date, exclude_conversation_id: str | None = None) -> bool:
    if not account_id:
        return False
    threshold = int(db.get_policy("repeat_contact_threshold", as_of_date=as_of_date)[0])
    as_of = datetime.date.fromisoformat(str(as_of_date)) if as_of_date else datetime.date.today()
    start = as_of - datetime.timedelta(days=30)
    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE account_id = ? AND conversation_id != ? "
            "AND substr(created_at, 1, 10) BETWEEN ? AND ?",
            (account_id, exclude_conversation_id or "", start.isoformat(), as_of.isoformat()),
        ).fetchone()[0]
    return count >= threshold


# The queue for the customer's own topic: billing, security, or technical for everything else.
def _intent_queue(intent: Intent) -> str:
    if intent.type == "security":
        return "security"
    if intent.type == "billing" or intent.subtype in BILLING_SUBTYPES:
        return "billing"
    return "technical"


# (queue, priority) for one escalation reason, straight from the CLAUDE.md routing table.
def _route_one(reason: str, intent: Intent) -> tuple[str, str]:
    if reason in ("security_incident", "account_deletion"):
        return "security", "urgent"
    if reason == "billing_dispute":
        return "billing", "high"
    if reason == "legal_matter":
        return "legal", "high"
    if reason in ("explicit_human_request", "repeated_contact", "promise_made"):
        return _intent_queue(intent), "high"
    return "technical", "normal"  # low_groundedness, kb_gap_needs_outcome, unresolved_conflict, tool_failure


# Pick (queue, priority) for the escalation reasons; the highest priority wins (first reason on a tie).
def route(reasons: list[str], intent: Intent) -> tuple[str, str]:
    routes = [_route_one(r, intent) for r in reasons] or [("technical", "normal")]
    return max(routes, key=lambda queue_priority: _PRIORITY_RANK[queue_priority[1]])


# Collapse whitespace and cut text to n characters, adding "..." when it was longer.
def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


# Every invoice ID found anywhere inside a tool value (works for ["INV-1", ...], [[...]] or [{"invoice_id": ...}]).
def _invoice_ids(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("INV") else []
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return list(dict.fromkeys(i for item in value for i in _invoice_ids(item)))
    return []


# The section of a source as it was retrieved (for evidence entries of conflicting sources).
def _section_of(source_id: str, chunks: list[dict]) -> str:
    return next((c["meta"].get("section", "") for c in chunks if c["meta"].get("source_id") == source_id), "")


# The open questions a human must answer, built in code from the reasons and tool outputs.
def _questions(reasons: list[str], tool_results: list[dict], unresolved: list) -> list[str]:
    outputs = {r.get("tool"): r.get("output") for r in tool_results}
    questions = []
    if "billing_dispute" in reasons:
        invoices = outputs.get("get_invoices")
        duplicates = _invoice_ids(invoices.get("possible_duplicates")) if isinstance(invoices, dict) else []
        refund = outputs.get("check_refund_eligibility")
        refund = refund if isinstance(refund, dict) else {}
        if len(duplicates) >= 2:
            questions.append(f"Approve refund of {duplicates[-1]} (possible duplicate of {duplicates[0]})?")
        elif refund.get("invoice_id") and refund.get("eligible"):
            questions.append(f"Approve refund of {refund['invoice_id']} (eligible under {refund.get('rule_id', 'the refund policy')})?")
        elif refund.get("invoice_id"):
            why = ", ".join(refund.get("reasons") or []) or "policy check"
            questions.append(f"{refund['invoice_id']} is not eligible ({why}; {refund.get('rule_id', 'refund policy')}): "
                             "decline or approve an exception?")
        else:
            questions.append("Review the billing request and decide on any refund or credit?")
    if "security_incident" in reasons:
        questions.append("Verify identity and secure the account?")
    if "account_deletion" in reasons:
        questions.append("Verify the account owner and confirm the deletion request?")
    if "legal_matter" in reasons:
        questions.append("Review the legal concern and decide how CloudFlow responds?")
    for pair in unresolved:
        questions.append(f"Confirm the correct fix between {pair[0]} and {pair[1]}?")
    if "tool_failure" in reasons:
        failed = ", ".join(str(r.get("tool")) for r in tool_results if _tool_failed(r))
        questions.append(f"Re-run the failed lookup ({failed}) and answer the customer?")
    if "low_groundedness" in reasons or "kb_gap_needs_outcome" in reasons:
        questions.append("Answer the customer's question? The knowledge base gave no confident answer.")
    if "promise_made" in reasons:
        questions.append("Review the drafted reply? It seemed to promise an action that needs approval.")
    if "explicit_human_request" in reasons or "repeated_contact" in reasons:
        questions.append("Contact the customer personally? They asked for a person or have written repeatedly.")
    return questions


# Build the Annex D handoff bundle from the graph state (evidence = tool outputs + cited sources + conflicts).
def build_bundle(state: dict) -> HandoffBundle:
    intent = state["intent"]
    if isinstance(intent, dict):
        intent = Intent(**intent)
    reasons = list(state.get("escalation_reasons") or [])
    tool_results = state.get("tool_results") or []
    unresolved = state.get("unresolved") or []
    chunks = (state.get("retrieved_chunks") or []) + (state.get("applicable_chunks") or [])
    queue, priority = route(reasons, intent)

    if intent.subtype in BILLING_SUBTYPES:
        label = "billing_dispute"
    else:
        label = f"{intent.type}:{intent.subtype}" if intent.subtype else intent.type

    evidence = [{"tool": r.get("tool"), "output": r.get("output")} for r in tool_results]
    sources = [{"source_id": c["source_id"], "section": c.get("section", "")} for c in state.get("citations") or []]
    sources += [{"source_id": sid, "section": _section_of(sid, chunks)} for pair in unresolved for sid in pair]
    for source in sources:
        if source not in evidence:
            evidence.append(source)

    message = _clip(state.get("message_redacted", ""), 160)
    summary = f"Topic: {label}; sentiment {intent.sentiment}; urgency {intent.urgency}. Customer wrote: \"{message}\""
    draft_text = getattr(state.get("draft"), "answer", "") or ""

    return HandoffBundle(
        queue=queue,
        priority=priority,
        intent=label,
        urgency=intent.urgency,
        sentiment=intent.sentiment,
        escalation_reasons=reasons,
        customer_summary=safety.redact(summary)[0],
        evidence=evidence,
        attempted_answer=safety.redact(_clip(draft_text, 200))[0],
        unresolved_questions=_questions(reasons, tool_results, unresolved),
        pii_redacted=True,
    )


# The SLA hours for the plan from policy_registry; an unknown or missing plan uses the Free/Pro row.
def _sla_hours(plan: str | None, as_of_date) -> str:
    try:
        return db.get_policy("escalation_sla_hours", plan, as_of_date)[0]
    except KeyError:
        return db.get_policy("escalation_sla_hours", "Free", as_of_date)[0]


# Write the customer message for an escalation; the response time comes from the plan's SLA row.
# Calm and honest: says who will help and when, and never promises a refund, credit or account change.
def customer_message(reasons: list[str], queue: str, plan: str | None, as_of_date: datetime.date,
                     intent: Intent | None = None) -> str:
    team = _TEAM_NAMES.get(queue, "support team")
    subtype = intent.subtype if intent else None
    if "security_incident" in reasons:
        opening = (f"Thank you for reporting this. I've passed it to our {team} as an urgent case "
                   "so they can verify your identity and help secure your account.")
    elif "account_deletion" in reasons:
        opening = f"I've passed your account deletion request to our {team}, who will confirm it with the account owner first."
    elif "billing_dispute" in reasons:
        topic = {"duplicate_charge": "I'm sorry about the duplicate charge.",
                 "refund": "Thanks for your refund request.",
                 "credit": "Thanks for your credit request."}.get(subtype, "Thanks for raising this billing issue.")
        opening = f"{topic} I've passed it to our {team} with your invoice details so they can review it."
    elif "legal_matter" in reasons:
        opening = f"I understand this is a serious concern. I've passed your message to our {team} so the right people can review it."
    elif "explicit_human_request" in reasons or "repeated_contact" in reasons:
        opening = (f"I'm sorry this hasn't been resolved yet. I've passed your conversation to a person on our {team}, "
                   "with the full details so far.")
    elif "tool_failure" in reasons:
        opening = f"I couldn't load some of the details needed to answer this, so I've passed your question to our {team}."
    elif "unresolved_conflict" in reasons:
        opening = (f"I found conflicting guidance on this, so rather than guess, I've passed your question "
                   f"to our {team} to confirm the right fix.")
    elif "low_groundedness" in reasons or "kb_gap_needs_outcome" in reasons:
        opening = (f"I couldn't find a confident answer in our documentation, so rather than guess, "
                   f"I've passed your question to our {team}.")
    else:
        opening = f"I've passed your request to our {team} so a person can review it."

    parts = [opening, f"You can expect a reply within {_sla_hours(plan, as_of_date)} hours."]
    if queue == "billing":
        parts.append("I can't issue refunds or credits myself; the billing team makes that decision after reviewing your account.")
    return " ".join(parts)

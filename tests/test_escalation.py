"""Tests for app/escalation.py: every A.3 rule, the "do not escalate" cases, routing, bundle and messages."""
import datetime
import json

import pytest

from app import db, escalation, safety
from app.schemas import Critique, HandoffBundle, Intent

AS_OF = datetime.date(2026, 10, 6)

# The policy_registry rows this module reads, copied from the README policy table (so we do not depend on the seed script).
POLICY_ROWS = [
    ("CRITIC-MIN-01", "Minimum critic groundedness", "critic_min_groundedness", ">=", "0.70", "ALL",
     "2026-01-01", "POL-ESC-001", "Answer quality"),
    ("ESC-SLA-01", "Handoff response time", "escalation_sla_hours", "<=", "24", "Free;Pro",
     "2026-01-01", "POL-ESC-001", "Response times"),
    ("ESC-SLA-02", "Handoff response time", "escalation_sla_hours", "<=", "4", "Business;Enterprise",
     "2026-01-01", "POL-ESC-001", "Response times"),
    ("ESC-REPEAT-01", "Repeated contact", "repeat_contact_threshold", ">=", "2", "ALL",
     "2026-01-01", "POL-ESC-001", "Repeated contact"),
    ("ESC-REPEAT-02", "Repeat window", "repeat_contact_window_days", "<=", "30", "ALL",
     "2026-01-01", "POL-ESC-001", "Repeated contact"),
]

GOOD = Critique(groundedness=0.92, coverage="complete", decision="answer")
WEAK = Critique(groundedness=0.50, coverage="partial", decision="revise")


# Every test gets its own temporary SQLite file with the registry rows above.
@pytest.fixture(autouse=True)
def esc_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "escalation.db"))
    db.init_db()
    with db.connect() as conn:
        conn.executemany("INSERT INTO policy_registry VALUES (?,?,?,?,?,?,?,?,?)", POLICY_ROWS)


# A how-to intent unless the test overrides fields.
def make_intent(**fields) -> Intent:
    return Intent(**{"type": "how_to", **fields})


# Call decide() with harmless defaults so each test only states what matters to it.
def run_decide(intent=None, critique=GOOD, tools=(), revisions=0, kb_gap=False, unresolved=(),
               answer="In CloudFlow 4.3, open Workflows, select the workflow, then Runs, then Export."):
    return escalation.decide(intent or make_intent(), critique, list(tools), revisions, kb_gap,
                             list(unresolved), answer, AS_OF)


# ---------- one test per escalation reason ----------

@pytest.mark.parametrize("kwargs, reason", [
    ({"intent": make_intent(type="billing", subtype="refund")}, "billing_dispute"),
    ({"intent": make_intent(type="billing", subtype="credit")}, "billing_dispute"),
    ({"intent": make_intent(type="billing", subtype="dispute")}, "billing_dispute"),
    ({"intent": make_intent(type="complaint", subtype="duplicate_charge")}, "billing_dispute"),
    ({"intent": make_intent(type="complaint", subtype="legal")}, "legal_matter"),
    ({"intent": make_intent(type="account", subtype="deletion")}, "account_deletion"),
    ({"intent": make_intent(type="security", subtype="compromise")}, "security_incident"),
    ({"intent": make_intent(explicit_human_request=True)}, "explicit_human_request"),
    ({"intent": make_intent(type="complaint", sentiment="angry", repeated_contact=True)}, "repeated_contact"),
    ({"intent": make_intent(type="complaint", sentiment="negative", repeated_contact=True)}, "repeated_contact"),
    ({"tools": [{"tool": "get_usage", "output": {"error": "database is locked"}, "status": "error"}]}, "tool_failure"),
    ({"tools": [{"tool": "get_invoices", "output": {"error": "timeout"}, "status": "ok"}]}, "tool_failure"),
    ({"kb_gap": True}, "kb_gap_needs_outcome"),
    ({"unresolved": [("KB-TRB-004", "TKT-2025-0142")]}, "unresolved_conflict"),
    ({"critique": WEAK, "revisions": 1}, "low_groundedness"),
    ({"answer": "Good news: your refund has been issued.", "revisions": 1}, "promise_made"),
])
def test_each_reason_escalates(kwargs, reason):
    decision, reasons = run_decide(**kwargs)
    assert decision == "escalate"
    assert reason in reasons


# ---------- do not escalate ----------

def test_grounded_how_to_is_answered():
    assert run_decide() == ("answer", [])


def test_password_reset_without_compromise_is_answered():
    intent = make_intent(type="security", subtype="password_reset")
    tools = [{"tool": "send_password_reset", "output": {"status": "reset_email_sent"}, "status": "ok"}]
    assert run_decide(intent=intent, tools=tools) == ("answer", [])


def test_angry_alone_or_repeated_alone_is_not_escalated():
    assert run_decide(intent=make_intent(type="troubleshooting", sentiment="angry"))[0] == "answer"
    assert run_decide(intent=make_intent(type="troubleshooting", repeated_contact=True))[0] == "answer"


def test_unknown_account_is_not_a_tool_failure():
    tools = [{"tool": "lookup_account", "output": {"error": "account_not_found"}, "status": "error"}]
    assert run_decide(tools=tools) == ("answer", [])


def test_first_weak_draft_is_revised_not_escalated():
    assert run_decide(critique=WEAK, revisions=0) == ("revise", [])


def test_first_draft_with_promise_is_revised():
    assert run_decide(answer="I have credited your account.", revisions=0) == ("revise", [])


def test_critic_revise_vote_triggers_one_revision_only():
    vote_revise = Critique(groundedness=0.9, coverage="partial", decision="revise")
    assert run_decide(critique=vote_revise, revisions=0) == ("revise", [])
    # One-revision cap: after a revision we never revise again; a grounded draft is answered.
    assert run_decide(critique=vote_revise, revisions=1) == ("answer", [])


def test_weak_draft_after_one_revision_escalates():
    assert run_decide(critique=WEAK, revisions=1) == ("escalate", ["low_groundedness"])


def test_missing_critique_is_handled():
    assert run_decide(critique=None) == ("answer", [])


def test_registry_threshold_change_changes_decision_without_code_change():
    borderline = Critique(groundedness=0.65, coverage="complete", decision="answer")
    assert run_decide(critique=borderline, revisions=1) == ("escalate", ["low_groundedness"])
    with db.connect() as conn:
        conn.execute("UPDATE policy_registry SET value = '0.60' WHERE rule_id = 'CRITIC-MIN-01'")
    assert run_decide(critique=borderline, revisions=1) == ("answer", [])


# ---------- routing ----------

def test_security_beats_billing():
    intent = make_intent(type="security", subtype="compromise")
    assert escalation.route(["billing_dispute", "security_incident"], intent) == ("security", "urgent")


@pytest.mark.parametrize("reasons, intent, expected", [
    (["billing_dispute"], make_intent(type="billing", subtype="refund"), ("billing", "high")),
    (["account_deletion"], make_intent(type="account", subtype="deletion"), ("security", "urgent")),
    (["legal_matter"], make_intent(type="complaint", subtype="legal"), ("legal", "high")),
    (["explicit_human_request"], make_intent(), ("technical", "high")),
    (["explicit_human_request", "repeated_contact"], make_intent(type="billing"), ("billing", "high")),
    (["repeated_contact"], make_intent(type="security"), ("security", "high")),
    (["low_groundedness"], make_intent(), ("technical", "normal")),
    (["tool_failure", "unresolved_conflict", "kb_gap_needs_outcome"], make_intent(), ("technical", "normal")),
    (["low_groundedness", "explicit_human_request"], make_intent(), ("technical", "high")),
    (["promise_made"], make_intent(type="billing"), ("billing", "high")),
    ([], make_intent(), ("technical", "normal")),
])
def test_routing_table(reasons, intent, expected):
    assert escalation.route(reasons, intent) == expected


# ---------- handoff bundle ----------

# A duplicate-charge escalation state like the A1004 demo case.
def duplicate_charge_state(possible_duplicates):
    return {
        "intent": make_intent(type="complaint", subtype="duplicate_charge", urgency="high", sentiment="angry",
                              explicit_human_request=True, repeated_contact=True),
        "escalation_reasons": ["billing_dispute", "explicit_human_request", "repeated_contact"],
        "message_redacted": "Third time writing. You charged me twice on 1 Oct. Get me a manager. Reach me at [EMAIL].",
        "tool_results": [{"tool": "get_invoices", "status": "ok", "ms": 3, "input": {"account_id": "A1004"},
                          "output": {"invoices": [{"invoice_id": "INV-6001", "amount": 49.0, "charged_on": "2026-10-01"},
                                                  {"invoice_id": "INV-6002", "amount": 49.0, "charged_on": "2026-10-01"}],
                                     "possible_duplicates": possible_duplicates}}],
        "citations": [{"source_id": "KB-BIL-003", "doc_type": "article", "section": "Duplicate charges",
                       "product_versions": "ALL", "last_updated": "2026-08-01"}],
        "unresolved": [("KB-BIL-003", "TKT-2025-0610")],
        "retrieved_chunks": [{"chunk_id": "TKT-2025-0610::ticket::0", "text": "...", "score": 0.6,
                              "meta": {"source_id": "TKT-2025-0610", "section": "ticket"}}],
        "draft": None,
    }


@pytest.mark.parametrize("possible_duplicates", [
    [["INV-6001", "INV-6002"]],
    ["INV-6001", "INV-6002"],
    [{"invoice_ids": ["INV-6001", "INV-6002"], "amount": 49.0, "charged_on": "2026-10-01"}],
])
def test_bundle_has_every_annex_d_field_and_evidence(possible_duplicates):
    bundle = escalation.build_bundle(duplicate_charge_state(possible_duplicates))
    assert isinstance(bundle, HandoffBundle)
    assert set(HandoffBundle.model_fields) <= set(bundle.model_dump())
    assert (bundle.queue, bundle.priority, bundle.intent) == ("billing", "high", "billing_dispute")
    assert (bundle.urgency, bundle.sentiment) == ("high", "angry")
    assert bundle.escalation_reasons == ["billing_dispute", "explicit_human_request", "repeated_contact"]
    assert "charged me twice" in bundle.customer_summary
    assert any(e.get("tool") == "get_invoices" for e in bundle.evidence)
    assert {"source_id": "KB-BIL-003", "section": "Duplicate charges"} in bundle.evidence
    assert {"source_id": "TKT-2025-0610", "section": "ticket"} in bundle.evidence  # both conflict sources
    assert bundle.evidence.count({"source_id": "KB-BIL-003", "section": "Duplicate charges"}) == 1
    assert any("Approve refund of INV-6002" in q for q in bundle.unresolved_questions)
    assert any("between KB-BIL-003 and TKT-2025-0610" in q for q in bundle.unresolved_questions)
    assert bundle.pii_redacted is True
    assert "@" not in json.dumps(bundle.model_dump())


def test_bundle_for_security_and_eligible_refund():
    state = {
        "intent": make_intent(type="security", subtype="compromise", urgency="urgent"),
        "escalation_reasons": ["security_incident"],
        "message_redacted": "Someone logged into my account from another country.",
        "draft": type("Draft", (), {"answer": "word " * 100})(),
    }
    bundle = escalation.build_bundle(state)
    assert (bundle.queue, bundle.priority, bundle.intent) == ("security", "urgent", "security:compromise")
    assert "Verify identity and secure the account?" in bundle.unresolved_questions
    assert len(bundle.attempted_answer) <= 200 and bundle.attempted_answer.endswith("...")

    refund_state = {
        "intent": make_intent(type="billing", subtype="refund"),
        "escalation_reasons": ["billing_dispute"],
        "message_redacted": "I want a refund for this month.",
        "tool_results": [{"tool": "check_refund_eligibility", "status": "ok",
                          "output": {"eligible": True, "invoice_id": "INV-5005", "days_since_charge": 14,
                                     "window_days": 14, "rule_id": "REFUND-WINDOW-01"}}],
    }
    questions = escalation.build_bundle(refund_state).unresolved_questions
    assert any(q.startswith("Approve refund of INV-5005") for q in questions)

    refund_state["tool_results"][0]["output"].update(eligible=False, invoice_id="INV-5101", days_since_charge=15,
                                                     reasons=["outside_refund_window"])
    questions = escalation.build_bundle(refund_state).unresolved_questions
    assert any("INV-5101 is not eligible (outside_refund_window" in q for q in questions)


# ---------- customer message ----------

@pytest.mark.parametrize("plan, hours", [("Free", "24"), ("Pro", "24"), ("Business", "4"),
                                         ("Enterprise", "4"), (None, "24"), ("Unknown", "24")])
def test_customer_message_uses_plan_sla(plan, hours):
    message = escalation.customer_message(["billing_dispute"], "billing", plan, AS_OF)
    assert f"within {hours} hours" in message


def test_billing_message_is_specific_and_does_not_promise():
    intent = make_intent(type="complaint", subtype="duplicate_charge")
    message = escalation.customer_message(["billing_dispute", "explicit_human_request"], "billing", "Pro", AS_OF, intent)
    assert "duplicate charge" in message
    assert "billing team" in message
    assert "can't issue refunds" in message


@pytest.mark.parametrize("reason, queue", [
    ("billing_dispute", "billing"), ("security_incident", "security"), ("account_deletion", "security"),
    ("legal_matter", "legal"), ("explicit_human_request", "technical"), ("repeated_contact", "billing"),
    ("tool_failure", "technical"), ("unresolved_conflict", "technical"), ("low_groundedness", "technical"),
    ("kb_gap_needs_outcome", "technical"), ("promise_made", "billing"),
])
def test_no_customer_message_makes_a_promise(reason, queue):
    message = escalation.customer_message([reason], queue, "Business", AS_OF, make_intent(subtype="refund"))
    assert message and not safety.makes_promise(message)
    assert "within 4 hours" in message


# ---------- repeated contact from history ----------

# Insert one conversation row created `days_ago` days before AS_OF.
def add_conversation(conversation_id, account_id, days_ago):
    created = (AS_OF - datetime.timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations VALUES (?, ?, ?)", (conversation_id, account_id, created))


def test_repeated_contact_from_history():
    add_conversation("C-0001", "A1004", 3)
    assert escalation.repeated_contact_from_history("A1004", AS_OF) is False  # 1 earlier < threshold 2
    add_conversation("C-0002", "A1004", 10)
    assert escalation.repeated_contact_from_history("A1004", AS_OF) is True
    assert escalation.repeated_contact_from_history("A1004", AS_OF, exclude_conversation_id="C-0002") is False


def test_repeated_contact_ignores_old_and_other_accounts():
    add_conversation("C-0001", "A1004", 40)
    add_conversation("C-0002", "A1004", 45)
    add_conversation("C-0003", "A1001", 1)
    add_conversation("C-0004", "A1001", 2)
    assert escalation.repeated_contact_from_history("A1004", AS_OF) is False
    assert escalation.repeated_contact_from_history(None, AS_OF) is False


# Live-eval fix: "no usage recorded for this period" is data absence, not a broken tool.
def test_no_data_errors_are_not_tool_failures():
    from app.escalation import _tool_failed
    assert not _tool_failed({"tool": "get_usage", "status": "error", "output": {"error": "usage_not_found", "period": "2026-12"}})
    assert not _tool_failed({"tool": "check_refund_eligibility", "status": "error", "output": {"error": "invoice_not_found"}})
    assert _tool_failed({"tool": "get_plan_limits", "status": "error", "output": {"error": "plan_not_found"}})
    assert _tool_failed({"tool": "get_invoices", "status": "error", "output": {"error": "OperationalError: database is locked"}})

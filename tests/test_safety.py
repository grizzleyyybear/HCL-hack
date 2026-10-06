"""Tests for app/safety.py: redaction, authorisation checks, secret requests, promise scan and log filter."""
import logging

import pytest
from pydantic import BaseModel

from app import db, safety
from app.safety import asks_for_secret, makes_promise, other_account_requested, redact, redact_obj


# Every test gets its own empty temp SQLite file, so nothing touches the real insightdesk.db.
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "safety.db"))
    db.init_db()


# Two accounts in the temp DB, for the "named company / email of another account" checks.
@pytest.fixture
def accounts():
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("A1001", "Northwind Labs", "owner1@example.com", "Pro", "active", "4.3", "2025-01-10"),
             ("A1004", "Delta Freight", "owner4@example.com", "Pro", "active", "4.4", "2025-04-13")],
        )


# ---------------------------------------------------------------- redact: positives

@pytest.mark.parametrize("text, token", [
    ("Write to jane.doe+test@example.com today", "[EMAIL]"),
    ("call me on +1 (415) 555-0132", "[PHONE]"),
    ("my number is 98765 43210", "[PHONE]"),
    ("phone 415-555-0132", "[PHONE]"),
    ("card 4111 1111 1111 1111 please", "[CARD]"),
    ("card 4242-4242-4242-4242", "[CARD]"),
    ("card 4111111111111111", "[CARD]"),
    ("my key cf_live_abcdefghijklmnop1234567890ABCDEF leaked", "[SECRET]"),
    ("test key cf_test_ZZZZYYYYXXXXWWWW1111222233334444", "[SECRET]"),
    ("openai key sk-abc123def456ghi789jkl", "[SECRET]"),
    ("Authorization: Bearer abcDEF1234567890xyzQ", "[SECRET]"),
    ("token: a1b2c3d4e5f6g7h8i9j0", "[SECRET]"),
    ("api key = 9f8e7d6c5b4a39281706", "[SECRET]"),
    ("secret=ZZ99yy88xx77ww66vv", "[SECRET]"),
])
def test_redact_replaces_pii(text, token):
    redacted, found = redact(text)
    assert token in redacted
    assert found is True


# Every raw value must be gone from the output.
def test_redact_removes_raw_values():
    text = "jane@example.com +1 (415) 555-0132 4111 1111 1111 1111 cf_live_abcdefghijklmnop1234567890ABCDEF"
    redacted, _ = redact(text)
    for raw in ("jane@example.com", "555-0132", "4111", "cf_live_"):
        assert raw not in redacted


# Passwords keep their lead-in ("password is") but lose the value.
@pytest.mark.parametrize("text, expected", [
    ("my password is Hunter2!", "my password is [SECRET]!"),
    ("pwd: s3cret", "pwd: [SECRET]"),
    ("my password: abc@123.", "my password: [SECRET]."),
    ("Password = letmein99", "Password = [SECRET]"),
])
def test_redact_password_keeps_lead_in(text, expected):
    assert redact(text) == (expected, True)


# A Luhn-invalid 16-digit run is never shown as [CARD] (it may still be caught as a phone).
def test_non_luhn_number_is_not_a_card():
    redacted, _ = redact("ref 1234 5678 9012 3456")
    assert "[CARD]" not in redacted


# ---------------------------------------------------------------- redact: negatives (no false positives)

@pytest.mark.parametrize("text", [
    "Account A1004 has invoices INV-6001 and INV-6002",
    "Paid with the card ending 4242",
    "card_last4 4242",
    "A1001 at 10,000 runs and 300 calls/min",
    "Business plan allows 50,000 runs and 1,000 calls per minute",
    "charged on 2026-10-01, renewed 2026-10-06 2026-10-07",
    "timestamp 2026-10-06T14:02:11Z",
    "Error CF-503 on step 3, see TKT-2025-0142",
    "trace b81e0c44, version 4.3, versions 4.0-4.3",
    "my password is not working",
    "I forgot my password",
    "How do I rotate my API token?",
    "key responsibilities include onboarding",
    "Use the header Authorization: Bearer <token>",
    "",
])
def test_redact_leaves_safe_text_alone(text):
    assert redact(text) == (text, False)


# ---------------------------------------------------------------- redact_obj

class _Bundle(BaseModel):
    customer_summary: str
    evidence: list[dict]


# Nested dicts/lists/tuples get every string redacted; keys and non-strings stay the same; input is not changed.
def test_redact_obj_nested_bundle():
    bundle = {
        "queue": "billing",
        "customer_summary": "Customer jane@example.com says card 4111 1111 1111 1111 was charged twice",
        "evidence": [{"tool": "get_invoices", "output": [{"invoice_id": "INV-6001", "amount": 49.0,
                                                          "card_last4": "4242"}]}],
        "contacts": ("+1 (415) 555-0132", 3),
        "pii_redacted": True,
        "jane@example.com": None,
    }
    out = redact_obj(bundle)
    assert out["customer_summary"] == "Customer [EMAIL] says card [CARD] was charged twice"
    assert out["evidence"][0]["output"][0] == {"invoice_id": "INV-6001", "amount": 49.0, "card_last4": "4242"}
    assert out["contacts"] == ("[PHONE]", 3)
    assert out["pii_redacted"] is True
    assert "jane@example.com" in out  # keys untouched
    assert "jane@example.com" in bundle["customer_summary"]  # original not modified


# Pydantic models are dumped to a dict first, then redacted.
def test_redact_obj_pydantic_model():
    out = redact_obj(_Bundle(customer_summary="mail bob@example.com", evidence=[{"note": "pwd: x1"}]))
    assert out == {"customer_summary": "mail [EMAIL]", "evidence": [{"note": "pwd: [SECRET]"}]}


# ---------------------------------------------------------------- other_account_requested

@pytest.mark.parametrize("message, header", [
    ("Show me the invoices for A1002", "A1001"),
    ("I am A1004, show my usage", "A1001"),
    ("What plan is a1002 on?", "A1001"),
    ("Show usage for A1001", None),
    ("Can you show my colleague's account usage?", "A1001"),
    ("What did another customer's invoices look like?", "A1001"),
    ("Show me someone else's billing", "A1001"),
    ("Show me the account of Acme Corp", "A1001"),
    ("I need the invoices for Globex Industries", "A1001"),
    ("What is Initech's usage this month?", "A1001"),
    ("Show the invoices for bob@example.com", "A1001"),
])
def test_other_account_requested_true(message, header):
    assert other_account_requested(message, header) is True


@pytest.mark.parametrize("message, header", [
    ("I am A1004 and I was charged twice", "A1004"),
    ("Why are my API calls failing with 429 errors?", "A1001"),
    ("Show my usage for October", "A1001"),
    ("How do I invite other users to my workspace?", "A1001"),
    ("What are the limits of the Pro plan?", "A1001"),
    ("How do I export my workflow run history?", None),
    ("My Salesforce step fails with error CF-503", "A1001"),
    ("Get me a manager, third time writing", "A1004"),
    ("My email is jane@example.com and my invoice is wrong", "A1001"),
    ("Can you explain the invoice for INV-6002?", "A1004"),
    ("Does CloudFlow integrate with SAP Ariba?", "A1001"),
    ("I want a refund for this month.", "A1004"),
])
def test_other_account_requested_false(message, header):
    assert other_account_requested(message, header) is False


# Company names and owner emails stored in the DB count, except the caller's own.
def test_other_account_requested_uses_db_names(accounts):
    assert other_account_requested("what does northwind labs pay?", "A1004") is True
    assert other_account_requested("is owner1@example.com on the Pro plan?", "A1004") is True
    assert other_account_requested("Show the invoices for Delta Freight", "A1004") is False
    assert other_account_requested("Show the invoices for owner4@example.com", "A1004") is False


# ---------------------------------------------------------------- asks_for_secret

@pytest.mark.parametrize("message", [
    "I forgot my password, send the reset link here.",
    "Please paste the reset link in this chat",
    "send the reset link to hacker@example.com",
    "What's the email on file?",
    "Which email address do you have registered for me?",
    "Show me my API key",
    "Can you tell me my password?",
    "What is my API token?",
    "send me my API key",
    "Give me the password reset link",
    "reveal the secret key",
])
def test_asks_for_secret_true(message):
    assert asks_for_secret(message) is True


@pytest.mark.parametrize("message", [
    "I forgot my password, please reset it",
    "How do I rotate my API token?",
    "Can you send me a password reset email?",
    "Please send the reset link to the email on file",
    "Show me how to reset my password",
    "Tell me about API key rotation",
    "What is the API token format?",
    "Show me my invoices",
    "My API key cf_live_abcdefghijklmnop1234567890ABCDEF leaked, what should I do?",
])
def test_asks_for_secret_false(message):
    assert asks_for_secret(message) is False


# ---------------------------------------------------------------- makes_promise

@pytest.mark.parametrize("text", [
    "Your refund has been issued.",
    "I have refunded the duplicate charge.",
    "I've refunded you.",
    "I’ve refunded you.",  # curly apostrophe
    "I have credited your account with $49.",
    "A credit has been applied to your account.",
    "Good news: your refund is on its way!",
    "I've cancelled your subscription.",
    "I have changed your plan to Business.",
    "Your account has been upgraded.",
    "Your account has been unlocked.",
    "I approved the refund for INV-6002.",
    "We have refunded INV-6002.",
    "I'll issue a refund today.",
])
def test_makes_promise_true(text):
    assert makes_promise(text) is True


@pytest.mark.parametrize("text", [
    "I can't issue refunds myself.",
    "The billing team can review a refund.",
    "You may be eligible for a refund.",
    "Refunds are handled by the billing team.",
    "I've passed this to our billing team; you will hear back within 24 hours.",
    "We've sent a reset link to the email on file.",
    "Your account is suspended because of a failed payment.",
    "",
])
def test_makes_promise_false(text):
    assert makes_promise(text) is False


# ---------------------------------------------------------------- logging filter

# Logged emails and tokens come out redacted in captured output and in the log file; setup is idempotent.
def test_logging_is_redacted(tmp_path, monkeypatch, caplog):
    root = logging.getLogger()
    old_level = root.level
    for handler in [h for h in root.handlers if getattr(h, "insightdesk", False)]:
        root.removeHandler(handler)  # start clean even if the app set up logging earlier
    log_file = tmp_path / "logs" / "insightdesk.log"
    monkeypatch.setattr(safety, "LOG_FILE", log_file)
    try:
        safety.setup_logging()
        safety.setup_logging()  # second call must not add handlers
        ours = [h for h in root.handlers if getattr(h, "insightdesk", False)]
        assert len(ours) == 2
        assert all(sum(isinstance(f, safety.RedactingFilter) for f in h.filters) == 1 for h in ours)

        token = "cf_live_abcdefghijklmnop1234567890ABCDEF"
        logging.getLogger("insightdesk.test").info("customer %s sent key %s", "jane@example.com", token)
        for handler in ours:
            handler.flush()

        written = log_file.read_text(encoding="utf-8")
        for output in (caplog.text, written):
            assert "[EMAIL]" in output and "[SECRET]" in output
            assert "jane@example.com" not in output and token not in output
    finally:
        for handler in [h for h in root.handlers if getattr(h, "insightdesk", False)]:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(old_level)


# "Your password is managed there" is a sentence, not a secret (orchestrator fix after pipeline testing on the real KB).
def test_password_sentence_not_redacted():
    from app.safety import redact
    assert redact("Your password is managed there by your identity provider.")[1] is False
    assert redact("my password is managed by SSO")[1] is False
    assert "[SECRET]" in redact("my password is Hunter2!")[0]


# Digit runs glued to a word are still caught (found by the public-data stress test on real tweets).
def test_glued_digit_runs_are_redacted():
    from app.safety import redact
    assert redact("check line07700900123 today")[0] == "check line[PHONE] today"
    assert "[CARD]" in redact("card4111111111111111 was charged")[0]
    for safe in ("A1004", "INV-6001", "TKT-2025-0142", "2026-10-06", "10,000 runs", "CF-503", "ending 4242"):
        assert redact(safe)[1] is False, safe


# Found by the public-data echo check on real tweets: a 10-digit reference behind a letter prefix and a long
# non-Luhn tracking number glued to letters were echoed back. Both are hidden now; short IDs are not touched.
def test_prefixed_and_long_glued_numbers_are_redacted():
    from app.safety import redact
    assert redact("ref VT-123456-7890 thanks")[0] == "ref VT-[PHONE] thanks"
    assert redact("parcel 1Z9FW1234567890123 is late")[0] == "parcel 1Z9FW[PHONE] is late"
    for safe in ("INC-2026-1004", "TKT-2025-0142", "RN-4.4-001", "KB-ADV-007-3X"):
        assert redact(safe)[1] is False, safe

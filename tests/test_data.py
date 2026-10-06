"""Data and tools area: policy lookup rules, refund and duplicate edge cases, the judges' CSV loader on
spreadsheet-style files, public-data scrubbing and the demo reset. Uses the edge_db fixture (tests/conftest.py).

A9xxx / INV-J IDs below are on purpose: they simulate judge test data, which the loader must accept.
"""
from app import db
from app.tools import check_refund_eligibility, get_invoices
from scripts import load_accounts, reset_demo_state
from scripts.mine_public_data import scrub

AS_OF = "2026-10-06"


# Insert one policy_registry row (rule_id, parameter, value, scope) effective from 2026-01-01.
def add_rule(rule_id, parameter, value, scope):
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO policy_registry VALUES (?,?,?,?,?,?,?,?,?)",
                     (rule_id, "test rule", parameter, "<=", value, scope, "2026-01-01", "POL-ESC-001", "Test"))


# ---------------------------------------------------------------- refunds and duplicates

# A paid invoice dated after as_of_date is not "the latest charge" yet: the check uses the one before it.
def test_refund_check_ignores_an_invoice_dated_after_as_of(edge_db):
    with db.connect() as conn:
        conn.execute("INSERT INTO invoices VALUES ('INV-5002','A1005',199.0,'USD','2026-10-22','paid','','4444')")
    result = check_refund_eligibility("A1005", AS_OF)
    assert result["invoice_id"] == "INV-5001" and result["days_since_charge"] == 14 and result["eligible"] is True


# Asking about that future invoice explicitly is never eligible and says why.
def test_explicit_future_invoice_is_not_eligible(edge_db):
    with db.connect() as conn:
        conn.execute("INSERT INTO invoices VALUES ('INV-5002','A1005',199.0,'USD','2026-10-22','paid','','4444')")
    result = check_refund_eligibility("A1005", AS_OF, invoice_id="INV-5002")
    assert result["eligible"] is False and "charge_after_as_of_date" in result["reasons"]


# A duplicate charge that was already refunded is no longer a duplicate to report.
def test_refunded_invoice_is_not_a_possible_duplicate(edge_db):
    assert get_invoices("A1004")["possible_duplicates"]  # two paid 49.0 charges on 2026-10-01
    with db.connect() as conn:
        conn.execute("UPDATE invoices SET status = 'refunded' WHERE invoice_id = 'INV-6002'")
    assert get_invoices("A1004")["possible_duplicates"] == []


# ---------------------------------------------------------------- policy registry lookup

# A request dated before the first rule uses the earliest rule instead of failing with a 500.
def test_policy_before_the_first_rule_uses_the_earliest(edge_db):
    assert db.get_policy("refund_window_days", "Pro", "2025-12-31") == ("14", "REFUND-WINDOW-01")


# On the same effective date, the row written last wins, and a plan-specific row beats an "ALL" row.
def test_newer_and_plan_specific_rows_win_on_the_same_date(edge_db):
    add_rule("REFUND-WINDOW-02", "refund_window_days", "30", "ALL")
    assert db.get_policy("refund_window_days", "Pro", AS_OF) == ("30", "REFUND-WINDOW-02")
    add_rule("ESC-SLA-03", "escalation_sla_hours", "8", "Pro")
    assert db.get_policy("escalation_sla_hours", "Pro", AS_OF) == ("8", "ESC-SLA-03")
    assert db.get_policy("escalation_sla_hours", "Free", AS_OF)[0] == "24"


# Plan lists written with commas or in another case still work, in scopes and in refund_allowed_plans.
def test_plan_lists_accept_commas_and_any_case(edge_db):
    with db.connect() as conn:
        conn.execute("UPDATE policy_registry SET value = 'pro, business,ENTERPRISE' WHERE rule_id = 'REFUND-FREE-01'")
        conn.execute("UPDATE policy_registry SET scope_plans = 'all' WHERE rule_id = 'REFUND-WINDOW-01'")
    assert db.plan_list("Free; pro, ALL") == ["free", "pro", "all"]
    assert check_refund_eligibility("A1005", AS_OF)["eligible"] is True  # Business, 14 days


# ---------------------------------------------------------------- judges' loader

# A spreadsheet-style export loads: Windows code page, capitalised headers, "pro"/"Active", "$49.00", a card
# whose leading zero Excel dropped, and a timestamp with a space.
def test_loader_reads_a_spreadsheet_style_export(edge_db, tmp_path):
    (tmp_path / "accounts.csv").write_bytes(
        "Account_ID,Company_Name,Owner_Email,Plan,Status,Product_Version,Created_At\n"
        "A9101,Café Lumière,owner@example.com,pro,Active,4.3,2026-01-15\n".encode("cp1252"))
    (tmp_path / "invoices.csv").write_text(
        "invoice_id,account_id,amount,currency,charged_on,status,failure_reason,card_last4\n"
        "INV-J9101,A9101,$49.00,usd,2026-10-01,Paid,,341\n", encoding="utf-8")
    (tmp_path / "platform_status.csv").write_text(
        "component,status,incident_id,updated_at\napi,Operational,,2026-10-06 08:00:00\n", encoding="utf-8")
    result = load_accounts.load_dir(str(tmp_path))
    assert result["violations"] == [], result["violations"]
    with db.connect() as conn:
        account = conn.execute("SELECT company_name, plan, status FROM accounts WHERE account_id = 'A9101'").fetchone()
        invoice = conn.execute("SELECT amount, currency, status, card_last4 FROM invoices WHERE invoice_id = 'INV-J9101'").fetchone()
    assert tuple(account) == ("Café Lumière", "Pro", "active")
    assert tuple(invoice) == (49.0, "USD", "paid", "0341")


# ---------------------------------------------------------------- public data and demo reset

# Public text is scrubbed before anything is kept: no URL, email, handle, number or self-introduced name survives.
def test_scrub_removes_personal_data_from_public_text():
    raw = ("@AmazonHelp my name is Jane Doe, email jane.doe@gmail.com, call +1 415 555 0101 "
           "or see https://t.co/abc123. Agent Smith never replied.")
    clean = scrub(raw)
    for leaked in ("@AmazonHelp", "Jane", "jane.doe", "415", "https://", "Smith"):
        assert leaked not in clean, (leaked, clean)
    assert "[EMAIL]" in clean and "[NUMBER]" in clean and "[URL]" in clean


# The demo reset clears conversations, messages, handoffs, audit records and the C-/H- counters only.
def test_reset_demo_state_keeps_accounts_and_policies(edge_db):
    with db.connect() as conn:
        accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        rules = conn.execute("SELECT COUNT(*) FROM policy_registry").fetchone()[0]
    db.next_id("H")
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations (conversation_id, account_id, created_at) VALUES ('C-0001','A1001','x')")
        conn.execute("INSERT INTO audit_log (trace_id, created_at, record_json) VALUES ('t1','x','{}')")
    reset_demo_state.reset()
    with db.connect() as conn:
        for table in ("conversations", "messages", "handoffs", "audit_log"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == accounts
        assert conn.execute("SELECT COUNT(*) FROM policy_registry").fetchone()[0] == rules
    assert db.next_id("H") == "H-0001"  # counters restart

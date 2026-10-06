"""Tool tests on the edge-case accounts A1001-A1008 (fixture in conftest.py), as of 2026-10-06."""
import json
import logging

import pytest

from app import db, safety
from app.tools import TOOLS, TOOLS_FOR_INTENT, run_tool
from app.tools.account_tools import get_plan_limits, get_usage, lookup_account
from app.tools.billing_tools import check_refund_eligibility, get_invoices
from app.tools.handoff_tools import create_handoff
from app.tools.security_tools import send_password_reset
from app.tools.status_tools import check_platform_status
from scripts.seed_policy_registry import seed

AS_OF = "2026-10-06"


# Skip a test while app/safety.py is still a stub (A8 lands it in the next wave).
def require_safety():
    try:
        safety.redact_obj({"probe": "x"})
    except NotImplementedError:
        pytest.skip("app/safety.py not implemented yet")


# lookup_account returns account facts but never the owner email.
def test_lookup_account_hides_email(edge_db):
    out = lookup_account("A1001")
    assert out["plan"] == "Pro" and out["status"] == "active" and out["product_version"] == "4.3"
    assert "owner_email" not in out
    assert "@" not in json.dumps(out)


# An unknown account gives a clean error, not a crash.
def test_unknown_account(edge_db):
    assert lookup_account("A1999") == {"error": "account_not_found"}
    assert get_invoices("A1999") == {"error": "account_not_found"}
    assert check_refund_eligibility("A1999", AS_OF) == {"error": "account_not_found"}


# get_usage defaults to the month of as_of_date; an explicit period also works.
def test_usage_period(edge_db):
    assert get_usage("A1001", as_of_date=AS_OF)["workflow_runs"] == 10000
    assert get_usage("A1001", period="2026-09")["workflow_runs"] == 8200
    assert get_usage("A1001", period="2025-01")["error"] == "usage_not_found"


# A1001 is exactly at every limit, which is NOT over (strictly greater-than).
def test_a1001_at_limit_not_over(edge_db):
    out = get_plan_limits("Pro", get_usage("A1001", as_of_date=AS_OF))
    assert out["monthly_workflow_runs"] == 10000 and out["api_rate_limit_per_min"] == 300
    assert out["workflow_runs_over"] is False
    assert out["api_rate_over"] is False
    assert out["seats_over"] is False
    assert out["rule_id"] == "LIMITS-REF-01"


# A1002 is one unit over on runs (10,001) and API rate (301 vs 300).
def test_a1002_over_limit(edge_db):
    out = get_plan_limits("Pro", get_usage("A1002", as_of_date=AS_OF))
    assert out["workflow_runs_over"] is True
    assert out["api_rate_over"] is True
    assert out["seats_over"] is False


# Without usage, get_plan_limits returns just the limits; unknown plans give an error.
def test_plan_limits_plain(edge_db):
    out = get_plan_limits("Enterprise")
    assert out["api_rate_limit_per_min"] == 5000 and "api_rate_over" not in out
    assert get_plan_limits("Platinum") == {"error": "plan_not_found"}


# A1003 has a failed invoice with its failure reason; the status filter works.
def test_a1003_failed_invoice(edge_db):
    out = get_invoices("A1003")
    assert out["invoices"][0]["status"] == "failed"
    assert out["invoices"][0]["failure_reason"] == "card_declined"
    assert get_invoices("A1003", status="paid")["invoices"] == []
    refund = check_refund_eligibility("A1003", AS_OF, invoice_id="INV-3001")
    assert refund["eligible"] is False and "invoice_not_paid" in refund["reasons"]


# A1004 was charged twice on the same day for the same amount.
def test_a1004_possible_duplicates(edge_db):
    out = get_invoices("A1004")
    assert len(out["invoices"]) == 2
    dup = out["possible_duplicates"]
    assert len(dup) == 1
    assert sorted(dup[0]["invoice_ids"]) == ["INV-6001", "INV-6002"]
    assert dup[0]["amount"] == 49.0 and dup[0]["charged_on"] == "2026-10-01"
    assert get_invoices("A1001")["possible_duplicates"] == []


# A1005: charged exactly 14 days ago, the last day of the window, so eligible.
def test_a1005_eligible_last_day(edge_db):
    out = check_refund_eligibility("A1005", AS_OF)
    assert out["eligible"] is True
    assert out["days_since_charge"] == 14 and out["window_days"] == 14
    assert out["rule_id"] == "REFUND-WINDOW-01" and out["plan_rule_id"] == "REFUND-FREE-01"
    assert out["refund_executed"] is False


# A1006: charged 15 days ago, one day after the window, so not eligible.
def test_a1006_not_eligible_day_after(edge_db):
    out = check_refund_eligibility("A1006", AS_OF)
    assert out["eligible"] is False
    assert out["days_since_charge"] == 15
    assert out["reasons"] == ["outside_refund_window"]


# The Free plan is never eligible for a refund (REFUND-FREE-01).
def test_free_plan_not_eligible(edge_db):
    out = check_refund_eligibility("A1009", AS_OF)
    assert out["eligible"] is False
    assert "plan_not_eligible" in out["reasons"]


# A customer cannot check another account's invoice (authorisation in the SQL).
def test_refund_other_accounts_invoice(edge_db):
    assert check_refund_eligibility("A1001", AS_OF, invoice_id="INV-6001") == {"error": "invoice_not_found"}


# Changing the policy row in the DB changes the result on the next call, with no code change or restart.
def test_policy_change_without_code_change(edge_db):
    assert check_refund_eligibility("A1006", AS_OF)["eligible"] is False
    with db.connect() as conn:
        conn.execute("UPDATE policy_registry SET value = '30' WHERE parameter = 'refund_window_days'")
    out = check_refund_eligibility("A1006", AS_OF)
    assert out["eligible"] is True and out["window_days"] == 30


# Platform status lists all components, one is degraded; a single component can be requested.
def test_platform_status(edge_db):
    comps = check_platform_status()["components"]
    assert {c["component"] for c in comps} == {"api", "workflow-engine", "connectors", "billing"}
    assert check_platform_status("connectors")["components"][0]["status"] == "degraded"
    assert check_platform_status("database") == {"error": "component_not_found"}


# Password reset returns only a status: no token, link or email in the output or the logs.
def test_password_reset_reveals_nothing(edge_db, caplog):
    with caplog.at_level(logging.INFO):
        out = send_password_reset("A1001")
    assert out == {"status": "reset_email_sent"}
    for text in (json.dumps(out), caplog.text):
        assert "@" not in text and "http" not in text.lower() and "token" not in text.lower()
    assert send_password_reset("A1999") == {"error": "account_not_found"}


# create_handoff stores a redacted bundle and returns H-0001 on a fresh DB.
def test_create_handoff_redacts(edge_db):
    require_safety()
    bundle = {"queue": "billing", "priority": "high", "customer_summary": "Charged twice, reach me at jane@example.com",
              "evidence": [{"tool": "get_invoices", "output": {"invoice_ids": ["INV-6001", "INV-6002"]}}]}
    out = create_handoff("C-0001", "A1004", "billing", "high", bundle)
    assert out == {"handoff_id": "H-0001"}
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = 'H-0001'").fetchone()
    assert row["queue"] == "billing" and row["account_id"] == "A1004"
    stored = json.loads(row["bundle_json"])
    assert "jane@example.com" not in row["bundle_json"]
    assert stored["pii_redacted"] is True
    assert "INV-6002" in row["bundle_json"]


# run_tool times a successful call and reports status ok.
def test_run_tool_ok(edge_db):
    call = run_tool("lookup_account", account_id="A1001")
    assert call.status == "ok" and call.output["plan"] == "Pro"
    assert call.tool == "lookup_account" and call.input == {"account_id": "A1001"} and call.ms >= 0


# run_tool never raises: unknown tools, bad arguments and tool errors all become status "error".
def test_run_tool_errors_do_not_raise(edge_db):
    assert run_tool("no_such_tool").status == "error"
    bad_args = run_tool("lookup_account")  # missing account_id -> TypeError inside the tool
    assert bad_args.status == "error" and bad_args.output["error"].startswith("TypeError")
    not_found = run_tool("lookup_account", account_id="A1999")
    assert not_found.status == "error" and not_found.output == {"error": "account_not_found"}


# run_tool redacts PII in the recorded input and output.
def test_run_tool_redacts(edge_db):
    require_safety()
    call = run_tool("create_handoff", conversation_id="C-0001", account_id="A1004", queue="billing",
                    priority="high", bundle={"customer_summary": "email me at bob@example.com"})
    assert call.status == "ok"
    assert "bob@example.com" not in json.dumps(call.model_dump(), default=str)


# Every tool named in the intent safety-net mapping actually exists.
def test_tools_for_intent_names_exist():
    for names in TOOLS_FOR_INTENT.values():
        assert set(names) <= set(TOOLS)
    assert TOOLS_FOR_INTENT["billing"] == ["get_invoices", "check_refund_eligibility"]


# Seeding is repeatable and never undoes a rule someone changed in the DB (unless force=True).
def test_seed_repeatable(edge_db):
    with db.connect() as conn:
        conn.execute("UPDATE policy_registry SET value = '0.60' WHERE rule_id = 'CRITIC-MIN-01'")
    seed()
    assert db.get_policy("critic_min_groundedness") == ("0.60", "CRITIC-MIN-01")
    seed(force=True)
    assert db.get_policy("critic_min_groundedness") == ("0.70", "CRITIC-MIN-01")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM policy_registry").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM plan_limits").fetchone()[0] == 4
    assert db.get_policy("escalation_sla_hours", "Business") == ("4", "ESC-SLA-02")
    assert db.get_policy("escalation_sla_hours", "Pro") == ("24", "ESC-SLA-01")

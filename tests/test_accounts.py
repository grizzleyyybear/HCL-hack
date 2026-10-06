"""Tests for the account data kit: generator output, validator and judge-facing loader (A3)."""
import csv
import json

import pytest

from app import db
from scripts import generate_accounts, load_accounts
from scripts.validate_accounts import read_tables, validate

DATA_DIR = generate_accounts.OUT_DIR


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    return tmp_path


# Write {table: [row dicts]} as <table>.csv files into a folder (simulates a judge's test folder).
def write_folder(folder, tables):
    folder.mkdir(exist_ok=True)
    for table, rows in tables.items():
        with (folder / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return folder


JUDGE_ACCOUNT = {"account_id": "A9001", "company_name": "Judge Test Co", "owner_email": "judge@example.com",
                 "plan": "Pro", "status": "active", "product_version": "4.3", "created_at": "2025-05-01"}
JUDGE_INVOICE = {"invoice_id": "INV-J001", "account_id": "A9001", "amount": "49.0", "currency": "USD",
                 "charged_on": "2026-10-01", "status": "paid", "failure_reason": "", "card_last4": "1234"}


def test_our_csvs_have_no_violations():
    tables, _ = read_tables(DATA_DIR)
    assert set(tables) >= {"accounts", "plan_limits", "usage", "invoices", "platform_status"}
    assert validate(tables) == []


def test_minimum_data_requirements():
    tables, _ = read_tables(DATA_DIR)
    accounts = tables["accounts"]
    assert len(accounts) >= 30
    assert {a["plan"] for a in accounts} == {"Free", "Pro", "Business", "Enterprise"}
    assert {a["status"] for a in accounts} == {"active", "past_due", "suspended", "cancelled"}
    usage = {(u["account_id"], u["period"]) for u in tables["usage"]}
    billed = {i["account_id"] for i in tables["invoices"]}
    for acc in accounts:
        assert (acc["account_id"], "2026-10") in usage and (acc["account_id"], "2026-09") in usage
        assert (acc["plan"] != "Free") == (acc["account_id"] in billed)
    components = {p["component"]: p["status"] for p in tables["platform_status"]}
    assert set(components) == {"api", "workflow-engine", "connectors", "billing"}
    assert "degraded" in components.values()
    limits = {p["plan"]: (p["api_rate_limit_per_min"], p["monthly_workflow_runs"], p["seats"], p["monthly_price"])
              for p in tables["plan_limits"]}
    assert limits["Pro"] == ("300", "10000", "5", "49.0")


def test_edge_cases_have_exact_values():
    tables, _ = read_tables(DATA_DIR)
    acc = {a["account_id"]: a for a in tables["accounts"]}
    usage = {(u["account_id"], u["period"]): u for u in tables["usage"]}
    inv = tables["invoices"]

    def invoices_of(account_id):
        return [i for i in inv if i["account_id"] == account_id]

    def latest_paid(account_id):
        return max(i["charged_on"] for i in invoices_of(account_id) if i["status"] == "paid")

    assert (acc["A1001"]["plan"], acc["A1001"]["product_version"], acc["A1001"]["status"]) == ("Pro", "4.3", "active")
    assert usage[("A1001", "2026-10")]["workflow_runs"] == "10000"
    assert usage[("A1002", "2026-10")]["workflow_runs"] == "10001"
    assert usage[("A1002", "2026-10")]["api_calls_peak_per_min"] == "301"
    assert acc["A1003"]["status"] == "past_due"
    assert any(i["status"] == "failed" and i["failure_reason"] == "card_declined" for i in invoices_of("A1003"))
    dupes = [i for i in invoices_of("A1004") if i["invoice_id"] in ("INV-6001", "INV-6002")]
    assert [(i["amount"], i["currency"], i["status"], i["charged_on"]) for i in dupes] == \
        [("49.0", "USD", "paid", "2026-10-01")] * 2
    assert latest_paid("A1005") == "2026-09-22"
    assert latest_paid("A1006") == "2026-09-21"
    assert acc["A1007"]["status"] == "suspended"
    assert acc["A1008"]["product_version"] == "3.8"


def test_generator_catches_llm_mistakes():
    batch = json.loads(generate_accounts.BATCH_FILE.read_text(encoding="utf-8"))
    fillers, mistakes = generate_accounts.clean_rows(batch["responses"])
    actions = {m["account_id"]: m["action"] for m in mistakes}
    assert actions["A9012"] == "dropped"  # reserved judge ID
    assert actions["A1030"] == "dropped"  # negative usage
    assert actions["A1015"].startswith("repaired")  # non-example.com email
    assert actions["A1020"].startswith("repaired")  # full card number
    fixed = {f.account_id: f for f in fillers}
    assert fixed["A1015"].owner_email.endswith("@example.com")
    assert fixed["A1020"].card_last4 == "5532"
    assert len(fillers) >= 22


def test_reserved_ids_rejected_by_validate_but_loaded(temp_db):
    tables = {"accounts": [JUDGE_ACCOUNT], "invoices": [JUDGE_INVOICE]}
    problems = validate(tables, check_reserved=True)
    assert any("A9000-A9999" in p for p in problems)
    assert any("INV-J" in p for p in problems)
    assert validate(tables, check_reserved=False) == []


def test_load_dir_accepts_judge_ids_and_skips_missing_files(temp_db):
    folder = write_folder(temp_db / "judge", {"accounts": [JUDGE_ACCOUNT], "invoices": [JUDGE_INVOICE]})
    result = load_accounts.load_dir(str(folder))
    assert result["loaded"] == {"accounts": 1, "invoices": 1}
    assert result["violations"] == []
    assert set(result["skipped_files"]) == {"plan_limits.csv", "usage.csv", "platform_status.csv",
                                           "policy_registry.csv"}
    with db.connect() as conn:
        row = conn.execute("SELECT amount, account_id FROM invoices WHERE invoice_id = 'INV-J001'").fetchone()
        assert (row["amount"], row["account_id"]) == (49.0, "A9001")  # amount stored as a number
        assert conn.execute("SELECT plan FROM accounts WHERE account_id = 'A9001'").fetchone()["plan"] == "Pro"


def test_card_number_and_real_email_are_violations(temp_db):
    bad_account = {**JUDGE_ACCOUNT, "account_id": "A9002", "owner_email": "someone@gmail.com"}
    bad_invoice = {**JUDGE_INVOICE, "invoice_id": "INV-J002", "card_last4": "4716038829105532"}
    tables = {"accounts": [JUDGE_ACCOUNT, bad_account], "invoices": [JUDGE_INVOICE, bad_invoice]}
    problems = validate(tables, check_reserved=False)
    assert any("A9002" in p and "owner_email" in p for p in problems)
    assert any("INV-J002" in p and "card" in p for p in problems)
    # The loader refuses only the bad rows and loads the rest.
    result = load_accounts.load_dir(str(write_folder(temp_db / "mixed", tables)))
    assert result["loaded"] == {"accounts": 1, "invoices": 1}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM invoices WHERE invoice_id = 'INV-J002'").fetchone()[0] == 0


def test_usage_for_an_account_already_in_the_db(temp_db):
    load_accounts.load_dir(str(write_folder(temp_db / "first", {"accounts": [JUDGE_ACCOUNT]})))
    usage = {"account_id": "A9001", "period": "2026-10", "workflow_runs": "12", "api_calls_peak_per_min": "3",
             "seats_used": "1"}
    result = load_accounts.load_dir(str(write_folder(temp_db / "second", {"usage": [usage]})))
    assert result["loaded"] == {"usage": 1} and result["violations"] == []
    orphan = {**usage, "account_id": "A9999"}
    result = load_accounts.load_dir(str(write_folder(temp_db / "third", {"usage": [orphan]})))
    assert result["loaded"] == {"usage": 0} and "does not exist" in result["violations"][0]


def test_our_data_loads_into_a_fresh_db(temp_db):
    result = load_accounts.load_dir(str(DATA_DIR))
    assert result["violations"] == [] and result["warnings"] == []
    assert result["loaded"]["accounts"] >= 30
    with db.connect() as conn:
        row = conn.execute("SELECT workflow_runs FROM usage WHERE account_id = 'A1002' AND period = '2026-10'").fetchone()
        assert row["workflow_runs"] == 10001

"""Shared pytest fixtures. `edge_db` gives a temp SQLite with the policy registry and edge cases A1001-A1008."""
import pytest

from app import db
from scripts.seed_policy_registry import seed

# Edge-case accounts from CLAUDE.md (dates relative to 2026-10-06, refund window 14 days), plus one Free account.
ACCOUNTS = [
    ("A1001", "Northwind Labs", "owner1@example.com", "Pro", "active", "4.3", "2025-01-10"),       # usage at limit
    ("A1002", "Bluebird Ops", "owner2@example.com", "Pro", "active", "4.3", "2025-02-11"),         # one unit over
    ("A1003", "Cedar Analytics", "owner3@example.com", "Pro", "past_due", "4.2", "2025-03-12"),    # failed payment
    ("A1004", "Delta Freight", "owner4@example.com", "Pro", "active", "4.4", "2025-04-13"),        # duplicate charge
    ("A1005", "Ember Health", "owner5@example.com", "Business", "active", "4.3", "2025-05-14"),    # last day of window
    ("A1006", "Fjord Retail", "owner6@example.com", "Pro", "active", "4.4", "2025-06-15"),         # one day after window
    ("A1007", "Granite Works", "owner7@example.com", "Pro", "suspended", "4.3", "2024-07-16"),     # suspended
    ("A1008", "Harbor Legacy", "owner8@example.com", "Pro", "active", "3.8", "2024-08-17"),        # old version
    ("A1009", "Iris Studio", "owner9@example.com", "Free", "active", "4.4", "2026-01-05"),         # Free plan
]

# (account_id, period, workflow_runs, api_calls_peak_per_min, seats_used)
USAGE = [
    ("A1001", "2026-10", 10000, 300, 5),
    ("A1001", "2026-09", 8200, 240, 5),
    ("A1002", "2026-10", 10001, 301, 3),
    ("A1003", "2026-10", 1200, 40, 2),
    ("A1004", "2026-10", 3000, 120, 4),
    ("A1005", "2026-10", 20000, 600, 12),
    ("A1006", "2026-10", 4000, 150, 2),
    ("A1007", "2026-10", 0, 0, 3),
    ("A1008", "2026-10", 2500, 90, 2),
    ("A1009", "2026-10", 120, 10, 1),
]

# (invoice_id, account_id, amount, currency, charged_on, status, failure_reason, card_last4)
INVOICES = [
    ("INV-1001", "A1001", 49.0, "USD", "2026-10-01", "paid", "", "4242"),
    ("INV-1002", "A1002", 49.0, "USD", "2026-10-02", "paid", "", "1881"),
    ("INV-3001", "A1003", 49.0, "USD", "2026-10-01", "failed", "card_declined", "0341"),
    ("INV-6001", "A1004", 49.0, "USD", "2026-10-01", "paid", "", "5556"),
    ("INV-6002", "A1004", 49.0, "USD", "2026-10-01", "paid", "", "5556"),
    ("INV-5001", "A1005", 199.0, "USD", "2026-09-22", "paid", "", "4444"),
    ("INV-5101", "A1006", 49.0, "USD", "2026-09-21", "paid", "", "1111"),
    ("INV-7001", "A1007", 49.0, "USD", "2026-09-01", "failed", "card_expired", "9999"),
    ("INV-8001", "A1008", 49.0, "INR", "2026-09-15", "paid", "", "2222"),
]

PLATFORM_STATUS = [
    ("api", "operational", "", "2026-10-06T08:00:00Z"),
    ("workflow-engine", "operational", "", "2026-10-06T08:00:00Z"),
    ("connectors", "degraded", "INC-2026-1004", "2026-10-06T07:45:00Z"),
    ("billing", "operational", "", "2026-10-06T08:00:00Z"),
]


# Point SQLITE_PATH at a fresh temp file, create tables, seed policies, insert the edge-case rows.
@pytest.fixture
def edge_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(path))
    seed()  # also runs db.init_db()
    with db.connect() as conn:
        conn.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)", ACCOUNTS)
        conn.executemany("INSERT INTO usage VALUES (?, ?, ?, ?, ?)", USAGE)
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", INVOICES)
        conn.executemany("INSERT INTO platform_status VALUES (?, ?, ?, ?)", PLATFORM_STATUS)
    return path

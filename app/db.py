"""SQLite access: one connection helper, table creation, ID counters and policy lookups.

The seven Annex C tables are created exactly as the guide defines them (judges load
their own CSVs into them). We add sources, audit_log, conversations, messages, counters.
"""
import datetime
import sqlite3

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY, company_name TEXT, owner_email TEXT, plan TEXT,
    status TEXT, product_version TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plan_limits (
    plan TEXT PRIMARY KEY, api_rate_limit_per_min INTEGER, monthly_workflow_runs INTEGER,
    seats INTEGER, support_tier TEXT, monthly_price REAL);
CREATE TABLE IF NOT EXISTS usage (
    account_id TEXT REFERENCES accounts(account_id), period TEXT, workflow_runs INTEGER,
    api_calls_peak_per_min INTEGER, seats_used INTEGER, PRIMARY KEY (account_id, period));
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY, account_id TEXT REFERENCES accounts(account_id), amount REAL,
    currency TEXT, charged_on TEXT, status TEXT, failure_reason TEXT, card_last4 TEXT);
CREATE TABLE IF NOT EXISTS platform_status (
    component TEXT PRIMARY KEY, status TEXT, incident_id TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS policy_registry (
    rule_id TEXT PRIMARY KEY, description TEXT, parameter TEXT, operator TEXT, value TEXT,
    scope_plans TEXT, effective_from TEXT, source_id TEXT, source_section TEXT);
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY, conversation_id TEXT, account_id TEXT, queue TEXT,
    priority TEXT, created_at TEXT, bundle_json TEXT);
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY, doc_type TEXT, title TEXT, authority_level INTEGER,
    product_versions TEXT, last_updated TEXT, effective_from TEXT, deprecated_on TEXT,
    supersedes TEXT, provenance TEXT, synthetic TEXT, tags TEXT, file_path TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
    trace_id TEXT PRIMARY KEY, created_at TEXT, record_json TEXT);
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY, account_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT,
    text_redacted TEXT, answer_type TEXT, trace_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER);
"""


# Open a connection to the SQLite file; rows behave like dicts (row["plan"]).
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.SQLITE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# Create every table if it does not exist yet; safe to call on every startup.
def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# Return the next sequential ID for a prefix, e.g. next_id("H") -> "H-0001", then "H-0002".
def next_id(prefix: str) -> str:
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO counters (name, value) VALUES (?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1 RETURNING value",
            (prefix,),
        ).fetchone()
    return f"{prefix}-{row['value']:04d}"


# Look up a threshold in policy_registry and return (value, rule_id).
# Picks the newest row in effect on as_of_date whose scope_plans is ALL or includes the plan.
def get_policy(parameter: str, plan: str | None = None, as_of_date=None) -> tuple[str, str]:
    as_of = str(as_of_date or datetime.date.today())
    with connect() as conn:
        rows = conn.execute(
            "SELECT rule_id, value, scope_plans FROM policy_registry "
            "WHERE parameter = ? AND effective_from <= ? ORDER BY effective_from DESC",
            (parameter, as_of),
        ).fetchall()
    for row in rows:
        scope = (row["scope_plans"] or "").strip()
        if scope == "ALL" or (plan and plan in [p.strip() for p in scope.split(";")]):
            return row["value"], row["rule_id"]
    raise KeyError(f"no policy_registry row for {parameter!r} (plan={plan}, as_of={as_of})")

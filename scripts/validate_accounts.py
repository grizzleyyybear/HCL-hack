"""Validate account data against the Annex C schema and logic rules. Area: data and tools.

Usage: python scripts/validate_accounts.py
Checks data/accounts/*.csv, prints the report and writes data/accounts/validation_report.txt.

The Pydantic row models below are the single definition of the Annex C tables: the generator,
this validator and the loader (scripts/load_accounts.py) all use them.
"""
import csv
import datetime
import pathlib
import re
import sys
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, ValidationError, model_validator

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # lets "python scripts/validate_accounts.py" import app.*

from app.config import settings  # noqa: E402

# Tables in a safe load order: plans before accounts, accounts before usage and invoices.
TABLE_ORDER = ["plan_limits", "accounts", "usage", "invoices", "platform_status", "policy_registry"]
KEYS = {"plan_limits": ["plan"], "accounts": ["account_id"], "usage": ["account_id", "period"],
        "invoices": ["invoice_id"], "platform_status": ["component"], "policy_registry": ["rule_id"]}
CARD_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")  # 13-19 digits, maybe with spaces/dashes


# Reject text that is not a real calendar date written YYYY-MM-DD.
def _date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("must be a date written YYYY-MM-DD")
    datetime.date.fromisoformat(value)  # raises for impossible dates such as 2026-02-30
    return value


# Reject text that is not a month written YYYY-MM.
def _period(value: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("must be a month written YYYY-MM")
    return value


# Reject text that is not an ISO timestamp such as 2026-10-06T08:00:00Z.
def _timestamp(value: str) -> str:
    if not re.match(r"\d{4}-\d{2}-\d{2}T", value):
        raise ValueError("must be an ISO timestamp like 2026-10-06T08:00:00Z")
    datetime.datetime.fromisoformat(value)
    return value


# Only synthetic @example.com addresses are allowed (no real personal data).
def _example_email(value: str) -> str:
    if not re.fullmatch(r"[\w.+-]+@example\.com", value):
        raise ValueError("must be an @example.com address")
    return value


Date = Annotated[str, AfterValidator(_date)]
Period = Annotated[str, AfterValidator(_period)]
Timestamp = Annotated[str, AfterValidator(_timestamp)]
ExampleEmail = Annotated[str, AfterValidator(_example_email)]
AccountId = Annotated[str, Field(pattern=r"^A\d{4}$")]
Plan = Literal["Free", "Pro", "Business", "Enterprise"]


class AccountRow(BaseModel):
    account_id: AccountId
    company_name: str = Field(min_length=1)
    owner_email: ExampleEmail
    plan: Plan
    status: Literal["active", "past_due", "suspended", "cancelled"]
    product_version: str = Field(min_length=1)
    created_at: Date


class PlanLimitRow(BaseModel):
    plan: Plan
    api_rate_limit_per_min: int = Field(ge=0)
    monthly_workflow_runs: int = Field(ge=0)
    seats: int = Field(ge=0)
    support_tier: Literal["standard", "priority"]
    monthly_price: float = Field(ge=0)


class UsageRow(BaseModel):
    account_id: AccountId
    period: Period
    workflow_runs: int = Field(ge=0)
    api_calls_peak_per_min: int = Field(ge=0)
    seats_used: int = Field(ge=0)


class InvoiceRow(BaseModel):
    invoice_id: str = Field(min_length=1)
    account_id: AccountId
    amount: float = Field(gt=0)
    currency: Literal["USD", "INR"]
    charged_on: Date
    status: Literal["paid", "failed", "refunded"]
    failure_reason: str = ""
    card_last4: str = Field(pattern=r"^\d{4}$")

    # failure_reason is only filled in for failed payments.
    @model_validator(mode="after")
    def _reason_only_when_failed(self):
        if self.failure_reason and self.status != "failed":
            raise ValueError("failure_reason must be empty unless status is failed")
        return self


class PlatformStatusRow(BaseModel):
    component: str = Field(min_length=1)
    status: Literal["operational", "degraded", "outage"]
    incident_id: str = ""
    updated_at: Timestamp


class PolicyRow(BaseModel):
    rule_id: str = Field(min_length=1)
    description: str = ""
    parameter: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: str
    scope_plans: str = Field(min_length=1)
    effective_from: Date
    source_id: str = ""
    source_section: str = ""


MODELS = {"plan_limits": PlanLimitRow, "accounts": AccountRow, "usage": UsageRow, "invoices": InvoiceRow,
          "platform_status": PlatformStatusRow, "policy_registry": PolicyRow}


# Column names of a table, in Annex C order (taken from the row model).
def columns(table: str) -> list[str]:
    return list(MODELS[table].model_fields)


# Turn a Pydantic error into short "field: message" lines (never echoes the bad value itself).
def error_lines(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in exc.errors()]


# Find every problem. Each problem names its row and says if it is "hard" (the loader must skip
# that row) or soft (a cross-table consistency warning; the row can still be loaded).
# known_accounts: account IDs already in the database (the loader passes them in).
def find_problems(tables: dict, check_reserved: bool = True, known_accounts=()) -> list[dict]:
    problems = []
    good_accounts = set(known_accounts)

    def add(table, index, row, text, hard=True):
        key = "/".join(str(row.get(k, "?")) for k in KEYS[table])
        problems.append({"table": table, "index": index, "hard": hard, "message": f"{table}[{key}]: {text}"})

    for table in TABLE_ORDER:  # accounts are checked before usage/invoices that point at them
        seen_keys = set()
        for i, row in enumerate(tables.get(table, [])):
            before = len(problems)
            try:
                MODELS[table].model_validate(row)
            except ValidationError as exc:
                for line in error_lines(exc):
                    add(table, i, row, line)
            for field, value in row.items():
                if isinstance(value, str) and CARD_NUMBER.search(value):
                    add(table, i, row, f"{field}: looks like a full card number (only the last 4 digits are allowed)")
            account_id = str(row.get("account_id", ""))
            if check_reserved and re.fullmatch(r"A9\d{3}", account_id):
                add(table, i, row, "account_id is in the judge-reserved range A9000-A9999")
            if check_reserved and str(row.get("invoice_id", "")).startswith("INV-J"):
                add(table, i, row, "invoice_id uses the judge-reserved prefix INV-J")
            if table in ("usage", "invoices") and account_id not in good_accounts:
                add(table, i, row, f"account_id {account_id} does not exist")
            if table == "accounts" and len(problems) == before:
                good_accounts.add(account_id)
            key = tuple(str(row.get(k, "")) for k in KEYS[table])
            if key in seen_keys:
                add(table, i, row, "duplicate key (the last row wins)", hard=False)
            seen_keys.add(key)

    # Cross-table consistency, only when both tables are part of this batch.
    if "accounts" in tables and "invoices" in tables:
        failed = {r.get("account_id") for r in tables["invoices"] if r.get("status") == "failed"}
        billed = {r.get("account_id") for r in tables["invoices"]}
        for i, acc in enumerate(tables["accounts"]):
            if acc.get("status") in ("past_due", "suspended") and acc.get("account_id") not in failed:
                add("accounts", i, acc, f"status {acc.get('status')} but no failed invoice", hard=False)
            if acc.get("plan") == "Free" and acc.get("account_id") in billed:
                add("accounts", i, acc, "Free plan account has invoices", hard=False)
    return problems


# Check every table's rows; check_reserved=False skips the judge-ID check (used by the loader).
def validate(tables: dict, check_reserved: bool = True) -> list[str]:
    return [p["message"] for p in find_problems(tables, check_reserved)]


# Read every Annex C CSV present in a folder; returns (tables, names of the files that are missing).
def read_tables(folder) -> tuple[dict, list[str]]:
    tables, missing = {}, []
    for table in TABLE_ORDER:
        path = pathlib.Path(folder) / f"{table}.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:  # utf-8-sig copes with Excel's BOM
            tables[table] = [{k.strip(): (v or "").strip() for k, v in row.items() if k}
                             for row in csv.DictReader(f)]
    return tables, missing


CHECKS_RUN = [
    "account_id matches ^A\\d{4}$ and is not in A9000-A9999; invoice_id does not start with INV-J",
    "plan, status, currency, support_tier and component status are in the allowed sets",
    "every usage and invoice account_id exists in accounts",
    "owner_email ends with @example.com; card_last4 is exactly 4 digits; no 13-19 digit card number in any cell",
    "amount > 0; usage and limits are non-negative integers; failure_reason empty unless status = failed",
    "past_due and suspended accounts have a failed invoice; Free accounts have no invoices",
    "dates are valid YYYY-MM-DD, periods YYYY-MM, updated_at an ISO timestamp; no duplicate keys",
]


# CLI: validate our generated CSVs, print the report and save it next to them.
def main() -> int:
    folder = pathlib.Path(settings.DATA_DIR) / "accounts"
    tables, missing = read_tables(folder)
    problems = validate(tables)
    lines = [f"Validation report for data/accounts (run on {datetime.date.today()})", "", "Checks run:"]
    lines += [f"- {c}" for c in CHECKS_RUN] + ["", "Rows checked:"]
    lines += [f"- {table}.csv: {len(rows)} rows" for table, rows in tables.items()]
    lines += [f"- {name}: not present (optional)" for name in missing]
    lines += ["", f"Violations: {len(problems)}"] + [f"- {p}" for p in problems]
    report = "\n".join(lines) + "\n"
    print(report)
    (folder / "validation_report.txt").write_text(report, encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

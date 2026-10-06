"""Generate the synthetic CloudFlow account data (Annex C tables) into data/accounts/*.csv. Owner: A3.

  python scripts/generate_accounts.py          REPLAY: reuse the saved LLM reply (no LLM needed)
  python scripts/generate_accounts.py --live   LIVE: ask the LLM again (Ollama via app.llm.call_json)

Where each part comes from:
- Edge cases A1001-A1008, plan_limits and platform_status: fixed specs in this file (guaranteed rows).
- Filler accounts A1009+: the LLM, prompted with data/generation/prompts/accounts_v1.md. Every row is
  validated with Pydantic. LIVE mode re-asks for invalid rows up to 2 times; whatever is still invalid
  gets a safe, logged code repair or is dropped. Every reply is saved in data/generation/accounts_batches/.
- Filler invoices: computed in code from the plan price (the LLM never does money arithmetic):
  monthly on the billing day (= created_at day) for Aug-Oct 2026 up to 2026-10-06; past_due and
  suspended accounts have their last invoice failed (suspended: no charge this month); cancelled
  accounts (cancelled 2026-08-31) have no invoices after that, and their last one is refunded if it
  was inside the refund window. Free accounts have no invoices.
Writes data/accounts/<table>.csv and data/generation/accounts_generation_log.json.
"""
import argparse
import csv
import datetime
import json
import pathlib
import re
import sys
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # lets "python scripts/generate_accounts.py" import app.* and scripts.*

from scripts.validate_accounts import AccountRow, MODELS, columns, error_lines, validate  # noqa: E402

PROMPT_FILE = ROOT / "data/generation/prompts/accounts_v1.md"
BATCH_FILE = ROOT / "data/generation/accounts_batches/batch_01.json"
LOG_FILE = ROOT / "data/generation/accounts_generation_log.json"
OUT_DIR = ROOT / "data/accounts"

REF_DATE = datetime.date(2026, 10, 6)
USAGE_PERIODS = ["2026-10", "2026-09"]
INVOICE_MONTHS = [(2026, 8), (2026, 9), (2026, 10)]
CANCELLED_ON = datetime.date(2026, 8, 31)
REFUND_WINDOW_DAYS = 14  # from cloudflow_facts.md / POL-REFUND-001; only shapes synthetic history here
USD_TO_INR = 83.7        # INR prices = USD price x 83.7, rounded to the nearest 100 (Pro 4,100)
FAILURE_REASONS = ["card_declined", "insufficient_funds", "card_expired"]
MAX_RETRIES = 2

# Plan limits exactly as cloudflow_facts.md and POL-LIMITS-001.
PLAN_LIMITS = [
    {"plan": "Free", "api_rate_limit_per_min": 60, "monthly_workflow_runs": 500, "seats": 1,
     "support_tier": "standard", "monthly_price": 0.0},
    {"plan": "Pro", "api_rate_limit_per_min": 300, "monthly_workflow_runs": 10000, "seats": 5,
     "support_tier": "standard", "monthly_price": 49.0},
    {"plan": "Business", "api_rate_limit_per_min": 1000, "monthly_workflow_runs": 50000, "seats": 25,
     "support_tier": "priority", "monthly_price": 199.0},
    {"plan": "Enterprise", "api_rate_limit_per_min": 5000, "monthly_workflow_runs": 500000, "seats": 200,
     "support_tier": "priority", "monthly_price": 999.0},
]
LIMITS = {row["plan"]: row for row in PLAN_LIMITS}

PLATFORM_STATUS = [
    {"component": "api", "status": "operational", "incident_id": "", "updated_at": "2026-10-06T08:00:00Z"},
    {"component": "workflow-engine", "status": "degraded", "incident_id": "INC-2026-1004",
     "updated_at": "2026-10-06T07:45:00Z"},
    {"component": "connectors", "status": "operational", "incident_id": "", "updated_at": "2026-10-06T08:00:00Z"},
    {"component": "billing", "status": "operational", "incident_id": "", "updated_at": "2026-10-06T08:00:00Z"},
]

# Edge cases from CLAUDE.md (reference date 2026-10-06, refund window 14 days). Fixed, never LLM-made.
EDGE_ACCOUNTS = [  # account_id, company_name, owner_email, plan, status, product_version, created_at
    ("A1001", "Northwind Labs", "priya.nair@example.com", "Pro", "active", "4.3", "2025-01-10"),     # usage exactly at limit
    ("A1002", "Bluebird Ops", "tom.becker@example.com", "Pro", "active", "4.3", "2025-02-11"),       # one unit over limit
    ("A1003", "Cedar Analytics", "lena.okafor@example.com", "Pro", "past_due", "4.2", "2025-03-01"),  # failed payment
    ("A1004", "Delta Freight", "raj.malhotra@example.com", "Pro", "active", "4.4", "2025-04-01"),    # duplicate charge
    ("A1005", "Ember Health", "sofia.lind@example.com", "Business", "active", "4.3", "2025-05-22"),  # last day of window
    ("A1006", "Fjord Retail", "erik.dahl@example.com", "Pro", "active", "4.4", "2025-06-21"),        # one day after window
    ("A1007", "Granite Works", "ana.costa@example.com", "Pro", "suspended", "4.3", "2024-07-01"),    # suspended
    ("A1008", "Harbor Legacy", "vikram.shah@example.com", "Pro", "active", "3.8", "2024-08-17"),     # old product version
]
EDGE_USAGE = [  # account_id, period, workflow_runs, api_calls_peak_per_min, seats_used
    ("A1001", "2026-10", 10000, 300, 5), ("A1001", "2026-09", 9420, 276, 5),   # exactly at every Pro limit
    ("A1002", "2026-10", 10001, 301, 3), ("A1002", "2026-09", 9875, 288, 3),   # one over: runs and API rate
    ("A1003", "2026-10", 1200, 40, 2), ("A1003", "2026-09", 4310, 95, 2),
    ("A1004", "2026-10", 3000, 120, 4), ("A1004", "2026-09", 7420, 180, 4),
    ("A1005", "2026-10", 8150, 420, 12), ("A1005", "2026-09", 38900, 610, 12),
    ("A1006", "2026-10", 1430, 85, 2), ("A1006", "2026-09", 6120, 150, 2),
    ("A1007", "2026-10", 0, 0, 3), ("A1007", "2026-09", 2150, 60, 3),          # paused since suspension
    ("A1008", "2026-10", 640, 45, 2), ("A1008", "2026-09", 3280, 70, 2),
]
EDGE_INVOICES = [  # invoice_id, account_id, amount, currency, charged_on, status, failure_reason, card_last4
    ("INV-6101", "A1001", 49.0, "USD", "2026-08-10", "paid", "", "4242"),
    ("INV-6102", "A1001", 49.0, "USD", "2026-09-10", "paid", "", "4242"),
    ("INV-6201", "A1002", 49.0, "USD", "2026-08-11", "paid", "", "1881"),
    ("INV-6202", "A1002", 49.0, "USD", "2026-09-11", "paid", "", "1881"),
    ("INV-6301", "A1003", 49.0, "USD", "2026-08-01", "paid", "", "0341"),
    ("INV-6302", "A1003", 49.0, "USD", "2026-09-01", "paid", "", "0341"),
    ("INV-6303", "A1003", 49.0, "USD", "2026-10-01", "failed", "card_declined", "0341"),
    ("INV-6401", "A1004", 49.0, "USD", "2026-08-01", "paid", "", "5556"),
    ("INV-6402", "A1004", 49.0, "USD", "2026-09-01", "paid", "", "5556"),
    ("INV-6001", "A1004", 49.0, "USD", "2026-10-01", "paid", "", "5556"),    # duplicate charge:
    ("INV-6002", "A1004", 49.0, "USD", "2026-10-01", "paid", "", "5556"),    # same amount, same day
    ("INV-6501", "A1005", 199.0, "USD", "2026-08-22", "paid", "", "4444"),
    ("INV-6502", "A1005", 199.0, "USD", "2026-09-22", "paid", "", "4444"),   # 14 days before: last day
    ("INV-6601", "A1006", 49.0, "USD", "2026-08-21", "paid", "", "7719"),
    ("INV-6602", "A1006", 49.0, "USD", "2026-09-21", "paid", "", "7719"),    # 15 days before: too late
    ("INV-6701", "A1007", 49.0, "USD", "2026-08-01", "paid", "", "9905"),
    ("INV-6702", "A1007", 49.0, "USD", "2026-09-01", "failed", "card_expired", "9905"),
    ("INV-6801", "A1008", 4100.0, "INR", "2026-08-17", "paid", "", "2222"),
    ("INV-6802", "A1008", 4100.0, "INR", "2026-09-17", "paid", "", "2222"),
]
FIRST_FILLER_INVOICE = 7001


class PeriodUsage(BaseModel):
    period: Literal["2026-10", "2026-09"]
    workflow_runs: int = Field(ge=0)
    api_calls_peak_per_min: int = Field(ge=0)
    seats_used: int = Field(ge=0)


class FillerAccount(AccountRow):
    """One account as the LLM must return it: the Annex C account row plus billing hints and usage."""
    product_version: Literal["3.8", "4.2", "4.3", "4.4"]
    currency: Literal["USD", "INR"]
    card_last4: str = ""
    usage: list[PeriodUsage]

    # Rules that need several fields at once.
    @model_validator(mode="after")
    def _cross_checks(self):
        if re.fullmatch(r"A9\d{3}", self.account_id):
            raise ValueError("account_id is in the judge-reserved range A9000-A9999")
        if self.plan != "Free" and not re.fullmatch(r"\d{4}", self.card_last4):
            raise ValueError("card_last4 must be exactly the last 4 digits of the card")
        if self.plan == "Free" and self.status in ("past_due", "suspended"):
            raise ValueError("a Free account is never charged, so it cannot be past_due or suspended")
        if sorted(u.period for u in self.usage) != sorted(USAGE_PERIODS):
            raise ValueError(f"usage must have exactly one row for each period {USAGE_PERIODS}")
        if any(u.seats_used > LIMITS[self.plan]["seats"] for u in self.usage):
            raise ValueError("seats_used is above the plan's seat limit")
        return self


class LLMReply(BaseModel):
    """Outer shape of the LLM reply; rows stay raw dicts so each one is validated on its own."""
    accounts: list[dict]


# Return the validation errors of one LLM row (an empty list means the row is valid).
def filler_errors(row) -> list[str]:
    try:
        FillerAccount.model_validate(row)
        return []
    except ValidationError as exc:
        return error_lines(exc)


# Safe code repairs for known LLM slips, applied only after the LLM could not fix the row itself.
def repair(row: dict) -> tuple[dict, list[str]]:
    row, fixes = dict(row), []
    email = str(row.get("owner_email", ""))
    if "@" in email and not email.endswith("@example.com"):
        row["owner_email"] = email.split("@")[0] + "@example.com"
        fixes.append("owner_email domain replaced with example.com")
    digits = re.sub(r"\D", "", str(row.get("card_last4", "")))
    if len(digits) > 4:
        row["card_last4"] = digits[-4:]
        fixes.append("full card number cut down to its last 4 digits")
    return row, fixes


# Apply the saved replies in order: the n-th corrected row of a retry replaces the n-th row still invalid.
def current_rows(responses: list[dict]) -> list[dict]:
    rows = list(responses[0]["rows"])
    for response in responses[1:]:
        still_bad = [i for i, row in enumerate(rows) if filler_errors(row)]
        for i, fixed in zip(still_bad, response["rows"]):
            rows[i] = fixed
    return rows


# Turn the saved LLM replies into valid filler accounts plus a log of every mistake that was caught.
def clean_rows(responses: list[dict]) -> tuple[list[FillerAccount], list[dict]]:
    accepted, mistakes = [], []
    seen = {acc[0] for acc in EDGE_ACCOUNTS}
    for original, row in zip(responses[0]["rows"], current_rows(responses)):
        errors = filler_errors(original)
        if errors:
            entry = {"account_id": original.get("account_id"), "errors": errors}
            if not filler_errors(row):
                entry["action"] = "fixed by an LLM retry"
            else:
                row, fixes = repair(row)
                entry["action"] = "repaired in code: " + "; ".join(fixes) if not filler_errors(row) else "dropped"
            mistakes.append(entry)
            if entry["action"] == "dropped":
                continue
        account = FillerAccount.model_validate(row)
        if account.account_id in seen:
            mistakes.append({"account_id": account.account_id, "errors": ["duplicate account_id"], "action": "dropped"})
            continue
        seen.add(account.account_id)
        accepted.append(account)
    return accepted, mistakes


# Price of one month on a plan in the account's currency.
def monthly_price(plan: str, currency: str) -> float:
    usd = LIMITS[plan]["monthly_price"]
    return usd if currency == "USD" else round(usd * USD_TO_INR, -2)


# The monthly invoices of one filler account, consistent with its status (rules in the module docstring).
def filler_invoices(acc: FillerAccount, failure_reason: str) -> list[dict]:
    if acc.plan == "Free":
        return []
    created = datetime.date.fromisoformat(acc.created_at)
    dates = [datetime.date(y, m, min(created.day, 28)) for y, m in INVOICE_MONTHS]
    dates = [d for d in dates if created <= d <= REF_DATE]
    if acc.status == "suspended":
        dates = [d for d in dates if d < REF_DATE.replace(day=1)]  # no new charge while suspended
    if acc.status == "cancelled":
        dates = [d for d in dates if d <= CANCELLED_ON]
    invoices = [{"account_id": acc.account_id, "amount": monthly_price(acc.plan, acc.currency),
                 "currency": acc.currency, "charged_on": str(d), "status": "paid", "failure_reason": "",
                 "card_last4": acc.card_last4} for d in dates]
    if invoices and acc.status in ("past_due", "suspended"):
        invoices[-1].update(status="failed", failure_reason=failure_reason)
    if invoices and acc.status == "cancelled" and (CANCELLED_ON - dates[-1]).days <= REFUND_WINDOW_DAYS:
        invoices[-1]["status"] = "refunded"
    return invoices


# Build every table: fixed specs plus the validated filler accounts.
def build_tables(fillers: list[FillerAccount]) -> dict:
    tables = {
        "plan_limits": PLAN_LIMITS,
        "accounts": [dict(zip(columns("accounts"), row)) for row in EDGE_ACCOUNTS],
        "usage": [dict(zip(columns("usage"), row)) for row in EDGE_USAGE],
        "invoices": [dict(zip(columns("invoices"), row)) for row in EDGE_INVOICES],
        "platform_status": PLATFORM_STATUS,
    }
    filler_invoice_rows, failures = [], 0
    for acc in fillers:
        tables["accounts"].append(acc.model_dump(include=set(columns("accounts"))))
        tables["usage"] += [{"account_id": acc.account_id, **u.model_dump()} for u in acc.usage]
        filler_invoice_rows += filler_invoices(acc, FAILURE_REASONS[failures % len(FAILURE_REASONS)])
        failures += acc.status in ("past_due", "suspended")
    for number, invoice in enumerate(filler_invoice_rows, start=FIRST_FILLER_INVOICE):
        tables["invoices"].append({"invoice_id": f"INV-{number}", **invoice})
    return tables


# Send one prompt through app.llm.call_json and return (rows, usage).
def ask_llm(prompt_text: str, tag: str) -> tuple[list[dict], dict]:
    from app import llm  # imported here so REPLAY mode never needs the LLM client
    prompt_path = BATCH_FILE.parent / f"{tag}.prompt.txt"  # the exact text of every call is kept
    prompt_path.write_text(prompt_text, encoding="utf-8")
    # call_json loads "<name>.txt" from app/prompts; an absolute name makes it load our saved prompt.
    reply, usage = llm.call_json(str(prompt_path.with_suffix("")), {}, LLMReply, lambda: LLMReply(accounts=[]))
    return reply.accounts, usage


# LIVE mode: ask the LLM, re-ask up to MAX_RETRIES times for rows that are still invalid, save every reply.
def generate_live() -> dict:
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    rows, usage = ask_llm(prompt, "batch_01_attempt0")
    if not rows:
        sys.exit("The LLM returned no rows (MOCK_LLM=true or Ollama unreachable). Run without --live to replay.")
    responses = [{"attempt": 0, "rows": rows}]
    for attempt in range(1, MAX_RETRIES + 1):
        bad = [{"row": r, "errors": filler_errors(r)} for r in current_rows(responses) if filler_errors(r)]
        if not bad:
            break
        retry_prompt = (prompt + "\n\n## Correction needed\n\nThese rows break the rules above. Return "
                        '{"accounts": [...]} with one corrected row for each, in the same order.\n\n'
                        + json.dumps(bad, indent=1))
        rows, _ = ask_llm(retry_prompt, f"batch_01_attempt{attempt}")
        responses.append({"attempt": attempt, "rows": rows})
    batch = {"batch": "batch_01", "prompt_file": "data/generation/prompts/accounts_v1.md",
             "model": usage.get("model"), "temperature": "set by app.llm (0.1)", "responses": responses}
    BATCH_FILE.write_text(json.dumps(batch, indent=1), encoding="utf-8")
    return batch


# Write one table to data/accounts/<table>.csv with the Annex C column order.
def write_csv(table: str, rows: list[dict]) -> None:
    with (OUT_DIR / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns(table))
        writer.writeheader()
        writer.writerows(rows)


# Run the whole generation: get the LLM rows, clean them, build and validate the tables, write files.
def main(live: bool = False) -> dict:
    batch = generate_live() if live else json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    fillers, mistakes = clean_rows(batch["responses"])
    tables = build_tables(fillers)
    problems = validate(tables)
    if problems:
        sys.exit("Generated data has violations:\n" + "\n".join(problems))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for table in MODELS:
        if table in tables:
            write_csv(table, tables[table])
    log = {
        "mode": "live" if live else "replay",
        "model": batch["model"], "temperature": batch["temperature"],
        "llm_calls": len(batch["responses"]),
        "prompt_file": batch["prompt_file"],
        "batch_file": "data/generation/accounts_batches/batch_01.json",
        "filler_rows_generated": len(batch["responses"][0]["rows"]),
        "filler_rows_accepted": len(fillers),
        "what_the_llm_got_wrong": mistakes,
        "fixed_spec_rows": {"edge_case_accounts": len(EDGE_ACCOUNTS), "plan_limits": len(PLAN_LIMITS),
                            "platform_status": len(PLATFORM_STATUS)},
        "row_counts": {table: len(rows) for table, rows in tables.items()},
        "accounts_by_plan": dict(Counter(a["plan"] for a in tables["accounts"])),
        "accounts_by_status": dict(Counter(a["status"] for a in tables["accounts"])),
        "invoices_by_status": dict(Counter(i["status"] for i in tables["invoices"])),
        "validation_violations": 0,
    }
    LOG_FILE.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    return log


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic CloudFlow account data.")
    parser.add_argument("--live", action="store_true", help="call the LLM instead of replaying the saved reply")
    print(json.dumps(main(parser.parse_args().live), indent=2))

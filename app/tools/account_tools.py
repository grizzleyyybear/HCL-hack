"""Account tools: lookup_account, get_usage, get_plan_limits. Area: data and tools."""
import datetime

from app import db


# Return plan, status, product_version, created_at for the account (never owner_email).
def lookup_account(account_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT account_id, plan, status, product_version, created_at FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    if row is None:
        return {"error": "account_not_found"}
    return dict(row)


# Return workflow_runs, api_calls_peak_per_min, seats_used for a period (default: as_of_date month).
def get_usage(account_id: str, period: str | None = None, as_of_date=None) -> dict:
    period = period or str(as_of_date or datetime.date.today())[:7]  # "2026-10-06" -> "2026-10"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT account_id, period, workflow_runs, api_calls_peak_per_min, seats_used "
            "FROM usage WHERE account_id = ? AND period = ?",
            (account_id, period),
        ).fetchone()
    if row is None:
        return {"error": "usage_not_found", "period": period}
    return dict(row)


# Return the plan's limits; when usage is given, add over_limit flags (over means strictly greater).
def get_plan_limits(plan: str, usage: dict | None = None) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT plan, api_rate_limit_per_min, monthly_workflow_runs, seats, support_tier "
            "FROM plan_limits WHERE plan = ?",
            (plan,),
        ).fetchone()
    if row is None:
        return {"error": "plan_not_found"}
    result = dict(row)
    # LIMITS-REF-01 says the plan_limits table is the source of truth; return its rule_id so answers can cite it.
    _, result["rule_id"] = db.get_policy("plan_limits_source", plan)
    if usage and "error" not in usage:
        # Strictly greater-than: usage exactly at the limit is NOT over (edge case A1001).
        result["workflow_runs_over"] = usage["workflow_runs"] > row["monthly_workflow_runs"]
        result["api_rate_over"] = usage["api_calls_peak_per_min"] > row["api_rate_limit_per_min"]
        result["seats_over"] = usage["seats_used"] > row["seats"]
    return result

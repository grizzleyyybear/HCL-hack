"""Billing tools: get_invoices, check_refund_eligibility. Area: data and tools. Never executes a refund."""
import datetime

from app import db
from app.tools.account_tools import lookup_account

INVOICE_COLUMNS = "invoice_id, amount, currency, charged_on, status, failure_reason, card_last4"


# Return the account's invoices plus possible_duplicates (same amount and same charged_on).
def get_invoices(account_id: str, status: str | None = None, date_from: str | None = None,
                 date_to: str | None = None) -> dict:
    account = lookup_account(account_id)
    if "error" in account:
        return account
    sql = f"SELECT {INVOICE_COLUMNS} FROM invoices WHERE account_id = ?"
    params = [account_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if date_from:
        sql += " AND charged_on >= ?"
        params.append(str(date_from))
    if date_to:
        sql += " AND charged_on <= ?"
        params.append(str(date_to))
    with db.connect() as conn:
        invoices = [dict(r) for r in conn.execute(sql + " ORDER BY charged_on DESC, invoice_id", params)]

    # Group charges by (amount, charged_on); any group with 2+ invoices is a possible duplicate.
    # Failed invoices are skipped because the customer was never actually charged.
    groups: dict[tuple, list[str]] = {}
    for inv in invoices:
        if inv["status"] != "failed":
            groups.setdefault((inv["amount"], inv["charged_on"]), []).append(inv["invoice_id"])
    duplicates = [{"invoice_ids": ids, "amount": amount, "charged_on": charged_on}
                  for (amount, charged_on), ids in groups.items() if len(ids) > 1]
    return {"invoices": invoices, "possible_duplicates": duplicates}


# Decide refund eligibility from policy_registry values; returns eligible, days, window, rule_id.
def check_refund_eligibility(account_id: str, as_of_date, invoice_id: str | None = None) -> dict:
    account = lookup_account(account_id)
    if "error" in account:
        return account
    as_of = datetime.date.fromisoformat(str(as_of_date or datetime.date.today()))
    plan = account["plan"]

    # Both thresholds come from policy_registry, read fresh on every call (no restart after a rule change).
    window_value, window_rule = db.get_policy("refund_window_days", plan, as_of)
    plans_value, plans_rule = db.get_policy("refund_allowed_plans", plan, as_of)
    window_days = int(window_value)
    allowed_plans = [p.strip() for p in plans_value.split(";")]

    with db.connect() as conn:
        if invoice_id:
            # account_id in the WHERE clause: a customer can only check their own invoices.
            invoice = conn.execute(f"SELECT {INVOICE_COLUMNS} FROM invoices WHERE invoice_id = ? AND account_id = ?",
                                   (invoice_id, account_id)).fetchone()
            if invoice is None:
                return {"error": "invoice_not_found"}
        else:
            invoice = conn.execute(f"SELECT {INVOICE_COLUMNS} FROM invoices WHERE account_id = ? AND status = 'paid' "
                                   "ORDER BY charged_on DESC, invoice_id DESC LIMIT 1", (account_id,)).fetchone()

    reasons = []
    if plan not in allowed_plans:
        reasons.append("plan_not_eligible")
    days = None
    if invoice is None:
        reasons.append("no_paid_invoice")
    else:
        days = (as_of - datetime.date.fromisoformat(invoice["charged_on"])).days
        if invoice["status"] != "paid":
            reasons.append("invoice_not_paid")
        if days > window_days:
            reasons.append("outside_refund_window")

    return {
        "eligible": not reasons,
        "invoice_id": invoice["invoice_id"] if invoice else None,
        "plan": plan,
        "days_since_charge": days,
        "window_days": window_days,
        "rule_id": window_rule,
        "plan_rule_id": plans_rule,
        "reasons": reasons,
        "refund_executed": False,  # this tool only checks; refunds are approved and issued by the billing team
    }

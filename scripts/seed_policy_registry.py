"""Seed policy_registry with every threshold the code uses (CLAUDE.md table). Owner: A7 tools-policy.

Also seeds the 4 plan_limits rows (they must equal POL-LIMITS-001 and data/generation/cloudflow_facts.md).
Usage: python scripts/seed_policy_registry.py [--force]
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # so "from app import db" works as a script

from app import db  # noqa: E402

# (rule_id, description, parameter, operator, value, scope_plans, effective_from, source_id, source_section)
POLICY_ROWS = [
    ("REFUND-WINDOW-01", "Paid invoices can be refunded within this many days of the charge date",
     "refund_window_days", "<=", "14", "ALL", "2026-01-01", "POL-REFUND-001", "Refund window"),
    ("REFUND-FREE-01", "Only these plans are eligible for refunds (Free has no charges)",
     "refund_allowed_plans", "in", "Pro;Business;Enterprise", "ALL", "2026-01-01", "POL-REFUND-001", "Eligibility"),
    ("CRITIC-MIN-01", "Minimum critic groundedness score for an answer to be sent without a human",
     "critic_min_groundedness", ">=", "0.70", "ALL", "2026-01-01", "POL-ESC-001", "Answer quality"),
    ("ESC-SLA-01", "Response time after a handoff for Free and Pro plans, in hours",
     "escalation_sla_hours", "<=", "24", "Free;Pro", "2026-01-01", "POL-ESC-001", "Response times"),
    ("ESC-SLA-02", "Response time after a handoff for Business and Enterprise plans, in hours",
     "escalation_sla_hours", "<=", "4", "Business;Enterprise", "2026-01-01", "POL-ESC-001", "Response times"),
    ("ESC-REPEAT-01", "Number of contacts about the same issue that counts as repeated contact",
     "repeat_contact_threshold", ">=", "2", "ALL", "2026-01-01", "POL-ESC-001", "Repeated contact"),
    ("LIMITS-REF-01", "Plan limits are read from the plan_limits table",
     "plan_limits_source", "=", "plan_limits table", "ALL", "2026-01-01", "POL-LIMITS-001", "Plan limits"),
    ("RETRIEVAL-MIN-01", "Minimum retrieval relevance score; below it the KB is treated as not covering the question",
     "min_relevance", ">=", "0.35", "ALL", "2026-01-01", "POL-ESC-001", "Answer quality"),
]

# (plan, api_rate_limit_per_min, monthly_workflow_runs, seats, support_tier, monthly_price)
PLAN_LIMIT_ROWS = [
    ("Free", 60, 500, 1, "standard", 0.0),
    ("Pro", 300, 10000, 5, "standard", 49.0),
    ("Business", 1000, 50000, 25, "priority", 199.0),
    ("Enterprise", 5000, 500000, 200, "priority", 999.0),
]


# Insert every policy_registry and plan_limits row. Safe to run repeatedly.
# By default existing rows are kept, so the startup call never undoes a rule someone changed in the DB;
# force=True overwrites them with the values above.
def seed(force: bool = False) -> None:
    db.init_db()
    verb = "INSERT OR REPLACE" if force else "INSERT OR IGNORE"
    with db.connect() as conn:
        conn.executemany(f"{verb} INTO policy_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", POLICY_ROWS)
        conn.executemany(f"{verb} INTO plan_limits VALUES (?, ?, ?, ?, ?, ?)", PLAN_LIMIT_ROWS)


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
    print(f"Seeded {len(POLICY_ROWS)} policy_registry rows and {len(PLAN_LIMIT_ROWS)} plan_limits rows.")

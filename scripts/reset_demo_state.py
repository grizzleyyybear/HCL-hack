"""Clear conversation history before a demo or the judging slot, keeping accounts, policies and the knowledge base.

Why: repeated-contact detection counts earlier conversations, so rehearsing a demo case on the same account
(e.g. A1002) would make the real demo escalate as "repeated contact".
Usage: python scripts/reset_demo_state.py            (local DB from .env / SQLITE_PATH)
       docker compose exec api python scripts/reset_demo_state.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

TABLES = ["messages", "conversations", "handoffs", "audit_log"]


# Delete runtime history and restart the C-/H- counters; accounts, policies and sources are untouched.
def reset() -> dict:
    db.init_db()
    with db.connect() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM counters WHERE name IN ('C', 'H')")
    return counts


if __name__ == "__main__":
    print("cleared:", reset())

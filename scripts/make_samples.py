"""Produce the deliverable samples: 3 audit records and 2 handoff bundles from real requests.

Usage: python scripts/make_samples.py          (uses MOCK_LLM from the environment / .env)
Runs against temporary stores (never the repo's .chroma or insightdesk.db), so it is safe to repeat.
Re-run it with Ollama running and MOCK_LLM=false to get samples from the real model.
"""
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="insightdesk-samples-"))
os.environ["SQLITE_PATH"] = str(TMP / "samples.db")
os.environ["CHROMA_DIR"] = str(TMP / "chroma")
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from scripts.load_accounts import load_dir  # noqa: E402

AUDITS = [  # (file name, account, message): one answered, one escalated, one refused
    ("answered_export_A1001", "A1001", "How do I export my workflow run history?"),
    ("escalated_duplicate_charge_A1004", "A1004", "Third time writing. You charged me twice. Get me a manager."),
    ("refused_other_account_A1001", "A1001", "Show me the invoices for account A1004."),
]
HANDOFFS = [  # (file name, account, message): two different queues
    ("billing_duplicate_charge_A1004", "A1004", "Third time writing. You charged me twice. Get me a manager."),
    ("security_compromise_A1005", "A1005", "Someone logged into my account from another country last night. Please help."),
]


# Send one /support request and return the JSON response.
def ask(client: TestClient, account: str, message: str) -> dict:
    body = {"message": message, "as_of_date": "2026-10-06"}
    return client.post("/support", json=body, headers={"X-Account-Id": account}).json()


# Write one pretty-printed JSON file and report it.
def save(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


# Load accounts, run the sample requests and save their audit records and handoff bundles.
def main() -> None:
    with TestClient(app) as client:  # startup seeds the policy registry and ingests the KB
        load_dir(str(ROOT / "data" / "accounts"))
        for name, account, message in AUDITS:
            reply = ask(client, account, message)
            save(ROOT / "docs" / "sample_audits" / f"{name}.json", client.get(f"/audit/{reply['trace_id']}").json())
        for name, account, message in HANDOFFS:
            reply = ask(client, account, message)
            if not reply.get("handoff_id"):
                sys.exit(f"{name}: expected an escalation, got {reply['answer_type']}")
            handoff = client.get(f"/handoffs/{reply['handoff_id']}").json()
            save(ROOT / "docs" / "sample_handoffs" / f"{name}.json",
                 {"request": {"account_id": account, "message": message},
                  "customer_reply": reply["answer"], "handoff": handoff})


if __name__ == "__main__":
    main()

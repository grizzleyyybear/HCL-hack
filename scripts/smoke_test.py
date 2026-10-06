"""HTTP smoke test of the judges' live-testing paths against a RUNNING InsightDesk API.

Usage:  python scripts/smoke_test.py                      (default http://localhost:8000, e.g. docker compose)
        python scripts/smoke_test.py --base-url http://localhost:8010
        python scripts/smoke_test.py --live               (real Ollama: /health must say llm "ok")

Prints a PASS/FAIL table and exits with code 1 if any check fails. Safe to re-run: the account rows are
upserted and JD-EVAL-001 / JD-SMOKE-PDF are simply re-ingested ("replaced").
"""
import argparse
import json
import pathlib
import sys
import tempfile
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "eval" / "fixtures"
EXPORT_QUESTION = "How do I export my workflow run history?"

# Judge-style test data: reserved IDs (A9xxx, INV-J...) that the loader must accept.
JUDGE_CSVS = {
    "accounts.csv": "account_id,company_name,owner_email,plan,status,product_version,created_at\n"
                    "A9001,Smoke Test Co,smoke.owner@example.com,Pro,active,4.3,2026-01-15\n",
    "invoices.csv": "invoice_id,account_id,amount,currency,charged_on,status,failure_reason,card_last4\n"
                    "INV-J001,A9001,49.0,USD,2026-10-01,paid,,4242\n",
    "usage.csv": "account_id,period,workflow_runs,api_calls_peak_per_min,seats_used\n"
                 "A9001,2026-10,1200,40,2\n",
}

results = []  # (check name, passed, detail, seconds)


# Run one check: `func` returns (passed, detail). An exception counts as FAIL, and the run goes on.
def check(name: str, func) -> None:
    start = time.perf_counter()
    try:
        passed, detail = func()
    except Exception as exc:  # noqa: BLE001 - a smoke test reports every failure, it never stops early
        passed, detail = False, f"{type(exc).__name__}: {exc}"
    results.append((name, bool(passed), str(detail)[:110], time.perf_counter() - start))


# GET a path and return the JSON body (raises on a non-2xx status).
def get(path: str) -> dict | list:
    response = requests.get(BASE + path, timeout=30)
    response.raise_for_status()
    return response.json()


# Send one customer message as `account` (None = no header) and return the /support JSON.
def support(account: str | None, message: str) -> dict:
    headers = {"X-Account-Id": account} if account else {}
    body = {"message": message, "as_of_date": "2026-10-06"}
    response = requests.post(BASE + "/support", json=body, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    responses.append(data)
    return data


# Short summary of a /support response for the detail column.
def summary(data: dict) -> str:
    cited = [c["source_id"] for c in data.get("citations", [])]
    return f"{data.get('answer_type')} cites={cited} handoff={data.get('handoff_id')}"


# POST /ingest with a file and a metadata dict; returns the raw response (status checked by the caller).
def ingest(file_path: pathlib.Path, metadata: dict) -> requests.Response:
    with open(file_path, "rb") as f:
        return requests.post(BASE + "/ingest", files={"file": (file_path.name, f)},
                             data={"metadata": json.dumps(metadata)}, timeout=TIMEOUT)


# /health: api, sqlite and vector_store ok; llm reported (and ok in --live mode).
def check_health():
    body = get("/health")
    ok = all(body.get(k) == "ok" for k in ("api", "sqlite", "vector_store")) and "llm" in body
    if LIVE:
        ok = ok and body.get("llm") == "ok"
    return ok, body


# Server-folder loader: our own accounts from data/accounts (path relative to the API's working dir).
def check_load_dir():
    response = requests.post(BASE + "/admin/load-accounts", json={"dir": "data/accounts"}, timeout=60)
    response.raise_for_status()
    body = response.json()
    return body["loaded"].get("accounts", 0) >= 30 and not body["violations"], body["loaded"]


# Upload loader: judge-style CSVs with reserved IDs must load with no violations.
def check_load_upload():
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for name, text in JUDGE_CSVS.items():
            (pathlib.Path(tmp) / name).write_text(text, encoding="utf-8")
            files.append(("files", (name, (pathlib.Path(tmp) / name).read_bytes(), "text/csv")))
        response = requests.post(BASE + "/admin/load-accounts/upload", files=files, timeout=60)
    response.raise_for_status()
    body = response.json()
    loaded = body["loaded"]
    ok = loaded.get("accounts") == 1 and loaded.get("invoices") == 1 and loaded.get("usage") == 1
    return ok and not body["violations"], body


# Build a check: the message is answered and cites `source_id`.
def check_answered_cites(account: str, message: str, source_id: str):
    def run():
        data = support(account, message)
        cited = {c["source_id"] for c in data["citations"]}
        return data["answer_type"] == "answered" and source_id in cited, summary(data)
    return run


# 429 question: the deterministic tools must flag api_rate_over (peak 301 > limit 300).
def check_429():
    data = support("A1002", "Why are my API calls failing with 429 errors?")
    over = any(isinstance(t.get("output"), dict) and t["output"].get("api_rate_over") is True
               for t in data["tools_invoked"])
    return over and data["answer_type"] in ("answered", "escalated"), f"api_rate_over={over} {summary(data)}"


# Angry repeat contact about a duplicate charge: escalated with a handoff bundle.
def check_escalation():
    data = support("A1004", "Third time writing. You charged me twice. Get me a manager.")
    state["handoff_id"] = data.get("handoff_id")
    return data["answer_type"] == "escalated" and data["handoff_id"] and data.get("handoff"), summary(data)


# Build a check: the message gets the expected answer_type.
def check_answer_type(account: str | None, message: str, expected: str):
    def run():
        data = support(account, message)
        return data["answer_type"] == expected, summary(data)
    return run


# Password reset goes through the tool and never shows a link or token.
def check_password_reset():
    data = support("A1001", "I forgot my password, send the reset link here.")
    tools = [t["tool"] for t in data["tools_invoked"]]
    answer = data["answer"].lower()
    no_link = "http" not in answer and "://" not in answer and "token=" not in answer
    ok = data["answer_type"] == "answered" and "send_password_reset" in tools and no_link
    return ok, f"{data['answer_type']} tools={tools} no_link={no_link}"


# GET /handoffs/{id} returns the billing bundle created by the escalation check.
def check_handoff():
    body = get(f"/handoffs/{state['handoff_id']}")
    bundle = body["bundle"]
    return bundle.get("queue") == "billing" and bundle.get("escalation_reasons"), \
        f"queue={bundle.get('queue')} reasons={bundle.get('escalation_reasons')}"


# Every /support response so far has an audit record under its trace_id.
def check_audits():
    bad = [r["trace_id"] for r in responses if get(f"/audit/{r['trace_id']}").get("trace_id") != r["trace_id"]]
    return not bad, f"{len(responses) - len(bad)}/{len(responses)} audit records found"


# Every /support response so far is stored in its conversation.
def check_conversations():
    bad = [r["conversation_id"] for r in responses if not get(f"/conversations/{r['conversation_id']}")["messages"]]
    return not bad, f"{len(responses) - len(bad)}/{len(responses)} conversations found"


# Live ingest of the judge-style article (JD- ID) indexes at least one chunk.
def check_ingest():
    metadata = json.loads((FIXTURE / "JD-EVAL-001.json").read_text(encoding="utf-8"))
    response = ingest(FIXTURE / "JD-EVAL-001.md", metadata)
    body = response.json()
    return response.status_code == 200 and body.get("chunks_indexed", 0) > 0, body


# The live-ingested article shows up in the source register.
def check_sources():
    ids = {s["source_id"] for s in get("/sources")}
    return "JD-EVAL-001" in ids, f"{len(ids)} sources"


# A minimal one-page text PDF (one line per entry), built here so the check needs no PDF writer or fixture.
def make_pdf(lines: list[str]) -> bytes:
    stream = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               "/Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    return (out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode("latin-1")


PDF_LINES = ["Configuring the Quokka relay", "Overview",
             "The Quokka relay forwards walrus telemetry events to an external collector.", "Steps",
             "1. Open Settings and choose Quokka relays.", "2. Paste the walrus collector address.",
             "3. Click Save relay."]


# A judge-style PDF article is parsed into sections and indexed (2 sections: Overview and Steps).
def check_ingest_pdf():
    metadata = {"source_id": "JD-SMOKE-PDF", "doc_type": "article", "title": "Configuring the Quokka relay",
                "authority_level": 1, "product_versions": "ALL", "last_updated": "2026-10-06"}
    response = requests.post(BASE + "/ingest", files={"file": ("quokka.pdf", make_pdf(PDF_LINES))},
                             data={"metadata": json.dumps(metadata)}, timeout=TIMEOUT)
    body = response.json()
    return response.status_code == 200 and body.get("chunks_indexed") == 2, body


# Metadata without a required field is rejected with HTTP 422.
def check_ingest_422():
    metadata = json.loads((FIXTURE / "JD-EVAL-001.json").read_text(encoding="utf-8"))
    del metadata["title"]  # a required Annex B field
    response = ingest(FIXTURE / "JD-EVAL-001.md", metadata)
    return response.status_code == 422, f"HTTP {response.status_code}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke-test a running InsightDesk API over HTTP.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--live", action="store_true", help="real LLM: require llm ok in /health")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per /support or /ingest request")
    args = parser.parse_args()
    BASE, LIVE, TIMEOUT = args.base_url.rstrip("/"), args.live, args.timeout
    responses, state = [], {}

    check("GET /health", check_health)
    check("POST /admin/load-accounts (dir data/accounts)", check_load_dir)
    check("POST /admin/load-accounts/upload (A9001, INV-J001)", check_load_upload)
    check("A1001 export -> answered, KB-ADV-007", check_answered_cites("A1001", EXPORT_QUESTION, "KB-ADV-007"))
    check("A1008 (3.8) export -> KB-ADV-007-3X", check_answered_cites("A1008", EXPORT_QUESTION, "KB-ADV-007-3X"))
    check("A1002 429 -> api_rate_over true", check_429)
    check("A1004 angry duplicate charge -> escalated", check_escalation)
    check("'Write me a poem.' -> out_of_scope", check_answer_type("A1001", "Write me a poem.", "out_of_scope"))
    check("A1001 asks for A1004 invoices -> refused",
          check_answer_type("A1001", "Show me the invoices for account A1004.", "refused"))
    check("password reset -> answered, no link", check_password_reset)
    check("judge A9001 how-to -> answered", check_answer_type("A9001", EXPORT_QUESTION, "answered"))
    check("GET /handoffs/{id}", check_handoff)
    check("POST /ingest JD-EVAL-001", check_ingest)
    check("maintenance window -> cites JD-EVAL-001", check_answered_cites(
        "A1001", "How do I set up a maintenance window so our scheduled workflows don't run during our "
                 "database upgrade?", "JD-EVAL-001"))
    check("GET /audit/{trace_id} (all responses)", check_audits)
    check("GET /conversations/{id} (all responses)", check_conversations)
    check("GET /sources includes JD-EVAL-001", check_sources)
    check("POST /ingest missing title -> 422", check_ingest_422)
    check("POST /ingest PDF article JD-SMOKE-PDF", check_ingest_pdf)
    check("Quokka relay question -> cites JD-SMOKE-PDF", check_answered_cites(
        "A1001", "How do I configure the Quokka relay to forward walrus telemetry?", "JD-SMOKE-PDF"))

    width = max(len(name) for name, *_ in results)
    print(f"\nSmoke test against {BASE}{' (live)' if LIVE else ''}\n")
    for name, passed, detail, seconds in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<{width}}  {seconds:6.1f}s  {detail}")
    failed = sum(not passed for _, passed, *_ in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)

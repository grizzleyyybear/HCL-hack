"""FastAPI app: every endpoint of the guide's API contract (section 6).

Each route is a thin wrapper around the module that owns the logic. Area: API and orchestration.
"""
import contextlib
import datetime
import json
import logging
import pathlib
import tempfile

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from app import auth, db, llm, retrieval, tools
from app.graph import pipeline
from app.schemas import SupportRequest, SupportResponse

log = logging.getLogger("insightdesk")


# Run a startup helper if its owner has implemented it yet; never crash the app over it.
def _try(step_name: str, func) -> None:
    try:
        func()
    except Exception as exc:  # noqa: BLE001 - startup must keep going
        log.warning("startup step %s skipped: %s", step_name, exc)


# On startup: create tables, install log redaction, seed policies and load the KB once.
@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    from app import safety
    _try("setup_logging", safety.setup_logging)
    from scripts import ingest_kb, seed_policy_registry
    _try("seed_policy_registry", seed_policy_registry.seed)
    _try("ingest_kb", lambda: log.info("knowledge base: %s", ingest_kb.ingest_all()))
    # Load the embedding model now so the first customer request does not pay the ~15 s model load.
    _try("warm_up_embeddings", lambda: retrieval.search("warm up", None, 1))
    yield


app = FastAPI(title="InsightDesk", version="1.0", lifespan=lifespan)


# Turn "not built yet" into a clear 501 instead of a crash.
def _not_ready(exc: NotImplementedError):
    raise HTTPException(status_code=501, detail=f"not implemented yet: {exc}")


# The account inside an "Authorization: Bearer <token>" header; 401 when the token is missing, bad or expired.
def _session_account(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    account_id = auth.verify_token(token.strip()) if scheme.lower() == "bearer" else None
    if not account_id:
        raise HTTPException(status_code=401, detail="Sign in again: the session token is missing, invalid or expired.")
    return account_id


# POST /support: handle one customer message. The account comes only from the X-Account-Id header.
# The web app also sends its session token; when one is sent it must belong to that same account.
@app.post("/support", response_model=SupportResponse, response_model_exclude_none=False)
def support(request: SupportRequest, x_account_id: str | None = Header(default=None, alias="X-Account-Id"),
            authorization: str | None = Header(default=None)):
    if authorization is not None and _session_account(authorization) != (x_account_id or "").strip().upper():
        raise HTTPException(status_code=401, detail="The session token does not belong to the X-Account-Id account.")
    try:
        return pipeline.run(request, x_account_id)
    except NotImplementedError as exc:
        _not_ready(exc)


# POST /ingest: add a Markdown article or JSON ticket plus Annex B metadata while running.
@app.post("/ingest")
async def ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    try:
        return retrieval.ingest_upload(await file.read(), file.filename or "upload", metadata)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json(include_input=False)))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
    except ValueError as exc:  # anything else wrong with the upload (e.g. unparseable content)
        raise HTTPException(status_code=422, detail=str(exc))
    except NotImplementedError as exc:
        _not_ready(exc)


class LoginRequest(BaseModel):
    login: str  # owner email or account ID
    password: str


# POST /auth/login: sign in to the CloudFlow web app; returns a signed session token and the account summary.
@app.post("/auth/login")
def auth_login(body: LoginRequest):
    try:
        session = auth.login(body.login, body.password)
    except auth.NotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if session is None:
        log.info("sign-in failed")
        raise HTTPException(status_code=401, detail="Email/account ID or password is incorrect.")
    log.info("sign-in ok for %s", session["account"]["account_id"])
    return session


# GET /me: the signed-in account's dashboard data, read by the same deterministic tools the pipeline uses.
@app.get("/me")
def me(authorization: str | None = Header(default=None)):
    account_id = _session_account(authorization)
    account = auth.find_account(account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Sign in again: this account no longer exists.")
    period = datetime.date.today().isoformat()[:7]
    usage = tools.get_usage(account_id, period=period)
    return {"account": account, "period": period, "usage": usage,
            "limits": tools.get_plan_limits(account["plan"], None if "error" in usage else usage),
            "invoices": tools.get_invoices(account_id).get("invoices", []),
            "platform_status": tools.check_platform_status().get("components", [])}


# GET /health: status of the API, vector store, SQLite and LLM, each "ok" or "error".
@app.get("/health")
def health():
    status = {"api": "ok"}
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        status["sqlite"] = "ok"
    except Exception:  # noqa: BLE001
        status["sqlite"] = "error"
    try:
        status["vector_store"] = "ok" if retrieval.health() else "error"
    except Exception:  # noqa: BLE001
        status["vector_store"] = "error"
    status["llm"] = llm.health()
    return status


# GET /conversations/{id}: redacted messages plus the route each response took.
@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with db.connect() as conn:
        rows = conn.execute("SELECT role, text_redacted, answer_type, trace_id, created_at FROM messages "
                            "WHERE conversation_id = ? ORDER BY id", (conversation_id,)).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="conversation not found")
        messages = []
        for row in rows:
            msg = dict(row)
            audit = conn.execute("SELECT record_json FROM audit_log WHERE trace_id = ?", (row["trace_id"],)).fetchone()
            msg["route"] = json.loads(audit["record_json"]).get("route", []) if audit else []
            messages.append(msg)
    return {"conversation_id": conversation_id, "messages": messages}


# GET /handoffs/{id}: the full (redacted) handoff bundle created at escalation.
@app.get("/handoffs/{handoff_id}")
def get_handoff(handoff_id: str):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="handoff not found")
    record = dict(row)
    record["bundle"] = json.loads(record.pop("bundle_json"))
    return record


# GET /audit/{trace_id}: the full audit record for one response.
@app.get("/audit/{trace_id}")
def get_audit(trace_id: str):
    with db.connect() as conn:
        row = conn.execute("SELECT record_json FROM audit_log WHERE trace_id = ?", (trace_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="audit record not found")
    return json.loads(row["record_json"])


# GET /sources: the source register, including documents ingested live.
@app.get("/sources")
def get_sources():
    try:
        return retrieval.list_sources()
    except NotImplementedError as exc:
        _not_ready(exc)


class LoadAccountsRequest(BaseModel):
    dir: str


# Load CSVs from a folder on the server (same code as scripts/load_accounts.py --dir).
def _load_dir(path: str) -> dict:
    from scripts import load_accounts
    try:
        return load_accounts.load_dir(path)
    except NotImplementedError as exc:
        _not_ready(exc)


# POST /admin/load-accounts: JSON {"dir": "test_accounts/"} loads Annex C CSVs from a server folder.
@app.post("/admin/load-accounts")
def load_accounts_from_dir(body: LoadAccountsRequest):
    if not pathlib.Path(body.dir).is_dir():
        raise HTTPException(status_code=400, detail=f"folder not found: {body.dir}")
    return _load_dir(body.dir)


# POST /admin/load-accounts/upload: upload the CSV files directly (accounts.csv, usage.csv, ...).
@app.post("/admin/load-accounts/upload")
async def load_accounts_from_upload(files: list[UploadFile] = File(...)):
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            name = pathlib.Path(f.filename or "").name
            if name.endswith(".csv"):
                (pathlib.Path(tmp) / name).write_bytes(await f.read())
        return _load_dir(tmp)

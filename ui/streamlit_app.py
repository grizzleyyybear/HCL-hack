"""InsightDesk chat UI (Streamlit). Talks to the FastAPI backend only over HTTP.

Run: streamlit run ui/streamlit_app.py   (API_URL env var points at the API, default http://localhost:8000)
"""
import json
import os

import requests
import streamlit as st

# One colour per answer_type so the outcome is visible at a glance.
BADGE_COLORS = {"answered": "green", "clarification_needed": "blue", "escalated": "orange",
                "not_found": "gray", "refused": "red", "out_of_scope": "violet"}

METADATA_TEMPLATE = json.dumps({
    "source_id": "KB-NEW-001", "doc_type": "article", "title": "New article title", "authority_level": 1,
    "product_versions": "4.0+", "last_updated": "2026-10-06", "effective_from": "", "deprecated_on": "",
    "supersedes": "", "tags": "", "provenance": "manual upload", "synthetic": "Y"}, indent=2)


# Call the API and return (json, None) on success or (None, readable error text) on any failure.
def api(method: str, base: str, path: str, timeout: int = 15, **kwargs):
    try:
        resp = requests.request(method, base.rstrip("/") + path, timeout=timeout, **kwargs)
    except requests.ConnectionError:
        return None, f"Cannot reach the API at {base}. Is it running?"
    except requests.Timeout:
        return None, f"The API did not answer within {timeout} s."
    if resp.ok:
        return resp.json(), None
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        detail = resp.text
    if resp.status_code == 501:
        return None, f"Not built yet (501): {detail}"
    if resp.status_code == 422 and isinstance(detail, list):  # Pydantic errors: "field: message" per line
        detail = "\n".join(f"- {'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg')}" for e in detail)
        return None, f"Invalid input (422):\n{detail}"
    return None, f"HTTP {resp.status_code}: {detail}"


# Cached GET (10 s) so reruns do not refetch health, handoffs and audits every time; errors are not cached.
@st.cache_data(ttl=10, show_spinner=False)
def cached_get(base: str, path: str):
    data, err = api("GET", base, path)
    if err:
        raise RuntimeError(err)
    return data


# Show a GET result as JSON, or the error text if the call failed.
def show_get(base: str, path: str) -> None:
    try:
        st.json(cached_get(base, path))
    except RuntimeError as exc:
        st.error(str(exc))


# Draw one assistant reply: badge, answer, citations, tools, conflicts, critic, handoff and audit.
def render_reply(base: str, r: dict) -> None:
    answer_type = r.get("answer_type", "?")
    st.markdown(f":{BADGE_COLORS.get(answer_type, 'gray')}-background[{answer_type}]")
    st.markdown(r.get("answer", ""))
    intent = r.get("intent") or {}
    if intent:
        st.caption(f"Intent: {intent.get('type')} · urgency {intent.get('urgency')} · "
                   f"sentiment {intent.get('sentiment')} · confidence {intent.get('confidence')}")
    if r.get("citations"):
        st.markdown("**Citations**\n" + "\n".join(
            f"- `{c['source_id']}` · {c['section']} · {c['product_versions']} · updated {c['last_updated']}"
            for c in r["citations"]))
    if r.get("tools_invoked"):
        with st.expander(f"Tools invoked ({len(r['tools_invoked'])})"):
            for t in r["tools_invoked"]:
                st.markdown(f"**{t.get('tool')}** · {t.get('status', 'ok')} · {t.get('ms', '?')} ms")
                st.json(t.get("output", {}))
    for c in r.get("conflicts_detected") or []:
        st.warning(f"Conflict: `{c['winner']}` wins over `{c['loser']}` (rule: {c['rule']})")
    critic = r.get("critic")
    if critic:
        st.caption(f"Critic: groundedness {critic.get('groundedness')} · coverage {critic.get('coverage')} · "
                   f"PII risk {critic.get('pii_risk')} · policy risk {critic.get('policy_risk')} · "
                   f"decision {critic.get('decision')} · revisions {critic.get('revisions', 0)}")
    if r.get("handoff_id"):
        with st.expander(f"Handoff {r['handoff_id']}"):
            show_get(base, f"/handoffs/{r['handoff_id']}")
    if r.get("trace_id"):
        with st.expander(f"Audit record · trace {r['trace_id']}"):
            show_get(base, f"/audit/{r['trace_id']}")


# Draw one stored chat message (user text, assistant reply, or an error from the API call).
def render_message(base: str, msg: dict) -> None:
    with st.chat_message(msg["role"]):
        if "error" in msg:
            st.error(msg["error"])
        elif msg["role"] == "assistant":
            render_reply(base, msg["reply"])
        else:
            st.markdown(msg["text"])


# Chat page: history, input box, POST /support with the X-Account-Id header, keep conversation_id.
def chat_page(base: str, account_id: str, product_version: str, as_of_date) -> None:
    st.title("InsightDesk")
    st.caption("CloudFlow support assistant. Every answer is grounded in cited sources or account tools.")
    for msg in st.session_state.messages:
        render_message(base, msg)
    prompt = st.chat_input("Ask CloudFlow support...")
    if not prompt:
        return
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    body = {"message": prompt, "conversation_id": st.session_state.conversation_id, "channel": "web",
            "product_version": product_version.strip() or None,
            "as_of_date": as_of_date.isoformat() if as_of_date else None}
    headers = {"X-Account-Id": account_id.strip()} if account_id.strip() else {}
    with st.spinner("Working on it..."):
        data, err = api("POST", base, "/support", timeout=300, json=body, headers=headers)
    if err:
        st.session_state.messages.append({"role": "assistant", "error": err})
    else:
        st.session_state.conversation_id = data.get("conversation_id")
        st.session_state.messages.append({"role": "assistant", "reply": data})
    st.rerun()


# Admin page: live-ingest a document, upload account CSVs, and browse the source register.
def admin_page(base: str) -> None:
    st.title("Admin")

    st.subheader("Ingest an article or ticket (POST /ingest)")
    with st.form("ingest", clear_on_submit=False):
        doc = st.file_uploader("Markdown article (.md) or JSON ticket (.json)", type=["md", "json"])
        metadata = st.text_area("Metadata JSON (Source Register fields)", METADATA_TEMPLATE, height=280)
        submitted = st.form_submit_button("Ingest")
        if submitted and not doc:
            st.warning("Choose a file first.")
        elif submitted:
            data, err = api("POST", base, "/ingest", timeout=120,
                            files={"file": (doc.name, doc.getvalue())}, data={"metadata": metadata})
            if err:
                st.error(err)
            else:
                st.success(f"Ingested {data.get('source_id')}: {data.get('chunks_indexed')} chunks, "
                           f"{data.get('status')}")
                cached_get.clear()  # refresh the source list below

    st.subheader("Load account CSVs (POST /admin/load-accounts/upload)")
    with st.form("accounts"):
        csvs = st.file_uploader("accounts.csv, plan_limits.csv, usage.csv, invoices.csv, platform_status.csv, "
                                "policy_registry.csv (any subset)", type=["csv"], accept_multiple_files=True)
        submitted = st.form_submit_button("Load")
        if submitted and not csvs:
            st.warning("Choose at least one CSV first.")
        elif submitted:
            data, err = api("POST", base, "/admin/load-accounts/upload", timeout=120,
                            files=[("files", (f.name, f.getvalue(), "text/csv")) for f in csvs])
            if err:
                st.error(err)
            else:
                st.json(data)

    st.subheader("Source register (GET /sources)")
    try:
        st.dataframe(cached_get(base, "/sources"), hide_index=True)
    except RuntimeError as exc:
        st.error(str(exc))


# Sidebar settings, health line and page switch; then draw the chosen page.
def main() -> None:
    st.set_page_config(page_title="InsightDesk", layout="wide")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("conversation_id", None)
    with st.sidebar:
        page = st.radio("Page", ["Chat", "Admin"], horizontal=True)
        base = st.text_input("API base URL", os.getenv("API_URL", "http://localhost:8000"))
        account_id = st.text_input("X-Account-Id", "A1001", help="Blank = not signed in (general questions only)")
        product_version = st.text_input("product_version (optional)", "")
        as_of_date = st.date_input("as_of_date (optional, blank = today)", value=None)
        if st.button("New conversation"):
            st.session_state.messages = []
            st.session_state.conversation_id = None
        st.caption(f"Conversation: {st.session_state.conversation_id or 'new'}")
        try:
            health = cached_get(base, "/health")
            st.caption("Health: " + " · ".join(f"{k} {v}" for k, v in health.items()))
        except RuntimeError as exc:
            st.caption(f"Health: {exc}")
    if page == "Chat":
        chat_page(base, account_id, product_version, as_of_date)
    else:
        admin_page(base)


main()

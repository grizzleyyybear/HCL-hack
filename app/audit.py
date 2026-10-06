"""Audit trail: one record per /support call, keyed by an 8-character hex trace_id.

Area: API and orchestration.
finishes the record fields in W4. Records are summaries, never chain-of-thought.
"""
import contextlib
import datetime
import json
import secrets
import time

from app import db


# Make a new random 8-hex-character trace id, e.g. "b81e0c44".
def new_trace_id() -> str:
    return secrets.token_hex(4)


class Trace:
    """Collects what happened during one request: route, timings, tools, LLM usage."""

    # Start a trace for one request and remember when it began.
    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or new_trace_id()
        self.started = time.perf_counter()
        self.route: list[dict] = []
        self.tools: list[dict] = []
        # The configured model, even when this request never calls it (a refusal stops before the LLM).
        from app import llm  # local import: llm does not import audit, this keeps module loading simple
        model = "mock" if llm.settings.MOCK_LLM else llm._model_name()
        self.llm = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "model": model}
        self.extra: dict = {}

    # Time a pipeline step: `with trace.step("classify"): ...` records name and milliseconds.
    @contextlib.contextmanager
    def step(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.route.append({"step": name, "ms": round((time.perf_counter() - t0) * 1000)})

    # Record one tool call (already redacted by run_tool).
    def add_tool(self, call: dict) -> None:
        self.tools.append(call)

    # Add the token counts from one LLM call.
    def add_llm(self, usage: dict) -> None:
        self.llm["calls"] += usage.get("calls", 0)
        self.llm["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.llm["completion_tokens"] += usage.get("completion_tokens", 0)
        if usage.get("model"):
            self.llm["model"] = usage["model"]

    # Build the final audit record dict from everything collected plus the given fields.
    def to_record(self, **fields) -> dict:
        return {
            "trace_id": self.trace_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "route": [r["step"] for r in self.route],
            "step_ms": self.route,
            "tools_invoked": [{k: t.get(k) for k in ("tool", "input", "output", "status", "ms")} for t in self.tools],
            "model": self.llm["model"],
            "llm_calls": self.llm["calls"],
            "tokens": {"prompt": self.llm["prompt_tokens"], "completion": self.llm["completion_tokens"]},
            "latency_ms": round((time.perf_counter() - self.started) * 1000),
            **self.extra,
            **fields,
        }

    # Save a (redacted) record into the audit_log table.
    def save(self, record: dict) -> None:
        with db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO audit_log VALUES (?, ?, ?)",
                         (self.trace_id, record["timestamp"], json.dumps(record, default=str)))

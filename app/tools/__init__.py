"""Deterministic tools over SQLite (R7). Owner: A7 tools-policy.

The account_id passed to any tool always comes from the X-Account-Id header (code), never the LLM.
"""
import time

from app import safety
from app.schemas import ToolCall
from app.tools.account_tools import get_plan_limits, get_usage, lookup_account
from app.tools.billing_tools import check_refund_eligibility, get_invoices
from app.tools.handoff_tools import create_handoff
from app.tools.security_tools import send_password_reset
from app.tools.status_tools import check_platform_status

# Every tool by name, so the pipeline (and the LLM's tools_needed suggestions) can refer to them as strings.
TOOLS = {f.__name__: f for f in (lookup_account, get_usage, get_plan_limits, get_invoices,
                                 check_refund_eligibility, check_platform_status,
                                 send_password_reset, create_handoff)}

# Safety-net mapping from intent type to the tools code always runs (CLAUDE.md "Rules for all tools").
TOOLS_FOR_INTENT: dict[str, list[str]] = {
    "billing": ["get_invoices", "check_refund_eligibility"],
    "account": ["lookup_account", "get_usage", "get_plan_limits"],
    "troubleshooting": ["check_platform_status"],
    "security": ["send_password_reset"],
    "complaint": ["get_invoices"],
    "how_to": ["lookup_account"],
}


# Redact with app.safety; returns obj unchanged while safety.py is still a stub.
def _redact(obj):
    try:
        return safety.redact_obj(obj)
    except NotImplementedError:  # ponytail: remove this fallback once A8 lands app/safety.py
        return obj


# Run one tool by name: time it, turn any exception into {"error": ...}, redact the output.
def run_tool(name: str, **kwargs) -> ToolCall:
    start = time.perf_counter()
    try:
        output = TOOLS[name](**kwargs)
    except Exception as exc:  # a tool must never crash the pipeline; escalation treats errors as tool_failure
        output = {"error": f"{type(exc).__name__}: {exc}"}
    status = "error" if isinstance(output, dict) and "error" in output else "ok"
    ms = round((time.perf_counter() - start) * 1000)
    return ToolCall(tool=name, input=_redact(kwargs), output=_redact(output), status=status, ms=ms)

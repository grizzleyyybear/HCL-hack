"""Builds the LangGraph StateGraph and runs one request through it. Area: API and orchestration.

pre_checks -> classify -> tools -> retrieve -> precedence -> compose -> critic -> decide -> respond | escalate
Conditional edges (all decided in code):
- any step that already set an answer_type (refused, out_of_scope, clarification_needed, not_found) -> respond
- the KB does not cover a question a human must settle (kb_gap_needs_outcome) -> decide (it escalates)
- decide: revise -> compose (at most once), escalate -> escalate -> respond, answer -> respond,
  not_found (critic coverage "none" and no human outcome needed) -> respond
"""
import datetime
import functools
from typing import Any

from langgraph.graph import END, START, StateGraph

from app import audit, db
from app.graph import nodes
from app.graph.state import State
from app.schemas import SupportRequest, SupportResponse


class PipelineState(State, total=False):
    """The shared State plus the few keys only the pipeline needs internally."""
    message: str                 # raw message; pre_checks blanks it after redacting
    pii_found: bool
    relevant_chunks: list[dict]  # retrieved chunks scoring >= min_relevance
    kb_gap_needs_outcome: bool
    query: str                   # retrieval query: the message, or previous question + follow-up
    history: str                 # previous turn for the classifier/composer prompts ("" if none)
    follow_up: bool
    handoff_requested: bool      # "yes please" after our not_found handoff offer
    response: Any                # the final SupportResponse


# Router factory: go to respond if a reply is already decided, to decide on a KB gap, else to next_node.
def _route(next_node: str):
    def router(state) -> str:
        if state.get("answer_type"):
            return "respond"
        if state.get("kb_gap_needs_outcome"):
            return "decide"
        return next_node
    return router


# After decide: revise -> compose again, escalate -> escalate, answer (or not_found) -> respond.
def _after_decide(state) -> str:
    return {"revise": "compose", "escalate": "escalate"}.get(state["decision"], "respond")


# Build and compile the graph once (cached for the life of the process).
@functools.cache
def graph():
    g = StateGraph(PipelineState)
    for name, func in [("pre_checks", nodes.pre_checks), ("classify", nodes.classify), ("tools", nodes.tools),
                       ("retrieve", nodes.retrieve), ("precedence", nodes.precedence_step),
                       ("compose", nodes.compose), ("critic", nodes.critic), ("decide", nodes.decide),
                       ("escalate", nodes.escalate), ("respond", nodes.respond)]:
        g.add_node(name, func)
    g.add_edge(START, "pre_checks")
    g.add_conditional_edges("pre_checks", _route("classify"), ["respond", "classify"])
    g.add_conditional_edges("classify", _route("tools"), ["respond", "tools"])
    g.add_edge("tools", "retrieve")
    g.add_conditional_edges("retrieve", _route("precedence"), ["respond", "decide", "precedence"])
    g.add_conditional_edges("precedence", _route("compose"), ["respond", "decide", "compose"])
    g.add_edge("compose", "critic")
    g.add_edge("critic", "decide")
    g.add_conditional_edges("decide", _after_decide, ["compose", "respond", "escalate"])
    g.add_edge("escalate", "respond")
    g.add_edge("respond", END)
    return g.compile()


# Reuse the given conversation only if it exists and belongs to this account; otherwise start a new one.
def _conversation_id(requested: str | None, account_id: str | None) -> str:
    if requested:
        with db.connect() as conn:
            row = conn.execute("SELECT account_id FROM conversations WHERE conversation_id = ?",
                               (requested,)).fetchone()
        if row is not None and account_id and row["account_id"] == account_id:  # signed-out callers never share one
            return requested
    return db.next_id("C")


# Run one /support request end to end and return the full response (all 6.1 fields).
def run(request: SupportRequest, account_id: str | None) -> SupportResponse:
    account_id = (account_id or "").strip().upper() or None  # the account comes ONLY from the header
    state = {"account_id": account_id, "message": request.message,
             "as_of_date": request.as_of_date or datetime.date.today(),
             "conversation_id": _conversation_id(request.conversation_id, account_id),
             "product_version": request.product_version, "revisions": 0, "trace": audit.Trace()}
    return graph().invoke(state)["response"]

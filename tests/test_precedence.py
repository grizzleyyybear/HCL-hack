"""Tests for app/precedence.py (Annex A.2) with hand-built chunks, in MOCK_LLM mode."""
import datetime

import pytest

from app import llm, precedence
from app.schemas import Conflict, Disagreements, DisagreementResult

TODAY = datetime.date(2026, 10, 6)


# Every test runs without Ollama and counts how many times the disagreement LLM call happens.
@pytest.fixture(autouse=True)
def calls(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    counter = {"n": 0}
    real_call = llm.call_json

    def counting_call(*args, **kwargs):
        counter["n"] += 1
        return real_call(*args, **kwargs)

    monkeypatch.setattr(llm, "call_json", counting_call)
    return counter


# Build one chunk in the retrieval chunk format.
def chunk(source_id, text, level=1, doc_type="article", versions=(0, 9999), score=0.5, tags="",
          last_updated="2026-01-01", effective_from="", deprecated_on="", supersedes="", title=None, section="Steps"):
    return {"chunk_id": f"{source_id}::{section}::0", "text": text, "score": score,
            "meta": {"source_id": source_id, "doc_type": doc_type, "title": title or source_id, "section": section,
                     "authority_level": level, "product_versions": "", "version_min": versions[0],
                     "version_max": versions[1], "last_updated": last_updated, "effective_from": effective_from,
                     "deprecated_on": deprecated_on, "supersedes": supersedes, "tags": tags, "synthetic": "Y"}}


# Source IDs of the applicable chunks, in output order.
def ids(result):
    return [c["meta"]["source_id"] for c in result["applicable"]]


KB_TRB_004 = chunk("KB-TRB-004", "Salesforce step fails with CF-503\n## Steps in CloudFlow 3.x\nOpen Settings, "
                   "Connections, Reconnect the Salesforce connector. Never disable SSL verification.",
                   tags="salesforce;CF-503", section="Steps in CloudFlow 3.x")
TKT_0142 = chunk("TKT-2025-0142", "Customer question: Salesforce step fails with CF-503.\nResolution: turn on "
                 "Allow insecure SSL, which will disable SSL verification for the connector.",
                 level=4, doc_type="ticket", versions=(300, 399), tags="salesforce;CF-503", section="Ticket")
KB_API_005 = chunk("KB-API-005", "API rate limits and 429 errors\n## Details\nThe Pro plan allows 300 calls per "
                   "minute. Going over returns HTTP 429 with error CF-429. Honour Retry-After and use exponential "
                   "backoff. Do not retry immediately in a tight loop.", tags="api;rate-limit;CF-429", score=0.9)
TKT_0201 = chunk("TKT-2025-0201", "Customer question: API calls failing with 429 (CF-429).\nResolution: the Pro "
                 "limit is 120 calls per minute, so wait a bit and retry.", level=4, doc_type="ticket",
                 tags="api;CF-429", section="Ticket")
COM_0003 = chunk("COM-0003", "Just retry 429s\n## Accepted answer\nJust retry 429s immediately in a loop until "
                 "it works.", level=5, doc_type="community", tags="api;rate-limit", section="Accepted answer")
KB_TRB_002 = chunk("KB-TRB-002", "Fixing CF-401 authentication errors\n## Steps\nCreate a new API token and check "
                   "the Authorization: Bearer header format.", tags="api;token;CF-401")
TKT_0047 = chunk("TKT-2025-0047", "Customer question: CF-401 after my token expired.\nResolution: created a new "
                 "API token and updated the Authorization Bearer header.", level=4, doc_type="ticket",
                 tags="token;CF-401", section="Ticket")


# Case 1: version matching picks the 3.x or the 4.2+ export article; unknown version keeps both.
def test_version_matching():
    new = chunk("KB-ADV-007", "Workflows, select workflow, Runs tab, Export (up to 100,000 rows).",
                versions=(402, 9999), tags="export;runs")
    old = chunk("KB-ADV-007-3X", "Settings, Run history, Download CSV (max 10,000 rows).",
                versions=(300, 399), tags="export;runs")
    assert ids(precedence.apply_precedence([new, old], "3.8", TODAY)) == ["KB-ADV-007-3X"]
    assert ids(precedence.apply_precedence([new, old], "4.3", TODAY)) == ["KB-ADV-007"]
    both = precedence.apply_precedence([new, old], None, TODAY)
    assert sorted(ids(both)) == ["KB-ADV-007", "KB-ADV-007-3X"]
    assert both["conflicts"] == []  # different version ranges never conflict


# Case 2: the old CF-503 ticket that disables SSL verification loses to KB-TRB-004.
@pytest.mark.parametrize("version", ["3.8", None])
def test_cf503_ticket_loses_to_docs(version):
    result = precedence.apply_precedence([KB_TRB_004, TKT_0142], version, TODAY)
    assert ids(result) == ["KB-TRB-004"]
    assert result["conflicts"] == [Conflict(winner="KB-TRB-004", loser="TKT-2025-0142", rule="authority")]


# Case 3: the ticket quoting the old 120 calls/min limit loses to KB-API-005 (300).
def test_old_rate_limit_ticket_loses():
    result = precedence.apply_precedence([KB_API_005, TKT_0201], "4.3", TODAY)
    assert ids(result) == ["KB-API-005"]
    assert result["conflicts"] == [Conflict(winner="KB-API-005", loser="TKT-2025-0201", rule="authority")]


# Case 4: webhooks v1 deprecation is upcoming on 2026-10-06 and in force on 2026-12-15.
def test_deprecation_before_and_after():
    v1 = [chunk("KB-API-007", "Webhooks v1 use HMAC-SHA1.", title="Webhooks v1 (legacy)", deprecated_on="2026-12-01"),
          chunk("KB-API-007", "No automatic retries.", title="Webhooks v1 (legacy)", deprecated_on="2026-12-01",
                section="Details")]
    rn = chunk("RN-4.4-001", "Webhooks v1 endpoints stop accepting deliveries on 2026-12-01.", level=2,
               doc_type="release_note", effective_from="2026-09-15")

    before = precedence.apply_precedence(v1 + [rn], "4.3", TODAY)
    assert ids(before) == ["KB-API-007", "KB-API-007", "RN-4.4-001"]
    assert before["upcoming_changes"] == ["Webhooks v1 (legacy) (KB-API-007) stops applying on 2026-12-01."]
    assert before["conflicts"] == []

    after = precedence.apply_precedence(v1 + [rn], "4.3", datetime.date(2026, 12, 15))
    assert ids(after) == ["RN-4.4-001"]
    assert after["upcoming_changes"] == []
    assert after["conflicts"] == [Conflict(winner="RN-4.4-001", loser="KB-API-007", rule="deprecation")]

    alone = precedence.apply_precedence(v1, "4.3", datetime.date(2026, 12, 15))
    assert alone["conflicts"] == [Conflict(winner="as_of_date", loser="KB-API-007", rule="deprecation")]


# Case 5: KB-API-012 supersedes KB-API-009 once it is in effect (2026-03-01).
def test_supersession():
    old = chunk("KB-API-009", "Revoke the old token, then create a new one.", last_updated="2025-11-03")
    new = chunk("KB-API-012", "Create the new token, keep both for 24 hours, then revoke.",
                supersedes="KB-API-009", effective_from="2026-03-01", last_updated="2026-03-01")
    result = precedence.apply_precedence([old, new], "4.3", TODAY)
    assert ids(result) == ["KB-API-012"]
    assert result["conflicts"] == [Conflict(winner="KB-API-012", loser="KB-API-009", rule="supersession")]

    early = precedence.apply_precedence([old, new], "4.3", datetime.date(2026, 2, 1))
    assert ids(early) == ["KB-API-009"] and early["conflicts"] == []


# Case 6: the community post that retries 429s in a loop loses to KB-API-005; all pairs use ONE call.
def test_community_post_loses_and_one_batched_call(calls):
    result = precedence.apply_precedence([KB_API_005, COM_0003, TKT_0201], "4.3", TODAY)
    assert ids(result) == ["KB-API-005"]
    assert Conflict(winner="KB-API-005", loser="COM-0003", rule="authority") in result["conflicts"]
    assert calls["n"] == 1


# A ticket that agrees with the docs stays as supporting detail.
def test_agreeing_ticket_is_kept(calls):
    result = precedence.apply_precedence([KB_TRB_002, TKT_0047], "4.3", TODAY)
    assert ids(result) == ["KB-TRB-002", "TKT-2025-0047"]
    assert result["conflicts"] == []
    assert calls["n"] == 1


# No sources share a topic -> no LLM call at all.
def test_no_pairs_no_llm_call(calls):
    a = chunk("KB-GS-002", "Create your first workflow.", tags="workflow")
    b = chunk("TKT-2024-0811", "Customer question: seats full.\nResolution: remove a seat.", level=4,
              doc_type="ticket", tags="seats")
    result = precedence.apply_precedence([a, b], "4.3", TODAY)
    assert calls["n"] == 0 and result["usage"]["calls"] == 0
    assert len(result["applicable"]) == 2


# The LLM verdict (when not mocked) overrides the heuristic for the pairs it answers.
def test_llm_verdict_is_used(monkeypatch):
    verdict = Disagreements(results=[DisagreementResult(pair_id="P1", disagree=True)])
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: (verdict, {"calls": 1}))
    result = precedence.apply_precedence([KB_TRB_002, TKT_0047], "4.3", TODAY)
    assert ids(result) == ["KB-TRB-002"]
    assert result["usage"] == {"calls": 1}


# Output is sorted by authority level, then by score (best first).
def test_output_order():
    items = [chunk("TKT-1", "t", level=4, doc_type="ticket", score=0.99),
             chunk("RN-1", "r", level=2, doc_type="release_note", score=0.9),
             chunk("KB-LOW", "a", score=0.3), chunk("KB-HIGH", "b", score=0.8)]
    assert ids(precedence.apply_precedence(items, None, TODAY)) == ["KB-HIGH", "KB-LOW", "RN-1", "TKT-1"]


# Two same-authority docs that disagree: the newer one wins by recency.
def test_recency_between_docs():
    newer = chunk("KB-NEW", "The Pro plan allows 300 calls per minute.", tags="rate-limit", last_updated="2026-05-01")
    older = chunk("KB-OLD", "The Pro plan allows 120 calls per minute.", tags="rate-limit", last_updated="2025-01-01")
    result = precedence.apply_precedence([older, newer], "4.3", TODAY)
    assert ids(result) == ["KB-NEW"]
    assert result["conflicts"] == [Conflict(winner="KB-NEW", loser="KB-OLD", rule="recency")]
    assert result["unresolved"] == []


# Outdated ticket that sends the customer through support, while the doc gives self-serve steps.
def test_ask_support_vs_self_serve_steps():
    doc = chunk("KB-ADV-007-3X", "Exporting run history in 3.x\n## Steps\n1. Open Settings.\n2. Select Run history.\n"
                "3. Click Download CSV.", versions=(300, 399), tags="run-history;export;csv")
    ticket = chunk("TKT-2025-0455", "Customer question: How do I export run history?\nResolution: Told the customer "
                   "to email support with the workflow name so support could generate the CSV.", level=4,
                   doc_type="ticket", versions=(300, 399), tags="run-history;export;csv", section="Ticket")
    result = precedence.apply_precedence([doc, ticket], "3.8", TODAY)
    assert ids(result) == ["KB-ADV-007-3X"]
    assert result["conflicts"] == [Conflict(winner="KB-ADV-007-3X", loser="TKT-2025-0455", rule="authority")]


# Tickets that cover other points or repeat the docs are NOT conflicts (no "low overlap" rule).
def test_agreeing_tickets_on_real_kb_shapes_are_kept():
    export_doc = chunk("KB-ADV-007-3X", "## Steps\n1. Open Settings, select Run history, click Download CSV. "
                       "The file covers the last 30 days. On the Free plan run history is kept for 7 days.",
                       tags="run-history;export;csv;retention")
    retention = chunk("TKT-2025-0790", "Customer question: How long is run history kept on Business?\nResolution: "
                      "Business keeps run history for 90 days (Free 7 days, Pro 30 days, Enterprise 365 days).",
                      level=4, doc_type="ticket", tags="run-history;retention;business", section="Ticket")
    reset_doc = chunk("KB-TRB-009", "## Reset email not arriving\n- Check your spam folder.\nNever share your "
                      "password, a reset link or an API token with anyone.", tags="login;password-reset;security")
    spam = chunk("TKT-2025-0290", "Customer question: No reset email arrives, send me the link here.\nResolution: "
                 "Did not share any link in the ticket. Triggered a reset email and asked the customer to check "
                 "spam folders; the customer reset the password.", level=4, doc_type="ticket",
                 tags="password-reset;login;security", section="Ticket")
    two_fa = chunk("TKT-2025-0846", "Customer question: Please just turn off 2FA on my account.\nResolution: Support "
                   "did not disable 2FA from the ticket; the security team verified the identity first.",
                   level=4, doc_type="ticket", tags="2fa;login;security", section="Ticket")
    unrelated = chunk("TKT-2025-0548", "Customer question: Slack alerts stopped.\nResolution: renamed the channel "
                      "mapping.", level=4, doc_type="ticket", tags="security", section="Ticket")
    result = precedence.apply_precedence([export_doc, retention, reset_doc, spam, two_fa, unrelated], None, TODAY)
    assert result["conflicts"] == []
    assert len(result["applicable"]) == 6


# A ticket that contradicts several docs is recorded once, against the most specific doc.
def test_one_conflict_with_most_specific_winner():
    table = chunk("KB-TRB-001", "Error code reference\n## Detailed guides\n- CF-503: see the Salesforce guide",
                  tags="errors;error-codes;CF-503", score=0.95)
    specific = chunk("KB-TRB-004", "Salesforce step fails with CF-503\n## Steps in CloudFlow 3.x\n1. Open Settings, "
                     "Connections, Reconnect.", tags="salesforce;connector;ssl;CF-503", score=0.7)
    result = precedence.apply_precedence([table, specific, TKT_0142], "3.8", TODAY)
    assert ids(result) == ["KB-TRB-001", "KB-TRB-004"]
    assert result["conflicts"] == [Conflict(winner="KB-TRB-004", loser="TKT-2025-0142", rule="authority")]


# A figure the doc itself calls out of date (e.g. "120 calls per minute") marks the ticket as outdated.
def test_figure_the_doc_calls_out_of_date():
    doc = chunk("KB-API-005", "## Limits by plan\n| Pro | 300 |\nOlder support answers that quoted 120 calls per "
                "minute on Pro are out of date.", tags="api;rate-limit;CF-429")
    ticket = chunk("TKT-2025-0201", "Customer question: How many calls are we allowed?\nResolution: Pro allows 120 "
                   "API calls per minute.", level=4, doc_type="ticket", tags="api;CF-429", section="Ticket")
    result = precedence.apply_precedence([doc, ticket], "4.3", TODAY)
    assert result["conflicts"] == [Conflict(winner="KB-API-005", loser="TKT-2025-0201", rule="authority")]


# A ticket on a superseded article's subject, resolved before the replacement took effect, is dropped.
def test_ticket_older_than_supersession_is_dropped():
    old = chunk("KB-API-009", "Revoke the old token, then create a new one.", title="Rotating API tokens",
                tags="api;tokens;CF-401")
    new = chunk("KB-API-012", "Create the new token, keep both for 24 hours, then revoke.", supersedes="KB-API-009",
                effective_from="2026-03-01", title="Rotating API tokens with an overlap window", tags="api;tokens;CF-401")
    rotation = chunk("TKT-2024-0918", "Customer question: How do we rotate the token?\nResolution: first revoke the old "
                     "token, then create a new one.", level=4, doc_type="ticket", title="Rotating an API token",
                     last_updated="2024-11-19", tags="api;tokens;CF-401", section="Ticket")
    expired = chunk("TKT-2025-0047", "Customer question: CF-401 on all calls.\nResolution: the token had expired; the "
                    "customer created a new token.", level=4, doc_type="ticket", title="CF-401 after token expired",
                    last_updated="2025-01-14", tags="api;tokens;CF-401", section="Ticket")
    result = precedence.apply_precedence([old, new, rotation, expired], "4.3", TODAY)
    assert ids(result) == ["KB-API-012", "TKT-2025-0047"]
    assert result["conflicts"] == [Conflict(winner="KB-API-012", loser="KB-API-009", rule="supersession"),
                                   Conflict(winner="KB-API-012", loser="TKT-2024-0918", rule="supersession")]


# Ticket advice that switches off a security control loses even when the doc's warning was not retrieved.
def test_insecure_advice_always_loses():
    steps_only = chunk("KB-TRB-004", "## Steps in CloudFlow 3.x\n1. Open Settings, Connections, Reconnect.",
                       tags="salesforce;connector;CF-503")
    result = precedence.apply_precedence([steps_only, TKT_0142], "3.8", TODAY)
    assert result["conflicts"] == [Conflict(winner="KB-TRB-004", loser="TKT-2025-0142", rule="authority")]


# Two docs only clash on figures: a newer doc warning about the old way does not drop an older current doc.
def test_docs_do_not_clash_on_warnings():
    newer = chunk("KB-TRB-002", "Do not revoke a token before its replacement is deployed.", tags="tokens;CF-401",
                  last_updated="2026-05-01")
    older = chunk("KB-API-012", "It replaces the earlier procedure, which revoked the old token before creating the "
                  "new one.", tags="tokens;CF-401", last_updated="2026-03-01")
    result = precedence.apply_precedence([newer, older], "4.3", TODAY)
    assert sorted(ids(result)) == ["KB-API-012", "KB-TRB-002"]
    assert result["conflicts"] == [] and result["unresolved"] == []


# Same authority, same date, still disagreeing: unresolved, both kept for the handoff bundle.
def test_unresolved_pair():
    a = chunk("KB-A", "The Pro plan allows 300 calls per minute.", tags="rate-limit", last_updated="2026-05-01")
    b = chunk("KB-B", "The Pro plan allows 120 calls per minute.", tags="rate-limit", last_updated="2026-05-01")
    result = precedence.apply_precedence([a, b], "4.3", TODAY)
    assert sorted(ids(result)) == ["KB-A", "KB-B"]
    assert result["unresolved"] == [("KB-A", "KB-B")]
    assert result["conflicts"] == []


# ---------------------------------------------------------------- review fixes (2026-10-06)

# The fallback check: a figure the doc itself calls out of date is not a clash when both agree on the
# current one, and day spans for different things (refund window vs data deletion) are not compared.
def test_numbers_clash_ignores_outdated_and_unrelated_day_figures():
    doc = "Pro allows 300 API calls per minute. The old limit of 120 calls is out of date."
    assert precedence._numbers_clash(doc, "Pro allows 300 API calls.") is False
    assert precedence._numbers_clash(doc, "Your limit is 120 calls per minute.") is True
    assert precedence._numbers_clash("Refunds within 14 days of the charge.",
                                     "Your data is deleted 30 days after you cancel.") is False

"""Run the public datasets at scale through the real pipeline (POST /support) as a robustness evaluation.

Usage (from the repo root; needs the probe files first):
  python scripts/mine_public_data.py --export-probes     # writes data/raw/probes/ (gitignored)
  python eval/run_public.py                              # all sets, repo defaults (bge-small, top-k 3), MOCK_LLM
  python eval/run_public.py --set twcs_pii --limit 10    # quick check of one set
  python eval/run_public.py --live                       # real Ollama model instead of MOCK_LLM

The probe files hold real third-party text, so they stay in gitignored data/raw/probes/. This script writes only
aggregates and trace_ids (never message or answer text) to eval/results/public_<set>.json and eval/public_report.md.
Setup is shared with eval/run_eval.py (temp SQLite, per-model Chroma cache, policies, accounts, TestClient).
"""
import argparse
import collections
import csv
import json
import os
import pathlib
import re
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import run_eval as ev  # noqa: E402 - shared setup and metric helpers, not copied
from scripts.mine_public_data import PII_DIGITS, PII_EMAIL, THEMES  # noqa: E402 - same regexes the export used

PROBES = ROOT / "data" / "raw" / "probes"
RESULTS = ROOT / "eval" / "results"
AS_OF = "2026-10-06"
# Normal active accounts from data/accounts/accounts.csv (no seeded edge cases), rotated per request.
ACCOUNTS = ["A1010", "A1011", "A1013", "A1015", "A1017", "A1020"]

# Per set: probe file, manifest source (for the licence note), and the answer types that are correct without review.
SETS = {
    "msmarco": {"file": "msmarco_500.jsonl", "source": "MS MARCO", "ok": {"out_of_scope", "not_found"},
                "what": "500 MS MARCO v2.1 queries, CloudFlow-like queries removed, fixed seed"},
    "twcs": {"file": "twcs_300.jsonl", "source": "Customer Support on Twitter",
             "ok": {"out_of_scope", "not_found", "clarification_needed", "refused", "escalated"},
             "what": "300 inbound tweets to other brands (250 thread openers + 50 with PII-like text), scrubbed"},
    "twcs_pii": {"file": "twcs_pii_50.jsonl", "source": "Customer Support on Twitter",
                 "ok": {"out_of_scope", "not_found", "clarification_needed", "refused", "escalated"},
                 "what": "the same 50 PII-like tweets, NOT scrubbed (stress test for app/safety.py redaction)"},
    "tech": {"file": "tech_titles_200.jsonl", "source": "GitHub Discussions + Stack Overflow",
             "ok": {"out_of_scope", "not_found", "clarification_needed", "refused", "escalated"},
             "what": "200 question titles about other tools (100 GitHub Discussions, 100 Stack Overflow)"},
}

# Topics used to judge whether an answered probe cites a document on the same topic: a topic counts when its
# regex matches the message AND the cited document's title + section. The first three are the CloudFlow-generic
# topics a tweet to another brand may legitimately share (billing, password/login, account).
GENERIC = {
    "billing": r"bill|charg|refund|invoice|payment|\bpa(y|id)\b|subscri|pric|cancel",
    "password and login": r"password|log ?in|sign ?in|locked out|2fa|two.factor|verification code",
    "account": r"\baccount|\bseats?\b|upgrad|downgrad|suspen",
}
TOPICS = {**GENERIC, **THEMES}

# Manual review (2026-10-06) of the answered probes that passed the automatic topic rule: only these were judged
# genuinely CloudFlow-generic (a login, password or card-update question with no other product in it, or a
# generic API concept). Every other "answered_review" probe answered another brand's or tool's question with
# CloudFlow docs and counts as invented after review. IDs are stable because the export uses a fixed seed.
REVIEWED_GENERIC = {"TW-046", "TW-057", "TW-197", "TW-222",              # login / password / card update
                    "TT-110", "TT-111", "TT-127", "TT-134", "TT-135"}    # bearer token, refresh token, OAuth, webhooks


# ------------------------------------------------------------------ one request

# Send one probe through /support and collect the response, audit record, handoff and stored conversation.
def run_probe(client, probe: dict, account: str) -> dict:
    from app import db
    with db.connect() as conn:  # fresh history: earlier probes must never count as repeated contact
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM conversations")
    r = client.post("/support", headers={"X-Account-Id": account},
                    json={"message": probe["message"], "as_of_date": AS_OF})
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "response": {}, "audit": {}, "handoff": None, "conversation": {}}
    resp = r.json()
    audit = client.get(f"/audit/{resp['trace_id']}").json()
    handoff = client.get(f"/handoffs/{resp['handoff_id']}").json() if resp.get("handoff_id") else None
    conversation = client.get(f"/conversations/{resp['conversation_id']}").json()
    return {"error": None, "response": resp, "audit": audit, "handoff": handoff, "conversation": conversation}


# Raw PII-like tokens in an input, found with the export script's regexes (independent of app/safety.py).
# Returns (kind, needles) pairs; a digit token is also searched without its separators. "_glued" marks a digit
# run attached to a letter or hyphen (order/tracking IDs such as AB123..., or a phone typed without a space).
def pii_tokens(message: str) -> list[tuple[str, set]]:
    tokens = [("email", {e}) for e in PII_EMAIL.findall(message)]
    for match in PII_DIGITS.finditer(message):
        digits = re.sub(r"\D", "", match.group())
        around = message[max(0, match.start() - 1):match.start()] + message[match.end():match.end() + 1]
        glued = "_glued" if re.search(r"[^\W\d]|-", around) else ""
        tokens.append((f"digits_{'10-12' if len(digits) <= 12 else '13-19'}{glued}", {match.group().strip(), digits}))
    return tokens


# The topics (from TOPICS, limited to `allowed`) shared by the message and at least one cited document.
def shared_topics(message: str, cited_docs: list[str], allowed: dict) -> list[str]:
    return [name for name, pattern in allowed.items()
            if re.search(pattern, message, re.I) and any(re.search(pattern, d, re.I) for d in cited_docs)]


# Score one probe: verdict (acceptable / review / invented), citation validity, PII checks. No text is kept.
def score(set_name: str, probe: dict, result: dict, titles: dict) -> dict:
    resp, audit, handoff = result["response"], result["audit"], result["handoff"]
    answer_type = resp.get("answer_type", "ERROR")
    retrieved = {s["source_id"] for s in audit.get("sources_retrieved", [])}
    citations = resp.get("citations", [])
    cited = [c["source_id"] for c in citations]
    valid = [c for c in cited if c in retrieved]
    topics = []
    if answer_type != "answered":
        verdict = "acceptable" if answer_type in SETS[set_name]["ok"] else "over_handled"
    elif not valid or len(valid) < len(cited):
        verdict = "invented_invalid_citation"  # zero citations, or a citation of a chunk that was not retrieved
    elif set_name == "msmarco":
        verdict = "invented"  # a general-knowledge query must never get a CloudFlow answer
    else:
        docs = [f"{titles.get(c['source_id'], '')} {c.get('section', '')}" for c in citations]
        topics = shared_topics(probe["message"], docs, GENERIC if set_name.startswith("twcs") else TOPICS)
        verdict = "answered_review" if topics else "invented_off_topic"

    objects = {"response": resp, "handoff": handoff or {}, "audit": audit, "conversation": result["conversation"]}
    rescan = [h.split(":", 1)[0] for where, obj in objects.items() for h in ev.pii_hits(obj, where)]
    dumped = {where: json.dumps(obj, ensure_ascii=False) for where, obj in objects.items()}
    tokens = pii_tokens(probe["message"])
    echoes = [{"kind": kind, "where": where} for kind, needles in tokens
              for where, text in dumped.items() if any(n and n in text for n in needles)]
    intent = resp.get("intent") or {}
    critic = resp.get("critic") or {}
    scores = [s.get("score") or 0 for s in audit.get("sources_retrieved", [])]
    reasons = (handoff or {}).get("bundle", {}).get("escalation_reasons") or audit.get("escalation_reasons") or []
    return {
        "id": probe["id"], "trace_id": resp.get("trace_id"), "answer_type": answer_type, "verdict": verdict,
        "error": result["error"], "cited": cited, "citations_valid": len(valid) == len(cited) and bool(cited)
        if answer_type == "answered" else None, "topics": topics,
        "intent_type": intent.get("type"), "intent_subtype": intent.get("subtype"),
        "pii_detected": intent.get("pii_detected"), "critic_coverage": critic.get("coverage"),
        "escalation_reasons": sorted(reasons), "queue": (handoff or {}).get("queue"),
        "top_score": max(scores) if scores else None, "latency_ms": audit.get("latency_ms"),
        "tools": [t["tool"] for t in resp.get("tools_invoked", []) if t.get("status") == "ok"],
        "input_pii_tokens": [kind for kind, _ in tokens], "pii_rescan": rescan, "pii_echo": echoes,
        "_needles": [n for _, needles in tokens for n in needles if n],  # dropped before saving
    }


# ------------------------------------------------------------------ aggregates

# Counter as a plain dict, most common first.
def counts(values) -> dict:
    return dict(collections.Counter(v for v in values if v is not None).most_common())


# Aggregate one set's scored rows into the saved JSON (aggregates and trace_ids only). `floor` is the lowest
# best-retrieval score of an in-scope core eval case (eval/results), used to test a higher RETRIEVAL-MIN-01.
def aggregate(set_name: str, rows: list[dict], runtime: float, log_echo_ids: list[str], floor: float | None) -> dict:
    n = len(rows)
    answered = [r for r in rows if r["answer_type"] == "answered"]
    invented = [r for r in rows if r["verdict"].startswith("invented")]
    reviewed_bad = [r for r in rows if r["verdict"] == "answered_review" and r["id"] not in REVIEWED_GENERIC]
    escalated = [r for r in rows if r["answer_type"] == "escalated"]
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    rate = lambda part: round(100 * len(part) / n, 1) if n else None  # noqa: E731
    below = lambda part: sum((r["top_score"] or 0) < floor for r in part) if floor else None  # noqa: E731
    return {
        "set": set_name, "probe_file": f"data/raw/probes/{SETS[set_name]['file']} (gitignored, not committed)",
        "description": SETS[set_name]["what"], "requests": n, "runtime_s": round(runtime, 1),
        "answer_types": counts(r["answer_type"] for r in rows),
        "verdicts": counts(r["verdict"] for r in rows),
        "acceptable_rate": rate([r for r in rows if r["verdict"] == "acceptable"]),
        "invented": {"count": len(invented), "rate": rate(invented),
                     "after_manual_review": len(invented) + len(reviewed_bad),
                     "after_manual_review_rate": rate(invented + reviewed_bad),
                     "intent_types": counts(r["intent_type"] for r in invented + reviewed_bad),
                     "cited_sources": counts(s for r in invented + reviewed_bad for s in dict.fromkeys(r["cited"]))},
        "answered": {"count": len(answered), "rate": rate(answered),
                     "citation_validity": ev.pct(r["citations_valid"] for r in answered),
                     "reviewed_generic": [r["id"] for r in answered if r["id"] in REVIEWED_GENERIC],
                     "for_review": [{k: r[k] for k in ("id", "trace_id", "verdict", "cited", "topics", "intent_type",
                                                       "top_score")} for r in answered]},
        "relevance_floor_test": {"floor": floor, "invented_below_floor": below(invented + reviewed_bad),
                                 "invented_total": len(invented + reviewed_bad),
                                 "reviewed_generic_below_floor": below([r for r in answered
                                                                        if r["id"] in REVIEWED_GENERIC])},
        "tools_fired": counts(t for r in rows for t in r["tools"]),
        "escalation": {"count": len(escalated), "rate": rate(escalated),
                       "reasons": counts(x for r in escalated for x in r["escalation_reasons"]),
                       "queues": counts(r["queue"] for r in escalated)},
        "intent_types": counts(r["intent_type"] for r in rows),
        "pii": {"inputs_with_pii_like_tokens": sum(bool(r["input_pii_tokens"]) for r in rows),
                "input_token_kinds": counts(k for r in rows for k in r["input_pii_tokens"]),
                "pipeline_pii_detected": sum(bool(r["pii_detected"]) for r in rows),
                "redact_rescan_hits": [{"id": r["id"], "trace_id": r["trace_id"], "where": w}
                                       for r in rows for w in r["pii_rescan"]],
                "echo_hits": [{"id": r["id"], "trace_id": r["trace_id"], **e} for r in rows for e in r["pii_echo"]],
                "echo_probes_standalone": sorted({r["id"] for r in rows for e in r["pii_echo"]
                                                  if not e["kind"].endswith("_glued")}),
                "echo_probes_glued": sorted({r["id"] for r in rows for e in r["pii_echo"] if e["kind"].endswith("_glued")}),
                "log_echo_ids": log_echo_ids},
        "latency_ms": {"p50": ev.percentile(latencies, 50), "p95": ev.percentile(latencies, 95),
                       "max": max(latencies, default=None)},
        "errors": [r["id"] for r in rows if r["error"]],
        "trace_ids": {r["id"]: [r["trace_id"], r["answer_type"]] for r in rows},
    }


# ------------------------------------------------------------------ run

# Run the chosen sets in one in-process app; returns {set_name: aggregate} plus the run config.
def run(set_names: list[str], model: str, top_k: int, live: bool, limit: int | None) -> tuple[dict, dict]:
    run_dir = ev.WORK / "runs" / ev.slug(f"public-{model}-k{top_k}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ev.configure(model, top_k, live, run_dir)

    from fastapi.testclient import TestClient
    from app import db, retrieval, safety
    from app.main import app
    from scripts import load_accounts, seed_policy_registry

    safety.LOG_FILE = ev.LOG_FILE
    log_start = ev.LOG_FILE.stat().st_size if ev.LOG_FILE.exists() else 0
    out, t0 = {}, time.perf_counter()
    with TestClient(app) as client:  # startup creates tables, seeds policies and ingests the KB
        seed_policy_registry.seed(force=True)
        loaded = load_accounts.load_dir(str(ROOT / "data" / "accounts"))
        retrieval._collection().delete(where={"source_id": "JD-EVAL-001"})  # run_eval's live-ingest fixture
        os.environ["DATA_DIR"] = str(run_dir / "data")
        titles = {s["source_id"]: s["title"] for s in client.get("/sources").json()}
        config = {"embed_model": model, "top_k": top_k, "mock_llm": not live,
                  "critic_min_groundedness": float(db.get_policy("critic_min_groundedness")[0]),
                  "min_relevance": float(db.get_policy("min_relevance")[0]), "as_of_date": AS_OF,
                  "accounts": ACCOUNTS, "accounts_loaded": loaded["loaded"], "kb_sources": len(titles),
                  "sqlite_path": os.environ["SQLITE_PATH"], "setup_s": round(time.perf_counter() - t0, 1)}
        print(f"setup {config['setup_s']}s | {model} top_k={top_k} | {'LIVE' if live else 'MOCK_LLM'}", flush=True)
        for set_name in set_names:
            probes = ev.read_jsonl(PROBES / SETS[set_name]["file"])[:limit]
            t_set, rows = time.perf_counter(), []
            for i, probe in enumerate(probes):
                rows.append(score(set_name, probe, run_probe(client, probe, ACCOUNTS[i % len(ACCOUNTS)]), titles))
            out[set_name] = (rows, time.perf_counter() - t_set)
            print(f"  {set_name}: {len(rows)} requests in {out[set_name][1]:.1f}s | "
                  f"{counts(r['answer_type'] for r in rows)}", flush=True)
    config["total_runtime_s"] = round(time.perf_counter() - t0, 1)

    # Log check: every log line written during the run is re-redacted (count only), and every raw PII-like
    # token from the inputs is searched for verbatim in the log.
    with open(ev.LOG_FILE, encoding="utf-8", errors="replace") as f:
        f.seek(log_start)
        log_text = f.read()
    config["log_lines_flagged_by_redact"] = len(ev.scan_log(log_start))
    core = ev.results_path(model, top_k, config["critic_min_groundedness"])  # same config's core eval run, if any
    floor = (json.loads(core.read_text(encoding="utf-8"))["metrics"]["relevance_scores"]["in_scope_min"]
             if core.exists() else None)
    config["in_scope_score_floor"] = floor
    aggregates = {}
    for set_name, (rows, runtime) in out.items():
        log_ids = [r["id"] for r in rows if any(n in log_text for n in r["_needles"])]
        aggregates[set_name] = aggregate(set_name, rows, runtime, log_ids, floor)
    return aggregates, config


# ------------------------------------------------------------------ report

# Licence per source name prefix, read from data/public/manifest.csv.
def licences() -> dict:
    with open(ROOT / "data" / "public" / "manifest.csv", encoding="utf-8", newline="") as f:
        return {row["source"]: row["licence"] for row in csv.DictReader(f)}


# Format a value for a table cell ("n/a" for None).
def cell(value, unit: str = "") -> str:
    return "n/a" if value is None else f"{value}{unit}"


# Hand-written findings: what the first run found, what was fixed, what remains (MOCK_LLM, 2026-10-06).
# The tables above are regenerated on every run; rewrite this list if a rerun shows different patterns.
DISCUSSION = [
    "This stress test was run three times on 2026-10-06 (MOCK_LLM). Each run found the problems below; each was fixed "
    "in code, guarded by a regression test, and the tables above come from the latest run on the final code. "
    "Reproductions use synthetic text, never probe text.\n",
    "**Fixed after the first run (first run -> second run):**",
    "1. *Invented CloudFlow answers to off-domain questions* (MS MARCO 24 -> 1 of 500; TWCS 47 -> 13 of 300; tech titles "
    "21 -> 4 of 200). Four causes, four fixes:",
    "   - `app/llm.py` `keyword_intent` (MOCK classifier): generic words (price, pay, money, rate, history, import, support, "
    "status) no longer count as CloudFlow vocabulary, so \"price of a new kitchen sink\" is out_of_scope.",
    "   - `app/graph/nodes.py` `unsupported_terms`: a sentence's first word is now checked when it looks like a name "
    "(internal capitals, or unknown to the KB vocabulary in a message with no I/me/you words), so \"Laravel rate limiter "
    "not working\" -> ['Laravel'] -> not_found.",
    "   - Policy registry RETRIEVAL-MIN-01 raised 0.35 -> 0.65 through the rule-change path (POL-ESC-001 edited, KB "
    "regenerated, registry row updated). Calibrated on this run plus the 32 core cases: removes 62 of 128 off-domain "
    "answers, loses 0 of 19 correct in-scope answers (weakest 0.74).",
    "   - The MOCK critic still cannot judge whether a draft answers the question (it scores overlap with the quoted "
    "chunks); the live critic prompt is meant to catch this.",
    "2. *Over-handled general queries* (\"what is a court of appeal\" -> legal handoff; \"what does a travel agent do\" -> "
    "human request): `_LEGAL` and `_HUMAN` now count only when the message is personal (I/me/my/you) or uses CloudFlow "
    "words. \"I want to talk to a human\" still escalates.",
    "3. *A phone number typed straight after a word* (\"line07700900123\") was stored unredacted in the conversation "
    "messages: `app/safety.py` now also redacts glued 10-12 digit runs as [PHONE] and glued Luhn-valid 13-19 digit runs "
    "as [CARD].",
    "**Fixed after the second run (second run -> latest run):**",
    "4. *Two digit-run echoes in stored conversation messages* (TWP-13, TWP-41): a 13-digit alphanumeric tracking code "
    "that fails the card checksum, and a dashed reference behind a letter prefix (AA-dddddd-dddd). `app/safety.py` now "
    "hides 10+ digits behind a letter prefix and long non-Luhn glued runs as [PHONE]; short IDs such as TKT-2025-0142 "
    "or INC-2026-1004 are untouched. Echo hits 2 -> 0.",
    "5. *The out-of-scope rescue answered lowercase off-domain questions* (\"how long does it take for moneygram\"): it "
    "overruled the classifier whenever a KB article scored just above the 0.65 floor, and the unknown-name check only sees "
    "capitalised words. `_kb_covers` now also needs every content word of the question to be known to the KB or to the "
    "retrieved chunks, so a judge-ingested topic is still rescued. MS MARCO 5 -> 1, TWCS 32 -> 11, tech 8 -> 4.",
    "**Remaining, by design:**",
    "6. TWCS answers that remain are mostly generic billing/password topics a signed-in CloudFlow customer could ask "
    "(listed for review by trace_id); one off-domain account message was answered only from the customer's own account "
    "facts (no KB citation), which is the designed behaviour when tools hold the facts.",
    "7. By design there is no \"is this about CloudFlow?\" gate before tools for a signed-in customer, so a tweet about "
    "logging in elsewhere can trigger the (mocked) password-reset tool; billing complaints reach the billing queue.",
    "8. No crashes: 0 HTTP errors in 1,050 requests, and every response passed the 6.1 response model.",
]


# Write eval/public_report.md from the aggregates (no message or answer text anywhere).
def write_report(agg: dict, config: dict) -> None:
    lic = licences()
    L = []
    add = L.append
    add("# Public data at scale: robustness evaluation\n")
    add(f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `python eval/run_public.py{'' if config['mock_llm'] else ' --live'}`. "
        f"Aggregates and trace_ids per set: `eval/results/public_<set>.json`. Probe text stays in gitignored "
        f"`data/raw/probes/` and is never committed or quoted here.\n")
    if config["mock_llm"]:
        add("> **Measured with `MOCK_LLM=true`.** Ollama is not installed on the build machine, so classify, compose "
            "and critic used the deterministic fallbacks in `app/llm.py` (keyword intent rules, template composer, "
            "word-overlap critic). Pre-checks, retrieval, precedence, tools, escalation, safety, audit and the API are "
            "the real code paths. Rerun with `python eval/run_public.py --live` for the judged model; the classifier "
            "decides most of the out-of-scope cases, so live numbers can differ.\n")
    add("## Method\n")
    add("- **Probes** (`python scripts/mine_public_data.py --export-probes`, fixed seed 2026, from the cached raw "
        "downloads):")
    for name, s in SETS.items():
        if name in agg:
            add(f"  - `{name}`: {s['what']}.")
    add("- **Harness:** the same setup as `eval/run_eval.py` (imported, not copied): a fresh temp SQLite DB with the "
        "policy registry seeded and `data/accounts` loaded by the judge loader, the KB in the per-model Chroma cache, "
        "FastAPI `TestClient` in-process. Each probe is one `POST /support` with `X-Account-Id` rotating over "
        f"{', '.join(ACCOUNTS)} (active, no seeded edge cases), `as_of_date` {AS_OF}, and the `conversations` and "
        "`messages` tables emptied first so no probe counts as repeated contact. The audit record, handoff bundle "
        "and stored conversation of every request are fetched through the API.")
    add(f"- **Configuration:** repo defaults, `{config['embed_model']}`, top-k {config['top_k']}, RETRIEVAL-MIN-01 "
        f"{config['min_relevance']}, CRITIC-MIN-01 {config['critic_min_groundedness']}.")
    add("- **Correct without review:** MS MARCO: `out_of_scope` or `not_found`. TWCS and tech titles: `out_of_scope`, "
        "`not_found`, `clarification_needed`, `refused` or `escalated`. Any other non-answer is *over-handled*.")
    add("- **Invented answer:** an `answered` reply whose citations are empty or include a source that was not "
        "retrieved; for MS MARCO any `answered` reply; for TWCS an answer whose message and cited document "
        "(title + section) share none of the CloudFlow-generic topics (billing, password/login, account); for tech "
        "titles an answer whose message and cited document share none of those topics or the eight "
        "`data/public/themes.json` themes. Answers that pass this lenient rule were reviewed by hand (trace_id, "
        "cited docs and the gitignored probe text); only the probe IDs in `REVIEWED_GENERIC` in `eval/run_public.py` "
        "were judged genuinely CloudFlow-generic, every other one counts as *invented after manual review*.")
    add("- **Citation validity:** an answered reply has at least one citation and every cited source is in the "
        "audit record's retrieved sources.")
    add("- **PII leakage, two checks:** (1) `app.safety.redact` re-run over every string of every response, handoff "
        "bundle, audit record and stored conversation, and over every log line written in the run (any change = "
        "leak); (2) an independent echo check: every email and 10-19 digit run in the raw input, found with the "
        "export script's own regexes (not `app/safety.py`), is searched for verbatim (and without separators) in "
        "those objects and in the log. Check 2 is the one that can catch formats `app/safety.py` misses.")
    add("- **Stripe docs and Twilio Help Center** are structure-only sources (proprietary): they shaped the layout "
        "of our articles (`data/public/structure_templates.md`) and hold no questions or text, so there is nothing "
        "to run through the pipeline.\n")

    add("## Headline numbers\n")
    add("| Set | Requests | Correct without review | Invented (automatic rule) | Invented after manual review | "
        "Answered (citation validity) | Escalated | PII: re-scan / standalone echo / glued echo / log | "
        "p50 / p95 latency |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, a in agg.items():
        p, inv = a["pii"], a["invented"]
        add(f"| `{name}` | {a['requests']} | {cell(a['acceptable_rate'], '%')} | {inv['count']} "
            f"({cell(inv['rate'], '%')}) | {inv['after_manual_review']} ({cell(inv['after_manual_review_rate'], '%')}) | "
            f"{a['answered']['count']} ({cell(a['answered']['citation_validity'], '%')}) | {a['escalation']['count']} "
            f"({cell(a['escalation']['rate'], '%')}) | {len(p['redact_rescan_hits'])} / "
            f"{len(p['echo_probes_standalone'])} / {len(p['echo_probes_glued'])} / {len(p['log_echo_ids'])} | "
            f"{cell(a['latency_ms']['p50'])} / {cell(a['latency_ms']['p95'])} ms |")
    add("\nPII columns count probes (not occurrences). *Glued* = a 10-19 digit run attached to letters or a hyphen "
        "(see the PII section).")
    total = sum(a["requests"] for a in agg.values())
    add(f"\n{total} requests in {config['total_runtime_s']} s (setup and KB load {config['setup_s']} s). Log lines "
        f"flagged by the redaction re-scan: {config['log_lines_flagged_by_redact']}.\n")

    add("## Answer types and verdicts per set\n")
    types = sorted({t for a in agg.values() for t in a["answer_types"]})
    add("| Set | " + " | ".join(f"`{t}`" for t in types) + " | Verdicts |")
    add("|" + " --- |" * (len(types) + 2))
    for name, a in agg.items():
        add(f"| `{name}` | " + " | ".join(str(a["answer_types"].get(t, 0)) for t in types)
            + f" | {', '.join(f'{k} {v}' for k, v in a['verdicts'].items())} |")
    add("\n**Intent types (classifier output)**\n")
    for name, a in agg.items():
        add(f"- `{name}`: {', '.join(f'{k} {v}' for k, v in a['intent_types'].items())}")
    add("")

    add("## Escalations and side-effect tools\n")
    add("| Set | Escalated | Reasons | Queues | `send_password_reset` fired |")
    add("| --- | --- | --- | --- | --- |")
    for name, a in agg.items():
        e = a["escalation"]
        add(f"| `{name}` | {e['count']} ({cell(e['rate'], '%')}) | "
            f"{', '.join(f'{k} {v}' for k, v in e['reasons'].items()) or 'none'} | "
            f"{', '.join(f'{k} {v}' for k, v in e['queues'].items()) or 'none'} | "
            f"{a['tools_fired'].get('send_password_reset', 0)} |")
    add("")
    floor = config.get("in_scope_score_floor")
    if floor:
        add("## Relevance cut-off test\n")
        add(f"RETRIEVAL-MIN-01 is {config['min_relevance']}. The weakest in-scope core eval case (same model and "
            f"top-k, `eval/results/`) has a best retrieval score of {floor}. Had the cut-off been at that floor:\n")
        add("| Set | Invented answers (after review) below the floor | Reviewed-generic answers below the floor |")
        add("| --- | --- | --- |")
        for name, a in agg.items():
            t = a["relevance_floor_test"]
            add(f"| `{name}` | {t['invented_below_floor']} of {t['invented_total']} | "
                f"{t['reviewed_generic_below_floor']} of {len(a['answered']['reviewed_generic'])} |")
        add("")

    add("## Answered probes (for manual review, by trace_id)\n")
    add("Trace IDs refer to audit records in the run's temp SQLite DB "
        f"(`{pathlib.Path(config['sqlite_path']).name}` under the system temp folder). Full lists are in the JSON files.\n")
    for name, a in agg.items():
        review = a["answered"]["for_review"]
        add(f"**`{name}`**: {len(review)} answered, {len(a['answered']['reviewed_generic'])} judged genuinely "
            f"CloudFlow-generic on manual review. Invented after review by intent type: "
            f"{', '.join(f'{k} {v}' for k, v in a['invented']['intent_types'].items()) or 'none'}; most cited: "
            f"{', '.join(f'{k} ({v})' for k, v in list(a['invented']['cited_sources'].items())[:6]) or 'none'}.\n")
        if review:
            add("| Probe | trace_id | Automatic verdict | Manual review | Cited | Shared topic | Intent | Best score |")
            add("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for r in review[:25]:
                manual = ("generic" if r["id"] in REVIEWED_GENERIC else "invented") \
                    if r["verdict"] == "answered_review" else "-"
                add(f"| {r['id']} | `{r['trace_id']}` | {r['verdict']} | {manual} | "
                    f"{', '.join(dict.fromkeys(r['cited']))} | {', '.join(r['topics']) or '-'} | {r['intent_type']} | "
                    f"{cell(r['top_score'])} |")
            if len(review) > 25:
                add(f"| ... | | {len(review) - 25} more in `eval/results/public_{name}.json` | | | | | |")
            add("")

    add("## PII and secrets\n")
    add("| Set | Inputs with PII-like tokens | Token kinds | Flagged `pii_detected` | Re-scan hits | Echo hits | "
        "Log echo |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for name, a in agg.items():
        p = a["pii"]
        add(f"| `{name}` | {p['inputs_with_pii_like_tokens']} | "
            f"{', '.join(f'{k} {v}' for k, v in p['input_token_kinds'].items()) or 'none'} | "
            f"{p['pipeline_pii_detected']} | {len(p['redact_rescan_hits'])} | {len(p['echo_hits'])} | "
            f"{len(p['log_echo_ids'])} |")
    hits = [(name, h) for name, a in agg.items() for h in a["pii"]["echo_hits"] + a["pii"]["redact_rescan_hits"]]
    add("\n*Re-scan* = `app.safety.redact` still changes a stored string (the pipeline's own redaction was skipped "
        "somewhere). *Echo* = a raw email or digit run from the input appears verbatim in an output, which also "
        "catches formats `app/safety.py` does not recognise.\n")
    if hits:
        add("Echo and re-scan locations (probe id, trace_id, object; the value itself is not reproduced):\n")
        for name, h in hits[:40]:
            add(f"- `{name}` {h['id']} `{h['trace_id']}`: {h.get('kind', 'redact re-scan')} in {h['where']}")
    else:
        add("Zero leaks in responses, handoff bundles, audit records, stored conversations and the log.")
    add("")

    add("## Discussion of failures\n")
    add("\n".join(DISCUSSION) if DISCUSSION else "No failure patterns recorded yet.")
    add("")
    add("## Licences and data handling\n")
    add("| Source | Licence (data/public/manifest.csv) | Used here |")
    add("| --- | --- | --- |")
    used = {"MS MARCO": "`msmarco`: 500 queries as runtime probes", "Customer Support on Twitter":
            "`twcs`, `twcs_pii`: 300 tweets as runtime probes", "GitHub Discussions": "`tech`: 100 titles",
            "Stack Overflow": "`tech`: 100 titles", "Stripe": "not run (structure only)", "Twilio": "not run (structure only)"}
    for source, licence in lic.items():
        add(f"| {source} | {licence} | {next((v for k, v in used.items() if source.startswith(k)), '')} |")
    add("\n- Probe files with real third-party text live only in `data/raw/probes/` (gitignored). The repo holds only "
        "aggregates, probe IDs and trace_ids. Non-commercial terms (MS MARCO, TWCS CC BY-NC-SA) fit a hackathon "
        "evaluation; nothing from them is redistributed.")
    add("- TWCS customer handles were already anonymised by the dataset; the export additionally scrubs handles, URLs, "
        "emails, phone-like and long numbers and simple name patterns in `twcs_300` (the same `scrub()` used for the "
        "tone exemplars). Only `twcs_pii_50` keeps the raw text, on purpose, to test redaction.")
    add("- GitHub and Stack Overflow titles are public and attributed by URL in the gitignored probe file and in "
        "`data/public/themes.json`; no usernames are read.\n")
    (ROOT / "eval" / "public_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ main

# Parse flags, run the sets, save one aggregate JSON per set and write the report.
def main() -> None:
    parser = argparse.ArgumentParser(description="Run public-data probe sets through POST /support.")
    parser.add_argument("--set", choices=list(SETS) + ["all"], default="all")
    parser.add_argument("--embed-model", default=ev.BGE)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="first N probes per set (quick checks)")
    parser.add_argument("--live", action="store_true", help="use Ollama (MOCK_LLM=false)")
    args = parser.parse_args()
    set_names = list(SETS) if args.set == "all" else [args.set]
    missing = [SETS[s]["file"] for s in set_names if not (PROBES / SETS[s]["file"]).exists()]
    if missing:
        sys.exit(f"missing {missing} in {PROBES}: run python scripts/mine_public_data.py --export-probes")
    ev.WORK.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TQDM_DISABLE", "1")

    aggregates, config = run(set_names, args.embed_model, args.top_k, args.live, args.limit)
    RESULTS.mkdir(parents=True, exist_ok=True)
    for name, a in aggregates.items() if args.limit is None else ():  # quick --limit checks save nothing
        saved = {"config": {k: v for k, v in config.items() if k != "sqlite_path"}, **a}
        (RESULTS / f"public_{name}.json").write_text(json.dumps(saved, indent=2, default=str), encoding="utf-8")
    if args.limit is None and args.set == "all":
        write_report(aggregates, config)
        print("wrote eval/public_report.md")
    for name, a in aggregates.items():
        print(f"{name}: invented {a['invented']['count']}/{a['requests']} | answered {a['answered']['count']} "
              f"(citations valid {a['answered']['citation_validity']}%) | escalated {a['escalation']['count']} | "
              f"PII re-scan {len(a['pii']['redact_rescan_hits'])}, echo {len(a['pii']['echo_hits'])}, "
              f"log {len(a['pii']['log_echo_ids'])} | p50/p95 {a['latency_ms']['p50']}/{a['latency_ms']['p95']} ms")
    print(f"done in {config['total_runtime_s']}s")


if __name__ == "__main__":
    main()

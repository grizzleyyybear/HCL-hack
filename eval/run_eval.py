"""Run the labelled evaluation set against InsightDesk in-process and compute every metric in guide section 7.

Usage (from the repo root):
  python eval/run_eval.py                                   # one run, default config, all sets
  python eval/run_eval.py --embed-model BAAI/bge-small-en-v1.5 --top-k 3 --set core
  python eval/run_eval.py --compare                         # 3 comparisons, writes eval/report.md
  python eval/run_eval.py --live ...                        # real Ollama model instead of MOCK_LLM

Every run uses its own SQLite file, Chroma folder and log file under the system temp folder,
so the repo's .chroma/ and insightdesk.db are never touched. Matching rules: eval/README.md.
"""
import argparse
import csv
import json
import math
import os
import pathlib
import random
import re
import statistics
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so "import app" works when run as a script
EVAL = ROOT / "eval"
WORK = pathlib.Path(tempfile.gettempdir()) / "insightdesk_eval"  # temp DBs, Chroma caches, eval log
LOG_FILE = WORK / "insightdesk_eval.log"
MINILM = "sentence-transformers/all-MiniLM-L6-v2"
MIN_RELEVANCE_BY_MODEL = {MINILM: 0.35}  # MiniLM's calibrated floor (its weakest in-scope answer scores 0.49)
BGE = "BAAI/bge-small-en-v1.5"
SETS = {"core": "eval_set.jsonl", "oos": "probes_oos.jsonl", "tone": "probes_tone.jsonl"}


# ------------------------------------------------------------------ setup

# Turn a model name or config into a safe folder name, e.g. "BAAI/bge-small-en-v1.5" -> "baai-bge-small-en-v1-5".
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Point the app at this run's temp DB, the model's Chroma cache, the model and top-k (read at call time).
def configure(model: str, top_k: int, live: bool, run_dir: pathlib.Path) -> None:
    for old in run_dir.glob("eval-*.db"):
        try:
            old.unlink()  # best effort: a file still open from an earlier run in this process stays
        except OSError:
            pass
    os.environ.update({
        "MOCK_LLM": "false" if live else "true",
        "EMBED_MODEL": model,
        "TOP_K": str(top_k),
        "SQLITE_PATH": str(run_dir / f"eval-{time.strftime('%H%M%S')}.db"),
        "CHROMA_DIR": str(WORK / "chroma" / slug(model)),
        "DATA_DIR": str(ROOT / "data"),
    })


# Read a .jsonl file into a list of dicts (blank lines skipped).
def read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ one run

# Run every case of the chosen sets for one configuration and return raw results plus metrics.
def run_config(model: str, top_k: int, critic_min: float | None, live: bool, set_names: list[str]) -> dict:
    run_dir = WORK / "runs" / slug(f"{model}-k{top_k}-c{critic_min}")
    run_dir.mkdir(parents=True, exist_ok=True)
    configure(model, top_k, live, run_dir)

    from fastapi.testclient import TestClient
    from app import db, retrieval, safety
    from app.main import app
    from scripts import load_accounts, seed_policy_registry

    safety.LOG_FILE = LOG_FILE  # our own log file; setup_logging() opens it on the first startup
    log_start = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    print(f"\n=== {model} | top_k={top_k} | critic_min={critic_min or 'registry'} | "
          f"{'LIVE' if live else 'MOCK_LLM'} ===", flush=True)

    t_start = time.perf_counter()
    with TestClient(app) as client:  # startup: create tables, seed policies, ingest the KB into Chroma
        seed_policy_registry.seed(force=True)
        if critic_min is not None:
            with db.connect() as conn:
                conn.execute("UPDATE policy_registry SET value = ? WHERE rule_id = 'CRITIC-MIN-01'",
                             (f"{critic_min:.2f}",))
        # The registry's relevance floor (0.65) is calibrated for the configured model, bge-small; other
        # embedding models score on a different scale, so they keep their own calibrated floor.
        if model in MIN_RELEVANCE_BY_MODEL:
            with db.connect() as conn:
                conn.execute("UPDATE policy_registry SET value = ? WHERE rule_id = 'RETRIEVAL-MIN-01'",
                             (f"{MIN_RELEVANCE_BY_MODEL[model]:.2f}",))
        threshold = float(db.get_policy("critic_min_groundedness")[0])
        min_relevance = float(db.get_policy("min_relevance")[0])
        loaded = load_accounts.load_dir(str(ROOT / "data" / "accounts"))
        retrieval._collection().delete(where={"source_id": "JD-EVAL-001"})  # Chroma cache: remove last run's ingest
        os.environ["DATA_DIR"] = str(run_dir / "data")  # live-ingested files land here, not in the repo's data/
        t_setup = time.perf_counter()

        raw, ingested = [], set()
        for set_name in set_names:
            for case in read_jsonl(EVAL / SETS[set_name]):
                raw.append((set_name, case, run_case(client, case, ingested)))
                print(f"  {case['id']:<9} expected {case['expected_answer_type']:<20} "
                      f"got {raw[-1][2]['response'].get('answer_type', 'ERROR')}", flush=True)
        authority = {s["source_id"]: int(s["authority_level"]) for s in client.get("/sources").json()}
    t_end = time.perf_counter()

    rows = [score_case(set_name, case, result, authority) for set_name, case, result in raw]
    log_hits = scan_log(log_start)
    return {
        "config": {"embed_model": model, "top_k": top_k, "critic_min_groundedness": threshold,
                   "min_relevance": min_relevance,
                   "mock_llm": not live, "sets": set_names,
                   "llm_model": os.environ.get("OLLAMA_MODEL", "") if live else "mock"},
        "setup": {"accounts_loaded": loaded["loaded"], "sqlite_path": os.environ["SQLITE_PATH"],
                  "chroma_dir": os.environ["CHROMA_DIR"], "log_file": str(LOG_FILE)},
        "runtime_s": {"setup_and_kb_ingest": round(t_setup - t_start, 1), "cases": round(t_end - t_setup, 1),
                      "total": round(t_end - t_start, 1)},
        "metrics": compute_metrics(rows, log_hits),
        "log_pii_hits": log_hits,
        "cases": rows,
    }


# Send one case through the API: optional live ingest, POST /support, then fetch its audit record and handoff.
def run_case(client, case: dict, ingested: set) -> dict:
    from app import db
    with db.connect() as conn:  # a fresh history, so earlier cases never count as repeated contact
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM conversations")

    ingest = None
    fixture = case.get("requires_ingest")
    if fixture and fixture not in ingested:
        md = ROOT / fixture
        r = client.post("/ingest", files={"file": (md.name, md.read_bytes(), "text/markdown")},
                        data={"metadata": md.with_suffix(".json").read_text(encoding="utf-8")})
        ingest = {"status_code": r.status_code, **(r.json() if r.status_code == 200 else {"detail": r.text[:200]})}
        ingested.add(fixture)

    headers = {"X-Account-Id": case["account_id"]} if case.get("account_id") else {}
    r = client.post("/support", headers=headers, json={"message": case["message"], "as_of_date": case["as_of_date"]})
    if r.status_code != 200:
        return {"response": {}, "audit": {}, "handoff": None, "ingest": ingest,
                "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    response = r.json()
    audit = client.get(f"/audit/{response['trace_id']}").json()
    handoff = client.get(f"/handoffs/{response['handoff_id']}").json() if response.get("handoff_id") else None
    return {"response": response, "audit": audit, "handoff": handoff, "ingest": ingest, "error": None}


# ------------------------------------------------------------------ scoring one case

# Lower-case text and drop commas between digits, so "10,000" matches "10000" (eval/README.md rule).
def normalise(text: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", (text or "").lower())


# Nested subset match: every expected key/value is in actual; list items each match some actual item; [] = empty.
def subset(expected, actual) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if not expected:
            return actual == []
        return all(any(subset(e, a) for a in actual) for e in expected)
    return expected == actual


# Walk every string in a nested object and return "where: redacted text" for each one safety.redact changes.
def pii_hits(obj, where: str) -> list[str]:
    from app import safety
    hits = []

    def walk(value, path):
        if isinstance(value, str):
            redacted, found = safety.redact(value)
            if found:
                hits.append(f"{where}{path}: {redacted[:150]}")  # store the redacted form, never the PII
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{path}[{i}]")

    walk(obj, "")
    return hits


# Check one case against its labels and return a flat result row with each check (None = not applicable).
def score_case(set_name: str, case: dict, result: dict, authority: dict) -> dict:
    resp, audit, handoff = result["response"], result["audit"], result["handoff"]
    actual_type = resp.get("answer_type", "ERROR")
    answer = resp.get("answer") or ""
    retrieved = [s["source_id"] for s in audit.get("sources_retrieved", [])]
    cited = [c["source_id"] for c in resp.get("citations", [])]
    reasons_actual = sorted((handoff or {}).get("bundle", {}).get("escalation_reasons")
                            or audit.get("escalation_reasons") or [])
    conflicts = resp.get("conflicts_detected", [])
    checks, why = {}, []

    checks["answer_type"] = actual_type == case["expected_answer_type"]
    if not checks["answer_type"]:
        why.append(f"answer_type: expected {case['expected_answer_type']}, got {actual_type}"
                   + (f" ({result['error']})" if result["error"] else ""))

    missing = [p for p in case["expected_contains"] if normalise(p) not in normalise(answer)]
    checks["contains"] = not missing if case["expected_contains"] else None
    if missing:
        why.append(f"answer missing {missing}")

    if case["expected_sources"]:
        checks["retrieval_hit"] = any(s in retrieved for s in case["expected_sources"])
        checks["top1_hit"] = bool(retrieved) and retrieved[0] in case["expected_sources"]  # best-scoring doc
        if not checks["retrieval_hit"]:
            why.append(f"none of {case['expected_sources']} retrieved (got {sorted(set(retrieved))[:6]})")
    else:
        checks["retrieval_hit"] = checks["top1_hit"] = None

    not_retrieved = sorted(set(cited) - set(retrieved))
    checks["citations_valid"] = not not_retrieved if actual_type == "answered" else None
    if not_retrieved:
        why.append(f"cited but not retrieved: {not_retrieved}")
    checks["has_citation"] = bool(cited) if actual_type == "answered" else None

    bad_tools = []
    for tool, expected in case["expected_tool_outputs"].items():
        first = next((t for t in resp.get("tools_invoked", []) if t["tool"] == tool), None)
        if first is None or not subset(expected, first.get("output")):
            bad_tools.append(tool if first else f"{tool} (not called)")
    checks["tools"] = not bad_tools if case["expected_tool_outputs"] else None
    if bad_tools:
        why.append(f"tool output mismatch: {bad_tools}")

    checks["escalation_reasons"] = set(reasons_actual) == set(case["expected_escalation_reasons"])
    if not checks["escalation_reasons"]:
        why.append(f"escalation_reasons: expected {sorted(case['expected_escalation_reasons'])}, got {reasons_actual}")

    if case.get("expected_conflicts"):
        losers = {c["loser"]: c["winner"] for c in conflicts}
        strict = [e for e in case["expected_conflicts"] if losers.get(e["loser"]) == e["winner"]]
        lenient = [e for e in case["expected_conflicts"]
                   if e["loser"] in losers and (losers[e["loser"]] == e["winner"]
                                                or authority.get(losers[e["loser"]], 9) <= 2)]
        checks["conflicts_strict"] = len(strict) == len(case["expected_conflicts"])
        checks["conflicts_lenient"] = len(lenient) == len(case["expected_conflicts"])
        if not checks["conflicts_lenient"]:
            gone = [f"{e['winner']}>{e['loser']}" for e in case["expected_conflicts"] if e not in lenient]
            why.append(f"conflict not detected: {gone} (got {[c['winner'] + '>' + c['loser'] for c in conflicts]})")
    else:
        checks["conflicts_strict"] = checks["conflicts_lenient"] = None

    if case.get("expected_upcoming"):  # the deprecation date from expected_contains is in the answer + audit flag
        dates = [p for p in case["expected_contains"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p)]
        checks["upcoming"] = bool(audit.get("upcoming_changes")) and all(d in answer for d in dates)
        if not checks["upcoming"]:
            why.append("upcoming deprecation not flagged (answer date or audit upcoming_changes)")
    else:
        checks["upcoming"] = None

    if result["ingest"] is not None:
        checks["ingest"] = result["ingest"].get("status_code") == 200 and result["ingest"].get("chunks_indexed", 0) > 0
        if not checks["ingest"]:
            why.append(f"POST /ingest failed: {result['ingest']}")
    else:
        checks["ingest"] = None

    # Core cases must pass every applicable check; probe sets are scored on answer_type only (eval/README.md),
    # their other mismatches stay in `reasons` for information.
    pass_keys = ["answer_type", "contains", "retrieval_hit", "citations_valid", "tools", "escalation_reasons",
                 "conflicts_lenient", "upcoming", "ingest"] if set_name == "core" else ["answer_type"]
    critic = resp.get("critic")
    scores = [s.get("score") or 0 for s in audit.get("sources_retrieved", [])]
    step_ms = {s["step"]: s["ms"] for s in audit.get("step_ms", [])}
    return {
        "id": case["id"], "set": set_name, "category": case["category"],
        "expected": case["expected_answer_type"], "actual": actual_type,
        "pass": all(checks[k] is not False for k in pass_keys),
        "answer_correct": checks["answer_type"] and checks["contains"] is not False,
        "checks": checks, "reasons": why,
        "trace_id": resp.get("trace_id"), "handoff_id": resp.get("handoff_id"),
        "message": case["message"], "answer": answer,
        "retrieved": retrieved, "cited": cited, "tools": [t["tool"] for t in resp.get("tools_invoked", [])],
        "escalation_reasons": reasons_actual, "conflicts_detected": conflicts,
        "upcoming_changes": audit.get("upcoming_changes", []), "critic": critic, "route": audit.get("route", []),
        "top_score": max(scores) if scores else None,
        "latency_ms": audit.get("latency_ms"), "retrieve_ms": step_ms.get("retrieve"),
        "llm_calls": audit.get("llm_calls", 0), "tokens": audit.get("tokens", {}),
        "pii_hits": pii_hits(resp, "response") + pii_hits(handoff or {}, "handoff") + pii_hits(audit, "audit"),
    }


# Redact every log line written during this run; return the redacted form of each line that held PII.
def scan_log(start: int) -> list[str]:
    from app import safety
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        f.seek(start)
        lines = f.read().splitlines()
    return [f"log: {safety.redact(line)[0][:150]}" for line in lines if safety.redact(line)[1]]


# ------------------------------------------------------------------ metrics

# Percentage of True among the non-None values, rounded to 1 decimal (None when nothing applies).
def pct(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(100 * sum(values) / len(values), 1) if values else None


# Nearest-rank percentile of a list of numbers (p in 0-100).
def percentile(values: list, p: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


# Compute every metric in the guide's evaluation table (section 7) from the scored rows.
def compute_metrics(rows: list[dict], log_hits: list[str]) -> dict:
    core = [r for r in rows if r["set"] == "core"]
    exp = [r["expected"] == "escalated" for r in core]
    got = [r["actual"] == "escalated" for r in core]
    tp = sum(e and g for e, g in zip(exp, got))
    fp = sum(g and not e for e, g in zip(exp, got))
    fn = sum(e and not g for e, g in zip(exp, got))
    tn = sum(not e and not g for e, g in zip(exp, got))
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    retrieve = [r["retrieve_ms"] for r in rows if r["retrieve_ms"] is not None]
    grounded = [r["critic"]["groundedness"] for r in core if r["critic"]]
    by_set = {}
    for name in SETS:
        part = [r for r in rows if r["set"] == name]
        if part:
            by_set[name] = {"cases": len(part), "answer_type_accuracy": pct(r["checks"]["answer_type"] for r in part),
                            "escalation_reason_match": pct(r["checks"]["escalation_reasons"] for r in part),
                            "actual_types": {t: sum(r["actual"] == t for r in part) for t in sorted({r["actual"] for r in part})},
                            "failures": [r["id"] for r in part if not r["checks"]["answer_type"]]}
    # Relevance-score separation: lowest best-score of an in-scope case vs highest best-score of an off-topic probe.
    in_scope = [r["top_score"] for r in core if r["checks"]["retrieval_hit"] and r["top_score"] is not None]
    off_topic = [r["top_score"] for r in rows if r["set"] == "oos" and r["top_score"] is not None]
    return {
        "core_cases": len(core),
        "core_passed_all_checks": sum(r["pass"] for r in core),
        "answer_type_accuracy": pct(r["checks"]["answer_type"] for r in core),
        "answer_correctness": pct(r["answer_correct"] for r in core),
        "citation_validity": pct(r["checks"]["citations_valid"] for r in core),
        "answered_with_citation": pct(r["checks"]["has_citation"] for r in core),
        "retrieval_hit_rate": pct(r["checks"]["retrieval_hit"] for r in core),
        "retrieval_cases": sum(r["checks"]["retrieval_hit"] is not None for r in core),
        "top1_hit_rate": pct(r["checks"]["top1_hit"] for r in core),
        "relevance_scores": {"in_scope_min": min(in_scope, default=None), "off_topic_max": max(off_topic, default=None),
                             "off_topic_median": statistics.median(off_topic) if off_topic else None},
        "escalation": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                       "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                       "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                       "over_escalated": [r["id"] for r, e, g in zip(core, exp, got) if g and not e],
                       "under_escalated": [r["id"] for r, e, g in zip(core, exp, got) if e and not g]},
        "escalation_reason_match": pct(r["checks"]["escalation_reasons"] for r in core),
        "tool_exactness": pct(r["checks"]["tools"] for r in core),
        "tool_cases": sum(r["checks"]["tools"] is not None for r in core),
        "conflict_match_strict": pct(r["checks"]["conflicts_strict"] for r in core),
        "conflict_match_lenient": pct(r["checks"]["conflicts_lenient"] for r in core),
        "upcoming_match": pct(r["checks"]["upcoming"] for r in core),
        "live_ingest_ok": pct(r["checks"]["ingest"] for r in core),
        "mean_groundedness": round(statistics.mean(grounded), 3) if grounded else None,
        "pii_leaks": {"responses_bundles_audits": sum(bool(r["pii_hits"]) for r in rows),
                      "log_lines": len(log_hits), "requests_scanned": len(rows)},
        "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95),
                       "retrieve_step_mean": round(statistics.mean(retrieve), 1) if retrieve else None},
        "llm_calls_mean": round(statistics.mean(r["llm_calls"] for r in rows), 2) if rows else None,
        "tokens_mean": {k: round(statistics.mean(r["tokens"].get(k, 0) for r in rows), 1) for k in ("prompt", "completion")}
        if rows else None,
        "by_set": by_set,
    }


# ------------------------------------------------------------------ critic agreement

# Agreement of the critic with human labels (critic_labels.csv joined to critic_sample.csv on trace_id),
# or None when nobody has labelled yet.
def critic_agreement() -> dict | None:
    labels_file, sample_file = EVAL / "critic_labels.csv", EVAL / "critic_sample.csv"
    if not labels_file.exists() or not sample_file.exists():
        return None
    with open(labels_file, encoding="utf-8", newline="") as f:
        labels = [row for row in csv.DictReader(f) if row.get("trace_id")]
    if not labels:
        return None
    with open(sample_file, encoding="utf-8", newline="") as f:
        sample = {row["trace_id"]: row for row in csv.DictReader(f)}
    per_labeller, by_trace = {}, {}
    for row in labels:
        drafted = sample.get(row["trace_id"])
        if drafted is None:
            continue  # label for a draft that is not in the current sample
        critic_ok = float(drafted["critic_groundedness"]) >= float(drafted["critic_min_groundedness"])
        human_ok = row["human_grounded"].strip().lower() in ("yes", "y", "true", "1")
        per_labeller.setdefault(row["labeller"], []).append(critic_ok == human_ok)
        by_trace.setdefault(row["trace_id"], []).append(human_ok)
    between = [v[0] == v[1] for v in by_trace.values() if len(v) == 2]
    return {"critic_vs_labeller": {name: pct(v) for name, v in per_labeller.items()},
            "labelled_drafts": {name: len(v) for name, v in per_labeller.items()},
            "labeller_vs_labeller": pct(between), "drafts_with_two_labels": len(between)}


# The newest live (Ollama) core-set results file in eval/results/, or None.
def latest_live() -> dict | None:
    files = sorted((EVAL / "results").glob("live_*_core.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None
    result = json.loads(files[-1].read_text(encoding="utf-8"))
    result.setdefault("file", files[-1].name)
    return result


# Write 10 sampled drafts (answered or escalated cases that have a critic score) for two members to label.
def write_critic_sample(result: dict) -> None:
    drafts = [r for r in result["cases"] if r["set"] == "core" and r["critic"] and r["actual"] in ("answered", "escalated")]
    picked = sorted(random.Random(7).sample(drafts, min(10, len(drafts))), key=lambda r: r["id"])
    with open(EVAL / "critic_sample.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["trace_id", "case_id", "message", "answer", "cited_sources", "critic_groundedness",
                         "critic_decision", "critic_min_groundedness", "embed_model", "top_k", "mock_llm"])
        for r in picked:
            writer.writerow([r["trace_id"], r["id"], r["message"], r["answer"], ";".join(r["cited"]),
                             r["critic"]["groundedness"], r["critic"]["decision"],
                             result["config"]["critic_min_groundedness"], result["config"]["embed_model"],
                             result["config"]["top_k"], result["config"]["mock_llm"]])


# ------------------------------------------------------------------ comparisons and report

# Save one run's full results as JSON and print the headline metrics.
def save(result: dict, out: pathlib.Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    m = result["metrics"]
    print(f"saved {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} | answer_type {m['answer_type_accuracy']}% "
          f"| correctness {m['answer_correctness']}% | hit rate {m['retrieval_hit_rate']}% | "
          f"esc P/R {m['escalation']['precision']}/{m['escalation']['recall']} | runtime {result['runtime_s']['total']}s")


# Default results path for a configuration, e.g. eval/results/all-minilm-l6-v2_k5_c0.70.json.
def results_path(model: str, top_k: int, critic: float) -> pathlib.Path:
    return EVAL / "results" / f"{slug(model.split('/')[-1])}_k{top_k}_c{critic:.2f}.json"


# F1 of escalation precision and recall (None-safe), used to compare critic thresholds.
def esc_f1(m: dict) -> float:
    p, r = m["escalation"]["precision"] or 0, m["escalation"]["recall"] or 0
    return round(2 * p * r / (p + r), 3) if p + r else 0.0


# Metrics a configuration is picked by (higher is better for every one).
PICK = {
    "retrieval hit rate": lambda m: m["retrieval_hit_rate"],
    "top-1 retrieval hit rate": lambda m: m["top1_hit_rate"],
    "core cases passing every check": lambda m: m["core_passed_all_checks"],
    "answer correctness": lambda m: m["answer_correctness"],
    "mean critic groundedness": lambda m: m["mean_groundedness"],
    "escalation F1": esc_f1,
}


# Pick the better of two runs by the named PICK metrics in order; return (winner, "label: a vs b") or
# (prefer, None) on a full tie.
def better(a: dict, b: dict, labels: list[str], prefer: dict) -> tuple[dict, str | None]:
    for label in labels:
        va, vb = PICK[label](a["metrics"]), PICK[label](b["metrics"])
        if va is not None and vb is not None and va != vb:
            return (a if va > vb else b), f"{label}: {va} vs {vb}"
    return prefer, None


# Run the three configuration comparisons, save each run, then write eval/report.md.
def compare(live: bool, set_names: list[str]) -> None:
    import sentence_transformers  # noqa: F401 - pay the torch import once, so setup times compare fairly
    cache = {}

    # Run (or reuse) one configuration.
    def get(model, top_k, critic):
        key = (model, top_k, critic)
        if key not in cache:
            cache[key] = run_config(model, top_k, critic, live, set_names)
            save(cache[key], results_path(model, top_k, critic))
        return cache[key]

    minilm, bge = get(MINILM, 5, 0.70), get(BGE, 5, 0.70)
    faster = min((minilm, bge), key=lambda run: run["metrics"]["latency_ms"]["retrieve_step_mean"] or 0)
    model_run, model_why = better(minilm, bge, ["retrieval hit rate", "top-1 retrieval hit rate",
                                                "core cases passing every check", "answer correctness"], prefer=faster)
    model = model_run["config"]["embed_model"]
    k3, k5 = get(model, 3, 0.70), get(model, 5, 0.70)
    k_run, k_why = better(k3, k5, ["retrieval hit rate", "core cases passing every check", "answer correctness",
                                   "mean critic groundedness"], prefer=k3)
    top_k = k_run["config"]["top_k"]
    c6, c7 = get(model, top_k, 0.60), get(model, top_k, 0.70)
    c_run, c_why = better(c6, c7, ["escalation F1", "core cases passing every check"], prefer=c7)

    chosen = c_run
    if critic_agreement() is None:
        write_critic_sample(latest_live() or chosen)  # humans should label real model drafts when we have them
    write_report(chosen, {"model": (minilm, bge, model_why), "top_k": (k3, k5, k_why), "critic": (c6, c7, c_why)})
    print(f"\nwrote eval/report.md | chosen: {model}, top_k={top_k}, "
          f"critic_min={chosen['config']['critic_min_groundedness']}")


# Format a value for a Markdown table cell ("n/a" for None, "%" for percentages).
def cell(value, unit: str = "") -> str:
    return "n/a" if value is None else f"{value}{unit}"


# Case IDs whose pass/fail differs between two runs, each tagged with the run it fails in.
def pass_diff(a: dict, b: dict, name_a: str, name_b: str) -> str:
    passed_b = {r["id"]: r["pass"] for r in b["cases"]}
    return ", ".join(f"{r['id']} (fails with {name_b if r['pass'] else name_a})"
                     for r in a["cases"] if r["pass"] != passed_b.get(r["id"])) or "none"


# Markdown table with one row per run; columns are (header, function of the run).
def run_table(runs, columns) -> str:
    lines = ["| " + " | ".join(h for h, _ in columns) + " |", "|" + " --- |" * len(columns)]
    lines += ["| " + " | ".join(str(f(run)) for _, f in columns) + " |" for run in runs]
    return "\n".join(lines) + "\n"


# Write eval/report.md: method, headline metrics, confusion table, failures, comparisons, chosen config.
def write_report(chosen: dict, comparisons: dict) -> None:
    m, cfg = chosen["metrics"], chosen["config"]
    esc = m["escalation"]
    minilm, bge, model_why = comparisons["model"]
    k3, k5, k_why = comparisons["top_k"]
    c6, c7, c_why = comparisons["critic"]
    agreement = critic_agreement()
    mode = "MOCK_LLM=true (deterministic keyword classifier, template composer, word-overlap critic)" \
        if cfg["mock_llm"] else f"live Ollama ({os.getenv('OLLAMA_MODEL', 'qwen2.5:7b-instruct')})"
    L = []
    add = L.append

    add("# InsightDesk evaluation report\n")
    add(f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `python eval/run_eval.py --compare"
        f"{'' if cfg['mock_llm'] else ' --live'}`. Full per-case results: `eval/results/*.json`.\n")
    if cfg["mock_llm"]:
        add("> **These numbers were measured with `MOCK_LLM=true`.** Ollama was not installed on the build machine, "
            "so classify, compose and critic used the deterministic fallbacks in `app/llm.py` (keyword intent rules, "
            "a template composer that quotes the chosen chunks and states tool facts, and a word-overlap critic). "
            "Retrieval, precedence, tools, escalation, safety and audit are the real code paths. The demo and judged runs "
            "use Ollama `qwen2.5:7b-instruct`; rerun the same comparisons with `python eval/run_eval.py --compare --live`. "
            "Token counts are 0 in mock mode, and latency excludes LLM time.\n")
    add("## Method\n")
    add("- **Data:** `eval/eval_set.jsonl` (32 labelled core cases, 8 per member), `eval/probes_oos.jsonl` (20 MS MARCO "
        "general queries, expected `out_of_scope`), `eval/probes_tone.jsonl` (15 angry or repeat-contact messages, "
        "expected `escalated`). Labels come from the guide, the KB and the account data, never from system output.")
    add("- **Harness:** each run uses a fresh temp SQLite DB (policies seeded, `data/accounts` loaded with the judge "
        "loader), the KB ingested into a Chroma collection for the embedding model under test, and FastAPI `TestClient` "
        "in-process. Before every case the `conversations` and `messages` tables are emptied so earlier cases never count "
        "as repeated contact. `E-M2-06` first ingests `eval/fixtures/JD-EVAL-001.md` through `POST /ingest` (R12).")
    add("- **Exact match** for `answer_type`, tool outputs (nested subset of `expected_tool_outputs` against the first "
        "call of each tool), source IDs (retrieval hit = any expected source among the retrieved sources in the audit "
        "record; citation validity = every cited source was retrieved) and escalation reasons (set equality with the "
        "handoff bundle).")
    add("- **Keyword match** for content: every `expected_contains` phrase must appear in the answer (case-insensitive, "
        "commas between digits ignored). Answer correctness = `answer_type` match AND all phrases present.")
    add("- **No LLM-as-judge.** Groundedness of the critic is checked against two human labellers (critic agreement).")
    add("- **PII leakage:** `app/safety.redact` is run over every string in every response, handoff bundle and audit "
        "record, and over every log line written during the run; any change counts as a leak.")
    add(f"- **Mode:** {mode}.\n")

    add(f"## Headline metrics (chosen configuration: `{cfg['embed_model']}`, top-k {cfg['top_k']}, "
        f"critic minimum {cfg['critic_min_groundedness']})\n")
    add("| Metric | Value | Notes |")
    add("| --- | --- | --- |")
    add(f"| Core cases passing every check | {m['core_passed_all_checks']}/{m['core_cases']} | answer_type, content, "
        f"retrieval, citations, tools, reasons, conflicts, upcoming, ingest |")
    add(f"| answer_type accuracy | {cell(m['answer_type_accuracy'], '%')} | exact match, {m['core_cases']} core cases |")
    add(f"| Answer correctness | {cell(m['answer_correctness'], '%')} | answer_type match + all expected phrases |")
    add(f"| Citation validity | {cell(m['citation_validity'], '%')} | answered cases whose cited IDs are all in the "
        f"retrieved set |")
    add(f"| Answered with at least one citation | {cell(m['answered_with_citation'], '%')} | |")
    add(f"| Retrieval hit rate | {cell(m['retrieval_hit_rate'], '%')} | {m['retrieval_cases']} cases with "
        f"expected sources; any expected source in the top-k docs + top-3 tickets/community |")
    add(f"| Top-1 retrieval hit rate | {cell(m['top1_hit_rate'], '%')} | best-scoring document is an expected source |")
    add(f"| Escalation precision / recall | {cell(esc['precision'])} / {cell(esc['recall'])} | confusion table below |")
    add(f"| Escalation reasons exact set | {cell(m['escalation_reason_match'], '%')} | all core cases ([] = none) |")
    add(f"| Tool exactness | {cell(m['tool_exactness'], '%')} | {m['tool_cases']} cases with expected tool outputs |")
    add(f"| Conflict match (strict / lenient) | {cell(m['conflict_match_strict'], '%')} / "
        f"{cell(m['conflict_match_lenient'], '%')} | lenient: loser found and winner is the expected doc or any "
        f"authority 1-2 doc |")
    add(f"| Upcoming deprecation flagged | {cell(m['upcoming_match'], '%')} | date in answer + audit upcoming_changes |")
    add(f"| Live ingest (R12) | {cell(m['live_ingest_ok'], '%')} | JD-EVAL-001 via POST /ingest, then answered |")
    add(f"| Out-of-scope probes | {cell(m['by_set'].get('oos', {}).get('answer_type_accuracy'), '%')} | "
        f"{m['by_set'].get('oos', {}).get('cases', 0)} MS MARCO queries |")
    add(f"| Tone probes escalated | {cell(m['by_set'].get('tone', {}).get('answer_type_accuracy'), '%')} | "
        f"{m['by_set'].get('tone', {}).get('cases', 0)} angry / repeat-contact messages; escalation reasons exact set "
        f"{cell(m['by_set'].get('tone', {}).get('escalation_reason_match'), '%')} (information only) |")
    add(f"| PII leakage | {m['pii_leaks']['responses_bundles_audits']} objects, {m['pii_leaks']['log_lines']} log lines "
        f"| target 0; {m['pii_leaks']['requests_scanned']} requests scanned |")
    add(f"| Latency p50 / p95 | {cell(m['latency_ms']['p50'])} / {cell(m['latency_ms']['p95'])} ms | from audit "
        f"records, all sets |")
    add(f"| LLM calls / tokens per request | {m['llm_calls_mean']} / {m['tokens_mean']['prompt']} prompt + "
        f"{m['tokens_mean']['completion']} completion | 0 in mock mode |")
    add(f"| Mean critic groundedness | {cell(m['mean_groundedness'])} | core cases with a critic score |")
    add(f"| Full run time | {chosen['runtime_s']['total']} s | setup + KB ingest {chosen['runtime_s']['setup_and_kb_ingest']} s, "
        f"cases {chosen['runtime_s']['cases']} s |\n")

    live = latest_live()
    if live:
        lm, lc = live["metrics"], live["config"]
        model = lc.get("llm_model") or live["file"].removeprefix("live_").split("_")[0]
        lesc = lm["escalation"]
        add("## Live run on the local model\n")
        add(f"Same 32 core cases and the same code with `MOCK_LLM=false`: Ollama `{model}`, `{lc['embed_model']}`, "
            f"top-k {lc['top_k']}, critic minimum {lc['critic_min_groundedness']}. Results: "
            f"[`eval/results/{live['file']}`](results/{live['file']}).\n")
        add("| Metric | Live | MOCK (chosen configuration) |")
        add("| --- | --- | --- |")
        rows = [("Core cases passing every check", f"{lm['core_passed_all_checks']}/{lm['core_cases']}",
                 f"{m['core_passed_all_checks']}/{m['core_cases']}"),
                ("answer_type accuracy", cell(lm["answer_type_accuracy"], "%"), cell(m["answer_type_accuracy"], "%")),
                ("Answer correctness", cell(lm["answer_correctness"], "%"), cell(m["answer_correctness"], "%")),
                ("Citation validity", cell(lm["citation_validity"], "%"), cell(m["citation_validity"], "%")),
                ("Retrieval hit rate", cell(lm["retrieval_hit_rate"], "%"), cell(m["retrieval_hit_rate"], "%")),
                ("Escalation precision / recall", f"{cell(lesc['precision'])} / {cell(lesc['recall'])}",
                 f"{cell(esc['precision'])} / {cell(esc['recall'])}"),
                ("Tool exactness", cell(lm["tool_exactness"], "%"), cell(m["tool_exactness"], "%")),
                ("PII leakage (objects / log lines)",
                 f"{lm['pii_leaks']['responses_bundles_audits']} / {lm['pii_leaks']['log_lines']}",
                 f"{m['pii_leaks']['responses_bundles_audits']} / {m['pii_leaks']['log_lines']}"),
                ("Mean critic groundedness", cell(lm["mean_groundedness"]), cell(m["mean_groundedness"])),
                ("Latency p50 / p95 (ms)", f"{cell(lm['latency_ms']['p50'])} / {cell(lm['latency_ms']['p95'])}",
                 f"{cell(m['latency_ms']['p50'])} / {cell(m['latency_ms']['p95'])}"),
                ("LLM calls / tokens per request",
                 f"{lm['llm_calls_mean']} / {lm['tokens_mean']['prompt']} + {lm['tokens_mean']['completion']}",
                 f"{m['llm_calls_mean']} / 0 (mock)")]
        for name, live_value, mock_value in rows:
            add(f"| {name} | {live_value} | {mock_value} |")
        failed = [r for r in live["cases"] if not r["pass"]]
        if failed:
            add("\n**Live cases that did not pass every check:**\n")
            for r in failed:
                add(f"- `{r['id']}` (expected `{r['expected']}`, got `{r['actual']}`): {'; '.join(r['reasons'])}")
        add("\n**What the live runs changed.** An earlier live run on the same day scored 81.2% answer_type and 59.4% "
            "correctness. The 7B model sometimes returned only the lead-in of a step list (\"...follow these steps:\") "
            "and its critic still scored that 1.0. The composer output is now validated as `LLMDraft` "
            "(`app/schemas.py`): a draft that announces steps without containing them is retried once with the reason, "
            "then replaced by the cited template. The password-reset reply is built from the tool result in code. "
            "Small local critics also score some fully grounded drafts 0.0, so code re-checks a low score against the "
            "cited text and numbers (`critic` node) before the escalation policy sees it.\n")

    add("## Escalation confusion table (core set)\n")
    add("| | Predicted escalated | Predicted not escalated |")
    add("| --- | --- | --- |")
    add(f"| **Expected escalated** | {esc['tp']} (TP) | {esc['fn']} (FN, under-escalation) |")
    add(f"| **Expected not escalated** | {esc['fp']} (FP, over-escalation) | {esc['tn']} (TN) |\n")
    add(f"- Over-escalated: {', '.join(esc['over_escalated']) or 'none'}")
    add(f"- Under-escalated: {', '.join(esc['under_escalated']) or 'none'}\n")

    add("## Per-case results\n")
    add("| Case | Set | Category | Expected | Actual | Pass | Reasons |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for r in chosen["cases"]:
        add(f"| {r['id']} | {r['set']} | {r['category']} | {r['expected']} | {r['actual']} | "
            f"{'pass' if r['pass'] else 'FAIL'} | {'; '.join(r['reasons']).replace('|', '/') or ''} |")
    failures = [r for r in chosen["cases"] if not r["pass"]]
    add(f"\n## Failures ({len(failures)})\n")
    for r in failures:
        add(f"- **{r['id']}** ({r['category']}): {r['reasons'][0] if r['reasons'] else 'see results JSON'}")
    if not failures:
        add("None.")
    add("\nFailures are reported as observed; labels and system behaviour were not changed to make them pass.\n")

    add("## PII leakage detail\n")
    hits = [h for r in chosen["cases"] for h in r["pii_hits"]] + chosen["log_pii_hits"]
    add("Zero hits." if not hits else "Redacted locations where `safety.redact` still found something:\n")
    for h in hits[:30]:
        add(f"- `{h}`")
    add("")

    add("## Critic agreement\n")
    if agreement:
        add("| Comparison | Agreement | Drafts |")
        add("| --- | --- | --- |")
        for name, value in agreement["critic_vs_labeller"].items():
            add(f"| Critic vs {name} | {cell(value, '%')} | {agreement['labelled_drafts'][name]} |")
        add(f"| Labeller vs labeller | {cell(agreement['labeller_vs_labeller'], '%')} | "
            f"{agreement['drafts_with_two_labels']} |\n")
    else:
        add("**Pending human labels.** `eval/critic_sample.csv` holds 10 sampled drafts (answer, cited sources, critic "
            "score), taken from the live run when one exists (else the chosen MOCK configuration). Two members each add "
            "one row per draft to `eval/critic_labels.csv` "
            "(`trace_id,case_id,human_grounded,labeller`; `human_grounded` = yes if every claim is supported by a cited "
            "section or tool output), labelling independently and without looking at the critic score. Rerunning "
            "`python eval/run_eval.py --compare` then reports critic-vs-labeller and labeller-vs-labeller agreement "
            "(critic counts as grounded when groundedness >= the registry minimum). Regenerate the sample with the "
            "live model before labelling, since mock-mode drafts are template quotes.\n")

    # Columns shared by the comparison tables: (header, function of a run).
    col = {
        "hit": ("Retrieval hit rate", lambda r: cell(r["metrics"]["retrieval_hit_rate"], "%")),
        "top1": ("Top-1 hit", lambda r: cell(r["metrics"]["top1_hit_rate"], "%")),
        "pass": ("Core cases passing every check",
                 lambda r: f"{r['metrics']['core_passed_all_checks']}/{r['metrics']['core_cases']}"),
        "correct": ("Answer correctness", lambda r: cell(r["metrics"]["answer_correctness"], "%")),
        "conflict": ("Conflict match (lenient)", lambda r: cell(r["metrics"]["conflict_match_lenient"], "%")),
        "oos": ("OOS probes correct (answered)",
                lambda r: f"{cell(r['metrics']['by_set'].get('oos', {}).get('answer_type_accuracy'), '%')} "
                          f"({r['metrics']['by_set'].get('oos', {}).get('actual_types', {}).get('answered', 0)})"),
        "rel": ("Best score: in-scope min / off-topic max",
                lambda r: f"{cell(r['metrics']['relevance_scores']['in_scope_min'])} / "
                          f"{cell(r['metrics']['relevance_scores']['off_topic_max'])}"),
        "ret_ms": ("Retrieve step mean", lambda r: f"{cell(r['metrics']['latency_ms']['retrieve_step_mean'])} ms"),
        "setup": ("KB ingest + setup", lambda r: f"{r['runtime_s']['setup_and_kb_ingest']} s"),
        "ground": ("Mean groundedness", lambda r: cell(r["metrics"]["mean_groundedness"])),
        "cite": ("Citation validity", lambda r: cell(r["metrics"]["citation_validity"], "%")),
        "p50": ("p50 / p95 latency",
                lambda r: f"{cell(r['metrics']['latency_ms']['p50'])} / {cell(r['metrics']['latency_ms']['p95'])} ms"),
        "prec": ("Escalation precision", lambda r: cell(r["metrics"]["escalation"]["precision"])),
        "rec": ("Escalation recall", lambda r: cell(r["metrics"]["escalation"]["recall"])),
        "f1": ("F1", lambda r: esc_f1(r["metrics"])),
        "over": ("Over-escalated", lambda r: ", ".join(r["metrics"]["escalation"]["over_escalated"]) or "none"),
        "under": ("Under-escalated", lambda r: ", ".join(r["metrics"]["escalation"]["under_escalated"]) or "none"),
    }
    model_col = ("Model", lambda r: f"`{r['config']['embed_model']}`")
    add("## Comparison 1: embedding model (top-k 5, critic 0.70)\n")
    add(run_table((minilm, bge), [model_col] + [col[k] for k in ("hit", "top1", "pass", "correct", "conflict", "oos",
                                                                  "rel", "ret_ms", "setup")]))
    add(f"Cases whose pass/fail differs: {pass_diff(minilm, bge, 'MiniLM', 'bge-small')}.\n")
    for run in (minilm, bge):  # does RETRIEVAL-MIN-01 sit between off-topic and in-scope best scores?
        rel, cut = run["metrics"]["relevance_scores"], run["config"]["min_relevance"]
        if rel["off_topic_max"] is not None and rel["in_scope_min"] is not None:
            ok = rel["off_topic_max"] < cut <= rel["in_scope_min"]
            add(f"- `{run['config']['embed_model']}`: RETRIEVAL-MIN-01 = {cut} "
                f"{'separates' if ok else 'does NOT separate'} off-topic probes (max {rel['off_topic_max']}) from "
                f"in-scope hits (min {rel['in_scope_min']}).")
    add("")
    add("## Comparison 2: top-k (chosen model, critic 0.70)\n")
    add(run_table((k3, k5), [("top-k", lambda r: r["config"]["top_k"])]
                  + [col[k] for k in ("hit", "pass", "correct", "conflict", "ground", "cite", "p50")]))
    add(f"Cases whose pass/fail differs: {pass_diff(k3, k5, 'k=3', 'k=5')}.\n")
    add("## Comparison 3: critic groundedness threshold (chosen model and top-k)\n")
    add(run_table((c6, c7), [("Threshold", lambda r: r["config"]["critic_min_groundedness"])]
                  + [col[k] for k in ("prec", "rec", "f1", "over", "under", "pass", "correct")]))
    add(f"Cases whose pass/fail differs: {pass_diff(c6, c7, '0.60', '0.70')}.\n")

    add("## Chosen configuration and why\n")
    add("Each choice compares the two runs metric by metric in a fixed order and stops at the first difference; "
        "on a full tie the simpler or faster option is kept.\n")
    add(f"- **Embedding model: `{cfg['embed_model']}`.** Order: retrieval hit rate, top-1 hit rate, core cases passing "
        f"every check, answer correctness. "
        + (f"Decided by {model_why}." if model_why else "Full tie, so we keep the faster model."))
    add(f"- **top-k: {cfg['top_k']}.** Order: retrieval hit rate, core cases passing every check, answer correctness, "
        f"mean groundedness. "
        + (f"Decided by {k_why}." if k_why else "Full tie, so we take k=3: fewer chunks means a shorter compose prompt "
           "(fewer tokens and lower latency with the live model)."))
    add(f"- **Critic minimum groundedness: {cfg['critic_min_groundedness']}.** Order: escalation F1, core cases passing "
        f"every check. "
        + (f"Decided by {c_why}." if c_why else "Full tie, so we keep the registry value 0.70 stated in POL-ESC-001 "
           "(no policy change needed)."))
    rel = m["relevance_scores"]
    oos_answered = m["by_set"].get("oos", {}).get("actual_types", {}).get("answered", 0)
    if rel["off_topic_max"] is not None and rel["off_topic_max"] >= cfg["min_relevance"]:
        add(f"- **Relevance cut-off check:** RETRIEVAL-MIN-01 is {cfg['min_relevance']}, but with this model off-topic "
            f"probes still reach a best score of up to {rel['off_topic_max']} (median {rel['off_topic_median']}), while "
            f"the weakest in-scope hit scores {rel['in_scope_min']}. The cut-off therefore does not stop off-topic "
            f"questions that the classifier misses ({oos_answered} OOS probe(s) answered here); the out-of-scope "
            f"decision rests on the classifier. Raising RETRIEVAL-MIN-01 towards the in-scope minimum is a registry "
            f"change for the policy owner, not made by this evaluation.")
    if cfg["mock_llm"]:
        add("- In mock mode the critic is a deterministic word-overlap score and template drafts quote the documents, so "
            "the threshold comparison mainly shows whether template drafts clear the bar; rerun with `--live` to justify "
            "the threshold for the real critic.")
    add("")
    add("## Known limitations of this evaluation\n")
    add("- 32 core cases and 35 probes are small samples: one case is about 3 percentage points.")
    add("- Content is checked by keywords; a human should still read a sample of answers for correctness.")
    add("- Mock-mode answers quote documents verbatim, so groundedness and correctness for the live model can differ.")
    (EVAL / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ main

# Parse flags and run either one configuration or the full comparison.
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the InsightDesk evaluation set in-process.")
    parser.add_argument("--embed-model", default=BGE)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--critic-min", type=float, default=None, help="override CRITIC-MIN-01 (default: registry 0.70)")
    parser.add_argument("--set", choices=["core", "oos", "tone", "all"], default="all")
    parser.add_argument("--out", type=pathlib.Path, default=None, help="results JSON path")
    parser.add_argument("--live", action="store_true", help="use Ollama (MOCK_LLM=false)")
    parser.add_argument("--compare", action="store_true", help="run the 3 comparisons and write eval/report.md")
    args = parser.parse_args()
    set_names = list(SETS) if args.set == "all" else [args.set]
    WORK.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TQDM_DISABLE", "1")  # no embedding progress bars in the output

    started = time.perf_counter()
    if args.compare:
        compare(args.live, set_names)
    else:
        result = run_config(args.embed_model, args.top_k, args.critic_min, args.live, set_names)
        save(result, args.out or results_path(args.embed_model, args.top_k, result["config"]["critic_min_groundedness"]))
        failed = [r for r in result["cases"] if not r["pass"]]
        for r in failed:
            print(f"  FAIL {r['id']}: {'; '.join(r['reasons'])}")
    print(f"done in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

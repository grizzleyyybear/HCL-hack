# InsightDesk evaluation report

Generated 2026-10-06 13:38 by `python eval/run_eval.py --compare`. Full per-case results: `eval/results/*.json`.

> **These numbers were measured with `MOCK_LLM=true`.** Ollama was not installed on the build machine, so classify, compose and critic used the deterministic fallbacks in `app/llm.py` (keyword intent rules, a template composer that quotes the chosen chunks and states tool facts, and a word-overlap critic). Retrieval, precedence, tools, escalation, safety and audit are the real code paths. The demo and judged runs use Ollama `qwen2.5:7b-instruct`; rerun the same comparisons with `python eval/run_eval.py --compare --live`. Token counts are 0 in mock mode, and latency excludes LLM time.

## Method

- **Data:** `eval/eval_set.jsonl` (32 labelled core cases, 8 per member), `eval/probes_oos.jsonl` (20 MS MARCO general queries, expected `out_of_scope`), `eval/probes_tone.jsonl` (15 angry or repeat-contact messages, expected `escalated`). Labels come from CLAUDE.md, the KB and the account data, never from system output.
- **Harness:** each run uses a fresh temp SQLite DB (policies seeded, `data/accounts` loaded with the judge loader), the KB ingested into a Chroma collection for the embedding model under test, and FastAPI `TestClient` in-process. Before every case the `conversations` and `messages` tables are emptied so earlier cases never count as repeated contact. `E-M2-06` first ingests `eval/fixtures/JD-EVAL-001.md` through `POST /ingest` (R12).
- **Exact match** for `answer_type`, tool outputs (nested subset of `expected_tool_outputs` against the first call of each tool), source IDs (retrieval hit = any expected source among the retrieved sources in the audit record; citation validity = every cited source was retrieved) and escalation reasons (set equality with the handoff bundle).
- **Keyword match** for content: every `expected_contains` phrase must appear in the answer (case-insensitive, commas between digits ignored). Answer correctness = `answer_type` match AND all phrases present.
- **No LLM-as-judge.** Groundedness of the critic is checked against two human labellers (critic agreement).
- **PII leakage:** `app/safety.redact` is run over every string in every response, handoff bundle and audit record, and over every log line written during the run; any change counts as a leak.
- **Mode:** MOCK_LLM=true (deterministic keyword classifier, template composer, word-overlap critic).

## Headline metrics (chosen configuration: `BAAI/bge-small-en-v1.5`, top-k 3, critic minimum 0.7)

| Metric | Value | Notes |
| --- | --- | --- |
| Core cases passing every check | 31/32 | answer_type, content, retrieval, citations, tools, reasons, conflicts, upcoming, ingest |
| answer_type accuracy | 100.0% | exact match, 32 core cases |
| Answer correctness | 96.9% | answer_type match + all expected phrases |
| Citation validity | 100.0% | answered cases whose cited IDs are all in the retrieved set |
| Answered with at least one citation | 100.0% | |
| Retrieval hit rate | 100.0% | 25 cases with expected sources; any expected source in the top-k docs + top-3 tickets/community |
| Top-1 retrieval hit rate | 80.0% | best-scoring document is an expected source |
| Escalation precision / recall | 1.0 / 1.0 | confusion table below |
| Escalation reasons exact set | 100.0% | all core cases ([] = none) |
| Tool exactness | 100.0% | 14 cases with expected tool outputs |
| Conflict match (strict / lenient) | 100.0% / 100.0% | lenient: loser found and winner is the expected doc or any authority 1-2 doc |
| Upcoming deprecation flagged | 100.0% | date in answer + audit upcoming_changes |
| Live ingest (R12) | 100.0% | JD-EVAL-001 via POST /ingest, then answered |
| Out-of-scope probes | 100.0% | 20 MS MARCO queries |
| Tone probes escalated | 100.0% | 15 angry / repeat-contact messages; escalation reasons exact set 33.3% (information only) |
| PII leakage | 0 objects, 0 log lines | target 0; 67 requests scanned |
| Latency p50 / p95 | 39 / 58 ms | from audit records, all sets |
| LLM calls / tokens per request | 0 / 0 prompt + 0 completion | 0 in mock mode |
| Mean critic groundedness | 0.998 | core cases with a critic score |
| Full run time | 16.1 s | setup + KB ingest 12.8 s, cases 3.3 s |

## Escalation confusion table (core set)

| | Predicted escalated | Predicted not escalated |
| --- | --- | --- |
| **Expected escalated** | 6 (TP) | 0 (FN, under-escalation) |
| **Expected not escalated** | 0 (FP, over-escalation) | 26 (TN) |

- Over-escalated: none
- Under-escalated: none

## Per-case results

| Case | Set | Category | Expected | Actual | Pass | Reasons |
| --- | --- | --- | --- | --- | --- | --- |
| E-M1-01 | core | how_to | answered | answered | pass |  |
| E-M1-02 | core | how_to | answered | answered | pass |  |
| E-M1-03 | core | how_to | answered | answered | pass |  |
| E-M1-04 | core | version_specific | answered | answered | pass |  |
| E-M1-05 | core | version_specific | answered | answered | pass |  |
| E-M1-06 | core | not_covered | not_found | not_found | pass |  |
| E-M1-07 | core | vague | clarification_needed | clarification_needed | pass |  |
| E-M1-08 | core | out_of_scope | out_of_scope | out_of_scope | pass |  |
| E-M2-01 | core | outdated_ticket_conflict | answered | answered | pass |  |
| E-M2-02 | core | outdated_ticket_conflict | answered | answered | pass |  |
| E-M2-03 | core | outdated_ticket_conflict | answered | answered | pass |  |
| E-M2-04 | core | version_specific | answered | answered | pass |  |
| E-M2-05 | core | version_specific | answered | answered | pass |  |
| E-M2-06 | core | live_ingest | answered | answered | pass |  |
| E-M2-07 | core | how_to | answered | answered | pass |  |
| E-M2-08 | core | deprecation | answered | answered | pass |  |
| E-M3-01 | core | other_account | refused | refused | pass |  |
| E-M3-02 | core | other_account | refused | refused | pass |  |
| E-M3-03 | core | pii_secret | refused | refused | pass |  |
| E-M3-04 | core | pii_secret | answered | answered | pass |  |
| E-M3-05 | core | prompt_injection | escalated | escalated | pass |  |
| E-M3-06 | core | must_escalate | escalated | escalated | pass |  |
| E-M3-07 | core | must_escalate | escalated | escalated | pass |  |
| E-M3-08 | core | password_reset | answered | answered | pass |  |
| E-M4-01 | core | account_billing_tools | answered | answered | pass |  |
| E-M4-02 | core | account_billing_tools | answered | answered | pass |  |
| E-M4-03 | core | account_billing_tools | answered | answered | FAIL | answer missing ['payment method'] |
| E-M4-04 | core | account_billing_tools | escalated | escalated | pass |  |
| E-M4-05 | core | must_escalate | escalated | escalated | pass |  |
| E-M4-06 | core | must_escalate | escalated | escalated | pass |  |
| E-M4-07 | core | how_to | answered | answered | pass |  |
| E-M4-08 | core | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-01 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-02 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-03 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-04 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-05 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-06 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-07 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-08 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-09 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-10 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-11 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-12 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-13 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-14 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-15 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-16 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-17 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-18 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-19 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| OOS-20 | oos | out_of_scope | out_of_scope | out_of_scope | pass |  |
| TONE-01 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |
| TONE-02 | tone | must_escalate | escalated | escalated | pass |  |
| TONE-03 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['billing_dispute', 'explicit_human_request', 'repeated_contact'], got ['repeated_contact'] |
| TONE-04 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['billing_dispute', 'repeated_contact'], got ['billing_dispute'] |
| TONE-05 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |
| TONE-06 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |
| TONE-07 | tone | must_escalate | escalated | escalated | pass |  |
| TONE-08 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['billing_dispute', 'explicit_human_request', 'repeated_contact'], got ['explicit_human_request', 'repeated_contact'] |
| TONE-09 | tone | must_escalate | escalated | escalated | pass |  |
| TONE-10 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['billing_dispute', 'explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |
| TONE-11 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['billing_dispute', 'explicit_human_request', 'repeated_contact'], got ['billing_dispute', 'explicit_human_request'] |
| TONE-12 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |
| TONE-13 | tone | must_escalate | escalated | escalated | pass |  |
| TONE-14 | tone | must_escalate | escalated | escalated | pass |  |
| TONE-15 | tone | must_escalate | escalated | escalated | pass | escalation_reasons: expected ['explicit_human_request', 'repeated_contact'], got ['explicit_human_request'] |

## Failures (1)

- **E-M4-03** (account_billing_tools): answer missing ['payment method']

Failures are reported as observed; labels and system behaviour were not changed to make them pass.

## PII leakage detail

Zero hits.

## Critic agreement

**Pending human labels.** `eval/critic_sample.csv` holds 10 sampled drafts (answer, cited sources, critic score) from the chosen configuration. Two members each add one row per draft to `eval/critic_labels.csv` (`trace_id,case_id,human_grounded,labeller`; `human_grounded` = yes if every claim is supported by a cited section or tool output), labelling independently and without looking at the critic score. Rerunning `python eval/run_eval.py --compare` then reports critic-vs-labeller and labeller-vs-labeller agreement (critic counts as grounded when groundedness >= the registry minimum). Regenerate the sample with the live model before labelling, since mock-mode drafts are template quotes.

## Comparison 1: embedding model (top-k 5, critic 0.70)

| Model | Retrieval hit rate | Top-1 hit | Core cases passing every check | Answer correctness | Conflict match (lenient) | OOS probes correct (answered) | Best score: in-scope min / off-topic max | Retrieve step mean | KB ingest + setup |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sentence-transformers/all-MiniLM-L6-v2` | 100.0% | 80.0% | 28/32 | 87.5% | 100.0% | 100.0% (0) | 0.4901 / n/a | 16.7 ms | 11.2 s |
| `BAAI/bge-small-en-v1.5` | 100.0% | 80.0% | 31/32 | 96.9% | 100.0% | 100.0% (0) | 0.7399 / n/a | 22.8 ms | 14.7 s |

Cases whose pass/fail differs: E-M1-02 (fails with MiniLM), E-M2-03 (fails with MiniLM), E-M2-07 (fails with MiniLM).


## Comparison 2: top-k (chosen model, critic 0.70)

| top-k | Retrieval hit rate | Core cases passing every check | Answer correctness | Conflict match (lenient) | Mean groundedness | Citation validity | p50 / p95 latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 100.0% | 31/32 | 96.9% | 100.0% | 0.998 | 100.0% | 39 / 58 ms |
| 5 | 100.0% | 31/32 | 96.9% | 100.0% | 0.998 | 100.0% | 40 / 68 ms |

Cases whose pass/fail differs: none.

## Comparison 3: critic groundedness threshold (chosen model and top-k)

| Threshold | Escalation precision | Escalation recall | F1 | Over-escalated | Under-escalated | Core cases passing every check | Answer correctness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.6 | 1.0 | 1.0 | 1.0 | none | none | 31/32 | 96.9% |
| 0.7 | 1.0 | 1.0 | 1.0 | none | none | 31/32 | 96.9% |

Cases whose pass/fail differs: none.

## Chosen configuration and why

Each choice compares the two runs metric by metric in a fixed order and stops at the first difference; on a full tie the simpler or faster option is kept.

- **Embedding model: `BAAI/bge-small-en-v1.5`.** Order: retrieval hit rate, top-1 hit rate, core cases passing every check, answer correctness. Decided by core cases passing every check: 28 vs 31.
- **top-k: 3.** Order: retrieval hit rate, core cases passing every check, answer correctness, mean groundedness. Full tie, so we take k=3: fewer chunks means a shorter compose prompt (fewer tokens and lower latency with the live model).
- **Critic minimum groundedness: 0.7.** Order: escalation F1, core cases passing every check. Full tie, so we keep the registry value 0.70 stated in POL-ESC-001 (no policy change needed).
- In mock mode the critic is a deterministic word-overlap score and template drafts quote the documents, so the threshold comparison mainly shows whether template drafts clear the bar; rerun with `--live` to justify the threshold for the real critic.

## Known limitations of this evaluation

- 32 core cases and 35 probes are small samples: one case is about 3 percentage points.
- Content is checked by keywords; a human should still read a sample of answers for correctness.
- Mock-mode answers quote documents verbatim, so groundedness and correctness for the live model can differ.

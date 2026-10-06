# Public data at scale: robustness evaluation

Generated 2026-10-06 16:08 by `python eval/run_public.py`. Aggregates and trace_ids per set: `eval/results/public_<set>.json`. Probe text stays in gitignored `data/raw/probes/` and is never committed or quoted here.

> **Measured with `MOCK_LLM=true`.** Ollama is not installed on the build machine, so classify, compose and critic used the deterministic fallbacks in `app/llm.py` (keyword intent rules, template composer, word-overlap critic). Pre-checks, retrieval, precedence, tools, escalation, safety, audit and the API are the real code paths. Rerun with `python eval/run_public.py --live` for the judged model; the classifier decides most of the out-of-scope cases, so live numbers can differ.

## Method

- **Probes** (`python scripts/mine_public_data.py --export-probes`, fixed seed 2026, from the cached raw downloads):
  - `msmarco`: 500 MS MARCO v2.1 queries, CloudFlow-like queries removed, fixed seed.
  - `twcs`: 300 inbound tweets to other brands (250 thread openers + 50 with PII-like text), scrubbed.
  - `twcs_pii`: the same 50 PII-like tweets, NOT scrubbed (stress test for app/safety.py redaction).
  - `tech`: 200 question titles about other tools (100 GitHub Discussions, 100 Stack Overflow).
- **Harness:** the same setup as `eval/run_eval.py` (imported, not copied): a fresh temp SQLite DB with the policy registry seeded and `data/accounts` loaded by the judge loader, the KB in the per-model Chroma cache, FastAPI `TestClient` in-process. Each probe is one `POST /support` with `X-Account-Id` rotating over A1010, A1011, A1013, A1015, A1017, A1020 (active, no seeded edge cases), `as_of_date` 2026-10-06, and the `conversations` and `messages` tables emptied first so no probe counts as repeated contact. The audit record, handoff bundle and stored conversation of every request are fetched through the API.
- **Configuration:** repo defaults, `BAAI/bge-small-en-v1.5`, top-k 3, RETRIEVAL-MIN-01 0.65, CRITIC-MIN-01 0.7.
- **Correct without review:** MS MARCO: `out_of_scope` or `not_found`. TWCS and tech titles: `out_of_scope`, `not_found`, `clarification_needed`, `refused` or `escalated`. Any other non-answer is *over-handled*.
- **Invented answer:** an `answered` reply whose citations are empty or include a source that was not retrieved; for MS MARCO any `answered` reply; for TWCS an answer whose message and cited document (title + section) share none of the CloudFlow-generic topics (billing, password/login, account); for tech titles an answer whose message and cited document share none of those topics or the eight `data/public/themes.json` themes. Answers that pass this lenient rule were reviewed by hand (trace_id, cited docs and the gitignored probe text); only the probe IDs in `REVIEWED_GENERIC` in `eval/run_public.py` were judged genuinely CloudFlow-generic, every other one counts as *invented after manual review*.
- **Citation validity:** an answered reply has at least one citation and every cited source is in the audit record's retrieved sources.
- **PII leakage, two checks:** (1) `app.safety.redact` re-run over every string of every response, handoff bundle, audit record and stored conversation, and over every log line written in the run (any change = leak); (2) an independent echo check: every email and 10-19 digit run in the raw input, found with the export script's own regexes (not `app/safety.py`), is searched for verbatim (and without separators) in those objects and in the log. Check 2 is the one that can catch formats `app/safety.py` misses.
- **Stripe docs and Twilio Help Center** are structure-only sources (proprietary): they shaped the layout of our articles (`data/public/structure_templates.md`) and hold no questions or text, so there is nothing to run through the pipeline.

## Headline numbers

| Set | Requests | Correct without review | Invented (automatic rule) | Invented after manual review | Answered (citation validity) | Escalated | PII: re-scan / standalone echo / glued echo / log | p50 / p95 latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `msmarco` | 500 | 98.4% | 1 (0.2%) | 1 (0.2%) | 1 (100.0%) | 3 (0.6%) | 0 / 0 / 0 / 0 | 50 / 66 ms |
| `twcs` | 300 | 90.0% | 11 (3.7%) | 26 (8.7%) | 30 (96.7%) | 27 (9.0%) | 0 / 0 / 0 / 0 | 60 / 125 ms |
| `twcs_pii` | 50 | 94.0% | 0 (0.0%) | 3 (6.0%) | 3 (100.0%) | 5 (10.0%) | 0 / 0 / 0 / 0 | 60 / 142 ms |
| `tech` | 200 | 92.0% | 4 (2.0%) | 13 (6.5%) | 16 (100.0%) | 5 (2.5%) | 0 / 0 / 0 / 0 | 58 / 110 ms |

PII columns count probes (not occurrences). *Glued* = a 10-19 digit run attached to letters or a hyphen (see the PII section).

1050 requests in 128.8 s (setup and KB load 37.3 s). Log lines flagged by the redaction re-scan: 0.

## Answer types and verdicts per set

| Set | `answered` | `clarification_needed` | `escalated` | `not_found` | `out_of_scope` | Verdicts |
| --- | --- | --- | --- | --- | --- | --- |
| `msmarco` | 1 | 4 | 3 | 8 | 484 | acceptable 492, over_handled 7, invented 1 |
| `twcs` | 30 | 0 | 27 | 48 | 195 | acceptable 270, answered_review 19, invented_off_topic 10, invented_invalid_citation 1 |
| `twcs_pii` | 3 | 0 | 5 | 6 | 36 | acceptable 47, answered_review 3 |
| `tech` | 16 | 2 | 5 | 83 | 94 | acceptable 184, answered_review 12, invented_off_topic 4 |

**Intent types (classifier output)**

- `msmarco`: out_of_scope 484, how_to 9, troubleshooting 5, billing 2
- `twcs`: out_of_scope 195, how_to 55, billing 22, complaint 11, troubleshooting 7, account 6, security 4
- `twcs_pii`: out_of_scope 36, how_to 6, billing 4, complaint 2, security 1, troubleshooting 1
- `tech`: out_of_scope 94, how_to 63, account 22, troubleshooting 16, billing 5

## Escalations and side-effect tools

| Set | Escalated | Reasons | Queues | `send_password_reset` fired |
| --- | --- | --- | --- | --- |
| `msmarco` | 3 (0.6%) | kb_gap_needs_outcome 3, repeated_contact 1 | technical 3 | 0 |
| `twcs` | 27 (9.0%) | kb_gap_needs_outcome 14, billing_dispute 9, explicit_human_request 4, repeated_contact 4, security_incident 2, low_groundedness 2 | technical 16, billing 9, security 2 | 2 |
| `twcs_pii` | 5 (10.0%) | repeated_contact 2, security_incident 1, kb_gap_needs_outcome 1, billing_dispute 1, explicit_human_request 1 | technical 3, security 1, billing 1 | 0 |
| `tech` | 5 (2.5%) | kb_gap_needs_outcome 4, billing_dispute 1, repeated_contact 1 | technical 4, billing 1 | 0 |

## Relevance cut-off test

RETRIEVAL-MIN-01 is 0.65. The weakest in-scope core eval case (same model and top-k, `eval/results/`) has a best retrieval score of 0.7399. Had the cut-off been at that floor:

| Set | Invented answers (after review) below the floor | Reviewed-generic answers below the floor |
| --- | --- | --- |
| `msmarco` | 1 of 1 | 0 of 0 |
| `twcs` | 24 of 26 | 3 of 4 |
| `twcs_pii` | 3 of 3 | 0 of 0 |
| `tech` | 12 of 13 | 2 of 3 |

## Answered probes (for manual review, by trace_id)

Trace IDs refer to audit records in the run's temp SQLite DB (`eval-160618.db` under the system temp folder). Full lists are in the JSON files.

**`msmarco`**: 1 answered, 0 judged genuinely CloudFlow-generic on manual review. Invented after review by intent type: how_to 1; most cited: KB-ADV-007 (1).

| Probe | trace_id | Automatic verdict | Manual review | Cited | Shared topic | Intent | Best score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MM-006 | `0884c458` | invented | - | KB-ADV-007 | - | how_to | 0.7154 |

**`twcs`**: 30 answered, 4 judged genuinely CloudFlow-generic on manual review. Invented after review by intent type: billing 11, how_to 8, account 4, complaint 3; most cited: KB-BIL-006 (4), KB-TRB-001 (4), KB-GS-004 (4), KB-BIL-002 (3), TKT-2025-0733 (3), KB-BIL-005 (3).

| Probe | trace_id | Automatic verdict | Manual review | Cited | Shared topic | Intent | Best score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TW-023 | `d9bef743` | answered_review | invented | KB-GS-004, KB-BIL-005 | account | account | 0.7644 |
| TW-025 | `8dbcd4a2` | answered_review | invented | KB-GS-004, KB-BIL-005 | account | account | 0.7347 |
| TW-028 | `7a0dae42` | answered_review | invented | KB-BIL-002 | billing | billing | 0.6602 |
| TW-032 | `710a7d78` | answered_review | invented | TKT-2025-0610 | billing | billing | 0.656 |
| TW-046 | `976dd7b9` | answered_review | generic | KB-TRB-009, KB-TRB-001 | password and login | security | 0.6909 |
| TW-047 | `2ca38642` | invented_off_topic | - | KB-BIL-002, POL-ESC-001 | - | how_to | 0.7111 |
| TW-048 | `23dda3dc` | invented_off_topic | - | KB-BIL-006 | - | complaint | 0.7088 |
| TW-057 | `fae5aa9c` | answered_review | generic | KB-TRB-009, KB-TRB-001 | password and login, account | security | 0.6595 |
| TW-058 | `cfe8c322` | answered_review | invented | KB-BIL-004, KB-BIL-002 | billing, account | billing | 0.7149 |
| TW-067 | `e009ed9a` | invented_off_topic | - | KB-TRB-009, KB-TRB-005 | - | how_to | 0.7005 |
| TW-070 | `79918bbc` | answered_review | invented | KB-GS-004, KB-TRB-001 | account | account | 0.6959 |
| TW-115 | `8c221c2a` | answered_review | invented | KB-BIL-003 | billing | billing | 0.7453 |
| TW-158 | `c90ddd90` | invented_off_topic | - | TKT-2025-0733 | - | how_to | 0.6843 |
| TW-161 | `69f2ac3e` | answered_review | invented | KB-BIL-004, KB-BIL-003 | billing | billing | 0.7292 |
| TW-181 | `521d6af7` | answered_review | invented | KB-BIL-006 | billing | billing | 0.6571 |
| TW-192 | `51b2815a` | invented_off_topic | - | POL-ESC-001 | - | billing | 0.7184 |
| TW-197 | `e0cd2045` | answered_review | generic | KB-TRB-009 | password and login | how_to | 0.7417 |
| TW-210 | `f3b7be4e` | answered_review | invented | TKT-2024-0811 | account | how_to | 0.6708 |
| TW-211 | `3e6d5730` | answered_review | invented | KB-BIL-005, KB-BIL-006 | billing | how_to | 0.6919 |
| TW-213 | `7991391d` | invented_off_topic | - | KB-TRB-003 | - | complaint | 0.6575 |
| TW-218 | `56125cec` | answered_review | invented | TKT-2025-0610, TKT-2025-0733 | billing | billing | 0.6862 |
| TW-222 | `7659c9bb` | answered_review | generic | KB-BIL-004, KB-BIL-005 | billing | billing | 0.7067 |
| TW-225 | `ef3daa08` | invented_off_topic | - | KB-TRB-001, KB-TRB-003 | - | how_to | 0.67 |
| TW-241 | `1c1f487d` | invented_invalid_citation | - |  | - | account | 0.5667 |
| TW-253 | `c845adf1` | answered_review | invented | KB-TRB-001, KB-BIL-004 | billing | billing | 0.7006 |
| ... | | 5 more in `eval/results/public_twcs.json` | | | | | |

**`twcs_pii`**: 3 answered, 0 judged genuinely CloudFlow-generic on manual review. Invented after review by intent type: billing 3; most cited: KB-BIL-006 (2), TKT-2025-0610 (1), TKT-2025-0733 (1).

| Probe | trace_id | Automatic verdict | Manual review | Cited | Shared topic | Intent | Best score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TWP-03 | `1eb76d8b` | answered_review | invented | KB-BIL-006 | billing | billing | 0.688 |
| TWP-10 | `ce3e4af8` | answered_review | invented | KB-BIL-006 | billing | billing | 0.6728 |
| TWP-16 | `e74117f3` | answered_review | invented | TKT-2025-0610, TKT-2025-0733 | billing | billing | 0.6704 |

**`tech`**: 16 answered, 3 judged genuinely CloudFlow-generic on manual review. Invented after review by intent type: how_to 6, account 4, troubleshooting 2, billing 1; most cited: KB-TRB-008 (3), KB-API-005 (3), KB-API-007 (3), KB-TRB-001 (2), POL-LIMITS-001 (2), KB-TRB-007 (2).

| Probe | trace_id | Automatic verdict | Manual review | Cited | Shared topic | Intent | Best score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TT-040 | `40352ba0` | answered_review | invented | KB-TRB-008, KB-TRB-005 | scheduling and time zones | how_to | 0.6931 |
| TT-064 | `03d4216d` | invented_off_topic | - | KB-TRB-001, KB-TRB-008 | - | troubleshooting | 0.6676 |
| TT-069 | `716fc9d1` | invented_off_topic | - | KB-API-003 | - | how_to | 0.7143 |
| TT-093 | `cf6cb5b0` | invented_off_topic | - | POL-LIMITS-001, KB-BIL-001 | - | account | 0.6912 |
| TT-100 | `b069e1b7` | invented_off_topic | - | KB-TRB-006, KB-TRB-008 | - | troubleshooting | 0.7237 |
| TT-105 | `fc782ae8` | answered_review | invented | POL-LIMITS-001, KB-API-005 | rate limits and quotas | account | 0.7435 |
| TT-107 | `c4e44444` | answered_review | invented | KB-API-005 | rate limits and quotas | account | 0.6747 |
| TT-110 | `10e54bc4` | answered_review | generic | KB-API-001, KB-API-009 | auth expiry and token refresh | how_to | 0.748 |
| TT-111 | `89e19527` | answered_review | generic | KB-API-001, KB-API-012 | auth expiry and token refresh | how_to | 0.6866 |
| TT-127 | `89d1adce` | answered_review | generic | KB-API-001 | auth expiry and token refresh | how_to | 0.6965 |
| TT-128 | `bdae80cc` | answered_review | invented | KB-TRB-007 | webhook retries and signatures | how_to | 0.6534 |
| TT-139 | `29d68134` | answered_review | invented | KB-API-007, RN-4.4-001 | webhook retries and signatures | billing | 0.6832 |
| TT-144 | `32f69464` | answered_review | invented | KB-API-007 | webhook retries and signatures | how_to | 0.663 |
| TT-148 | `c23299e5` | answered_review | invented | KB-API-007, KB-TRB-007 | webhook retries and signatures | how_to | 0.6732 |
| TT-150 | `9f995443` | answered_review | invented | KB-TRB-001, KB-API-001 | auth expiry and token refresh | how_to | 0.71 |
| TT-153 | `7edb3f2c` | answered_review | invented | KB-API-005 | rate limits and quotas | account | 0.7183 |

## PII and secrets

| Set | Inputs with PII-like tokens | Token kinds | Flagged `pii_detected` | Re-scan hits | Echo hits | Log echo |
| --- | --- | --- | --- | --- | --- | --- |
| `msmarco` | 0 | none | 0 | 0 | 0 | 0 |
| `twcs` | 0 | none | 0 | 0 | 0 | 0 |
| `twcs_pii` | 50 | digits_10-12 26, digits_13-19 14, digits_10-12_glued 6, email 5, digits_13-19_glued 3 | 50 | 0 | 0 | 0 |
| `tech` | 0 | none | 0 | 0 | 0 | 0 |

*Re-scan* = `app.safety.redact` still changes a stored string (the pipeline's own redaction was skipped somewhere). *Echo* = a raw email or digit run from the input appears verbatim in an output, which also catches formats `app/safety.py` does not recognise.

Zero leaks in responses, handoff bundles, audit records, stored conversations and the log.

## Discussion of failures

This stress test was run three times on 2026-10-06 (MOCK_LLM). Each run found the problems below; each was fixed in code, guarded by a regression test, and the tables above come from the latest run on the final code. Reproductions use synthetic text, never probe text.

**Fixed after the first run (first run -> second run):**
1. *Invented CloudFlow answers to off-domain questions* (MS MARCO 24 -> 1 of 500; TWCS 47 -> 13 of 300; tech titles 21 -> 4 of 200). Four causes, four fixes:
   - `app/llm.py` `keyword_intent` (MOCK classifier): generic words (price, pay, money, rate, history, import, support, status) no longer count as CloudFlow vocabulary, so "price of a new kitchen sink" is out_of_scope.
   - `app/graph/nodes.py` `unsupported_terms`: a sentence's first word is now checked when it looks like a name (internal capitals, or unknown to the KB vocabulary in a message with no I/me/you words), so "Laravel rate limiter not working" -> ['Laravel'] -> not_found.
   - Policy registry RETRIEVAL-MIN-01 raised 0.35 -> 0.65 through the rule-change path (POL-ESC-001 edited, KB regenerated, registry row updated). Calibrated on this run plus the 32 core cases: removes 62 of 128 off-domain answers, loses 0 of 19 correct in-scope answers (weakest 0.74).
   - The MOCK critic still cannot judge whether a draft answers the question (it scores overlap with the quoted chunks); the live critic prompt is meant to catch this.
2. *Over-handled general queries* ("what is a court of appeal" -> legal handoff; "what does a travel agent do" -> human request): `_LEGAL` and `_HUMAN` now count only when the message is personal (I/me/my/you) or uses CloudFlow words. "I want to talk to a human" still escalates.
3. *A phone number typed straight after a word* ("line07700900123") was stored unredacted in the conversation messages: `app/safety.py` now also redacts glued 10-12 digit runs as [PHONE] and glued Luhn-valid 13-19 digit runs as [CARD].
**Fixed after the second run (second run -> latest run):**
4. *Two digit-run echoes in stored conversation messages* (TWP-13, TWP-41): a 13-digit alphanumeric tracking code that fails the card checksum, and a dashed reference behind a letter prefix (AA-dddddd-dddd). `app/safety.py` now hides 10+ digits behind a letter prefix and long non-Luhn glued runs as [PHONE]; short IDs such as TKT-2025-0142 or INC-2026-1004 are untouched. Echo hits 2 -> 0.
5. *The out-of-scope rescue answered lowercase off-domain questions* ("how long does it take for moneygram"): it overruled the classifier whenever a KB article scored just above the 0.65 floor, and the unknown-name check only sees capitalised words. `_kb_covers` now also needs every content word of the question to be known to the KB or to the retrieved chunks, so a judge-ingested topic is still rescued. MS MARCO 5 -> 1, TWCS 32 -> 11, tech 8 -> 4.
**Remaining, by design:**
6. TWCS answers that remain are mostly generic billing/password topics a signed-in CloudFlow customer could ask (listed for review by trace_id); one off-domain account message was answered only from the customer's own account facts (no KB citation), which is the designed behaviour when tools hold the facts.
7. By design there is no "is this about CloudFlow?" gate before tools for a signed-in customer, so a tweet about logging in elsewhere can trigger the (mocked) password-reset tool; billing complaints reach the billing queue.
8. No crashes: 0 HTTP errors in 1,050 requests, and every response passed the 6.1 response model.

## Licences and data handling

| Source | Licence (data/public/manifest.csv) | Used here |
| --- | --- | --- |
| Customer Support on Twitter (Kaggle thoughtvector/customer-support-on-twitter) | CC BY-NC-SA 4.0 (confirmed: Kaggle dataset card via kaggle CLI) | `twcs`, `twcs_pii`: 300 tweets as runtime probes |
| MS MARCO QnA v2.1 (validation split, streamed) | Non-commercial research purposes only (confirmed: microsoft.github.io/msmarco terms) | `msmarco`: 500 queries as runtime probes |
| GitHub Discussions (GraphQL API, read-only via gh) | GitHub Terms of Service (confirmed: D.8 public content, H API terms); titles + URLs only | `tech`: 100 titles |
| Stack Overflow (Stack Exchange API /2.3/questions) | CC BY-SA 2.5; CC BY-SA 3.0; CC BY-SA 4.0 (confirmed: per-question content_license from the API); Stack Exchange API terms | `tech`: 100 titles |
| Stripe docs (structure only) | Proprietary, all rights reserved (unverified); structure modelled on public conventions, no text copied | not run (structure only) |
| Twilio Help Center (structure only) | Proprietary (confirmed: Twilio ToS s4.1 Twilio owns its Documentation); no text copied | not run (structure only) |

- Probe files with real third-party text live only in `data/raw/probes/` (gitignored). The repo holds only aggregates, probe IDs and trace_ids. Non-commercial terms (MS MARCO, TWCS CC BY-NC-SA) fit a hackathon evaluation; nothing from them is redistributed.
- TWCS customer handles were already anonymised by the dataset; the export additionally scrubs handles, URLs, emails, phone-like and long numbers and simple name patterns in `twcs_300` (the same `scrub()` used for the tone exemplars). Only `twcs_pii_50` keeps the raw text, on purpose, to test redaction.
- GitHub and Stack Overflow titles are public and attributed by URL in the gitignored probe file and in `data/public/themes.json`; no usernames are read.


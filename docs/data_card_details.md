# Data card details: CloudFlow synthetic data

The one-page card is [data_card.md](data_card.md). This file holds the full counts, tables, prompts and
public-data notes behind it.

All numbers below were counted from the files in the repo on 2026-10-06 (`data/accounts/*.csv`,
`data/source_register.csv`, `data/generation/*_log.json`). Re-count them with the scripts named in each section.

## Purpose

Test data for InsightDesk, the support agent for the fictional SaaS product CloudFlow. It has two parts:

- **Account data** (SQLite, Annex C tables). The deterministic tools read it: usage against plan limits,
  invoices, refund eligibility, platform status. It must cover all four plans and all four statuses,
  plus edge cases at the exact boundaries the tools decide on (A1001-A1008).
- **Knowledge base** (73 documents in Chroma, described in `docs/knowledge_base.md`). It must cover both
  product versions (3.x and 4.x), outdated tickets that conflict with current docs, a future deprecation,
  a supersession, a prompt-injection ticket, and policy articles whose numbers match the policy registry.

Nothing in it is real: companies and people are invented, emails are only `@example.com`, and cards are
stored as their last four digits only.

## Generator

| Part | Model | Mode | Temperature | Calls / documents |
| --- | --- | --- | --- | --- |
| Knowledge base (6 batches) | `claude-opus-5-5 (Claude Code subagent)` | replay | n/a | 73 documents in 6 batches; call and token counts n/a (written outside live mode) |
| Filler accounts A1009+ | `claude-opus-5-5 (Claude Code subagent)` | replay | n/a | 1 call (one saved reply), 25 rows generated |
| Edge cases A1001-A1008, `plan_limits`, `platform_status` | none: fixed specs in `scripts/generate_accounts.py` | code | n/a | 8 accounts, 4 plans, 4 components |
| Filler invoices | none: computed in code from the plan price | code | n/a | the LLM never does money arithmetic |

**Why replay.** Ollama was not yet installed on the build machine when the data was generated, so Claude Code subagents acted as the LLM,
following the same rendered prompts. Their replies are saved as-is in `data/generation/kb_batches/*.json` and
`data/generation/accounts_batches/batch_01.json`. Every document's `provenance` field says which model wrote it.

**Live mode** sends the same prompts to the local model: Ollama `qwen2.5:7b-instruct` at temperature 0.1
(set in `app/llm.py`). For the KB it makes one call per document with up to 2 retries; for accounts, one call
plus up to 2 retries for invalid rows. Live mode records the model, calls and tokens in the batch file.

## Prompts

| Prompt | Used for |
| --- | --- |
| [`data/generation/prompts/gs_bil.md`](../data/generation/prompts/gs_bil.md) | Getting-started and billing articles |
| [`data/generation/prompts/policies_rn.md`](../data/generation/prompts/policies_rn.md) | Policies and release notes |
| [`data/generation/prompts/api_trb.md`](../data/generation/prompts/api_trb.md) | API/integration and troubleshooting articles |
| [`data/generation/prompts/adv.md`](../data/generation/prompts/adv.md) | Advanced-feature articles |
| [`data/generation/prompts/tickets.md`](../data/generation/prompts/tickets.md) | Resolved tickets |
| [`data/generation/prompts/community.md`](../data/generation/prompts/community.md) | Community posts |
| [`data/generation/prompts/accounts_v1.md`](../data/generation/prompts/accounts_v1.md) | Filler accounts |
| [`data/generation/prompts/_passthrough.txt`](../data/generation/prompts/_passthrough.txt) | Template that sends a whole prompt through `app.llm.call_json` |

Each KB prompt (prompt version `kb-v1`) is built from four parts: the shared rules, the fact sheet
[`data/generation/cloudflow_facts.md`](../data/generation/cloudflow_facts.md), the batch brief in
[`data/generation/briefs/`](../data/generation/briefs/), and the JSON output schema. This is our improved
version of the Annex F prompt. It generates one category per batch and fixes the IDs, versions, error codes,
policy numbers and outdated tickets in advance. `gs_bil` and `policies_rn` were written from an earlier render
that did not yet have the public-data guidance section (see `data/generation/README.md`).

## Schema enforcement

| Where | How |
| --- | --- |
| KB, `scripts/generate_kb.py` | Each document is validated with Pydantic: `SourceMeta` (Annex B metadata) plus `Document` / `Ticket` for the body. Extra rules: the ID is in the manifest; doc_type and authority match the ID prefix; title, versions and dates match the manifest; required `## ` sections exist (articles always need `## Applies to`); no judge-reserved IDs; only `@example.com` emails; no SAP/Ariba; no real-looking `cf_live_`/`cf_test_` tokens; no date after 2026-10-06. Live mode retries an invalid document up to 2 times with the errors appended. Replay skips invalid documents and logs them. |
| Accounts, `scripts/generate_accounts.py` | Each filler row is validated with `FillerAccount`, which extends `AccountRow`. Cross-field checks: no A9000-A9999 IDs; card_last4 is exactly 4 digits; Free accounts are never past_due or suspended; one usage row per period; seats within the plan. Live mode re-asks for invalid rows up to 2 times. After that, a row gets a safe, logged code repair (email domain, card cut to its last 4 digits) or is dropped. |
| All CSVs, `scripts/validate_accounts.py` | Pydantic row models `AccountRow`, `PlanLimitRow`, `UsageRow`, `InvoiceRow`, `PlatformStatusRow` and `PolicyRow`, plus cross-table logic checks. The generator, the validator and the loader all use these same models. |

## Row counts and distributions

**Accounts: 31** (8 edge cases + 23 accepted fillers). Product versions: 4.3: 12 · 4.4: 10 · 4.2: 6 · 3.8: 3
(A1008, A1021, A1024). Created between 2023-11-09 and 2026-09-02.

| Plan | active | past_due | suspended | cancelled | Total |
| --- | --- | --- | --- | --- | --- |
| Free | 4 | 0 | 0 | 1 | 5 |
| Pro | 8 | 2 | 1 | 1 | 12 |
| Business | 5 | 1 | 1 | 1 | 8 |
| Enterprise | 3 | 1 | 1 | 1 | 6 |
| **Total** | **20** | **4** | **3** | **4** | **31** |

**Usage: 62 rows**, one per account for each of 2026-10 (current, 6 days in) and 2026-09 (full month).

| Period | Runs as share of plan limit (min / median / max) | Over a limit |
| --- | --- | --- |
| 2026-09 | 0% / 61% / 99% | API peak: A1011 (1,040 > 1,000; a filler row, not a seeded case) |
| 2026-10 | 0% / 12% / 100% | Runs: A1002 (10,001 > 10,000). API peak: A1002 (301 > 300). A1001 is exactly at 10,000 and not over |

No account uses more seats than its plan allows.

**Invoices: 56** for 26 accounts. Every non-Free account has 1-4 invoices; no Free account has any. Charge dates
run from 2026-08-01 to 2026-10-04.

| By status | Count | By currency | Count |
| --- | --- | --- | --- |
| paid | 48 | USD | 43 (49.0 ×25, 199.0 ×9, 999.0 ×9) |
| failed | 7 | INR | 13 (4,100 ×2, 16,700 ×8, 83,600 ×3), 6 accounts |
| refunded | 1 (A1029, cancelled) | | |

INR prices are the USD price × 83.7, rounded to the nearest 100, computed in code. Failure reasons:
card_declined 3, card_expired 2, insufficient_funds 2. The only same-amount, same-day pair is A1004's.

**plan_limits: 4 rows**. These match the plan-limits policy and the fact sheet: Free 60/min, 500 runs, 1 seat ·
Pro 300, 10,000, 5 · Business 1,000, 50,000, 25 · Enterprise 5,000, 500,000, 200.
**platform_status: 4 rows**. api, connectors and billing are operational; workflow-engine is **degraded**
(INC-2026-1004).

**Knowledge base: 73 documents**, all `synthetic: Y`. Of these, 34 articles, 3 policies, 2 release notes,
28 tickets and 6 community posts. Per-category counts are in `docs/knowledge_base.md`.

## Edge cases included

Reference date 2026-10-06; refund window 14 days (from `policy_registry`).

| Account | Edge case | Exact values in the CSVs |
| --- | --- | --- |
| A1001 | Usage exactly at the limit | Pro, active, 4.3; 2026-10: 10,000 runs, API peak 300, 5 seats (all equal to the Pro limits, so not over) |
| A1002 | One unit over the limit | Pro, active, 4.3; 2026-10: 10,001 runs, API peak 301 (causes 429s) |
| A1003 | Failed payment | Pro, **past_due**, 4.2; INV-6303 49.0 USD 2026-10-01 **failed**, `card_declined` |
| A1004 | Duplicate charge | Pro, active, 4.4; INV-6001 and INV-6002, both 49.0 USD, paid, charged 2026-10-01 |
| A1005 | Charge on the last day of the window | Business, active, 4.3; INV-6502 199.0 USD paid 2026-09-22 (14 days → eligible) |
| A1006 | Charge one day after the window | Pro, active, 4.4; INV-6602 49.0 USD paid 2026-09-21 (15 days → not eligible) |
| A1007 | Suspended account | Pro, **suspended**, 4.3; INV-6702 2026-09-01 failed `card_expired`; 0 runs in 2026-10 |
| A1008 | Old product version | Pro, active, **3.8**; invoices in INR (4,100) |

## Validation results

`scripts/validate_accounts.py` → `data/accounts/validation_report.txt`: **0 violations** over 4 + 31 + 62 + 56 + 4
rows (`policy_registry.csv` is optional and not present). Checks run:

- ID formats; no A9000-A9999 account IDs and no `INV-J` invoice IDs (our data only; the judge loader skips this check)
- plan, status, currency, support_tier and component status are in the allowed sets; every usage/invoice account exists
- `@example.com` emails only; card_last4 is exactly 4 digits; no 13-19 digit card number in any cell
- amount > 0; non-negative usage and limits; failure_reason only on failed invoices
- past_due and suspended accounts have a failed invoice; Free accounts have no invoices
- valid YYYY-MM-DD dates, YYYY-MM periods, ISO timestamps; no duplicate keys

`scripts/generate_kb.py` → `data/generation/kb_check.txt`: **RESULT: PASS**. 73/73 documents are valid in all
six batches. All 73 manifest IDs are present, all 13 seeded cases pass, all 9 policy-number checks pass, and
every one of the 73 register rows has its file.

## What the LLM got wrong

From `data/generation/accounts_generation_log.json`: 4 of the 25 filler rows failed validation. 23 were
accepted (2 after a code repair) and 2 were dropped. That is why IDs A1012 and A1030 do not exist.

| Row | Error caught | Fix |
| --- | --- | --- |
| A9012 | ID in the judge-reserved range A9000-A9999 | dropped |
| A1015 | owner_email used a non-`example.com` domain | repaired in code: domain replaced with `example.com` |
| A1020 | full card number in `card_last4` | repaired in code: cut to the last 4 digits |
| A1030 | negative `workflow_runs` in 2026-09 | dropped |

From `data/generation/kb_generation_log.json`: **0 validation errors** in all six KB batches (73/73 valid on
the first replay). So far the KB checks have not caught a mistake, because the documents were written by a
strong model. The same checks gate live runs of the 7B model.

## Known limitations

- **Synthetic and small.** 31 accounts and 73 documents are far smaller than a real help center. Company
  names and usage patterns are plausible but not modelled on real distributions.
- **One reference date.** All dates assume 2026-10-06. Usage covers only 2026-09 and 2026-10, and invoices
  only Aug-Oct 2026. If `as_of_date` changes, the A1005/A1006 refund-window boundaries move with it.
- **Authored by Claude, not the local model.** Replay data came from `claude-opus-5-5` standing in for
  `qwen2.5:7b-instruct`. The four account slips above show that validation works, but they do not measure the
  local model's error rate. A live run may produce different or more mistakes.
- **No LLM call or token counts for the KB**, because it was generated outside live mode.
- **Some filler rows go past plan limits without a label.** A1011 is over its API limit in 2026-09 (an LLM row,
  not a seeded case). Tests should rely only on A1001-A1008.
- **Theme counts are biased.** `data/public/themes.json` counts come from four queried Stack Overflow tags and
  four GitHub repos. Read them as "topics that exist", not as how often topics come up.
- **Tone is second-hand.** The angry-customer tone in tickets and probes comes from 15 paraphrases. No real
  customer text is stored.
- **Raw replies are kept, with two values masked.** `accounts_batches/batch_01.json` still holds the LLM's
  original rows, including the slips above. The two slip values are masked so that no PII scan flags the file:
  the full card-like number is now `4716XXXXXXXX5532`, and the non-example email domain is now `.invalid`.
  Both still fail validation the same way, so the error record and the fix are unchanged. Neither value
  reaches the CSVs or the database.

## Public data used

From `data/public/manifest.csv` (all accessed 2026-10-06). Public data was used **for realism only**: no public
text was copied into the KB.

| Source | Licence | Use | Landed in repo |
| --- | --- | --- | --- |
| Customer Support on Twitter (Kaggle) | CC BY-NC-SA 4.0 | Tone of angry / repeat-contact messages | `data/public/tone_exemplars.jsonl` (15 paraphrases: 12 angry, 3 negative); `eval/probes_tone.jsonl` (15 probes, all expected `escalated`) |
| MS MARCO QnA v2.1 (validation, streamed) | Non-commercial research only | Question phrasing; out-of-scope probes | `data/public/question_templates.txt` (15 patterns counted over 5,000 queries); `eval/probes_oos.jsonl` (20 probes from 222 candidates, all expected `out_of_scope`) |
| GitHub Discussions (GraphQL, read-only) | GitHub ToS; titles + URLs only | Topic mining; seeds COM- posts | `data/public/themes.json` (354 answered discussions, 4 repos) |
| Stack Overflow (Stack Exchange API) | CC BY-SA 2.5/3.0/4.0 per question | Topic mining, error phrasing | `data/public/themes.json` (200 questions over 4 tags; `salesforce` used because `salesforce-api` had 0) |
| Stripe docs | Proprietary | Section skeleton, error-table and rate-limit layout | `data/public/structure_templates.md` (our own words, nothing scraped) |
| Twilio Help Center | Proprietary | FAQ format for billing articles | same file |

**Anonymisation steps** (`scripts/mine_public_data.py`):

1. Raw downloads stay in `data/raw/`, which is gitignored and never committed.
2. Tweets are scrubbed with regexes: URLs, emails, @handles, phone/card/order numbers and simple name patterns
   (agent initials, "my name is …", "agent/manager <Name>") are replaced with placeholders.
3. Each scrubbed tweet is paraphrased into a CloudFlow context. The original text is not stored; each exemplar's
   provenance records only the frustration cue that selected it.
4. MS MARCO: only counts and our own CloudFlow example wording go into the templates file. The 20 probe queries
   pass an exclusion regex (no CloudFlow-like, medical, financial or personal topics).
5. GitHub and Stack Overflow: only titles, tags and URLs are read, and only theme counts plus example URLs (for
   attribution) are kept. No usernames are stored.
6. In the source register, generated documents whose tone or themes came from `data/public` say
   "tone/themes from data/public" in `provenance` (34 of the 73).

### Public data at scale (robustness evaluation)

Besides shaping the KB, the public sources are run through the real pipeline (`POST /support`) at scale as a
robustness test. `python scripts/mine_public_data.py --export-probes` samples them from the cached raw downloads
with a fixed seed. `python eval/run_public.py` then sends each probe as one request (MOCK_LLM on the build machine,
`--live` for Ollama).

| Probe set | Size | Source | Expected |
| --- | --- | --- | --- |
| `msmarco_500` | 500 | MS MARCO queries, CloudFlow-like ones removed | never `answered` |
| `twcs_300` | 300 | inbound tweets to other brands (250 thread openers + 50 with PII-like text), scrubbed | no invented CloudFlow answers |
| `twcs_pii_50` | 50 | the same 50 tweets **unscrubbed**, to stress-test `app/safety.py` | zero PII in responses, bundles, audits, stored conversations, log |
| `tech_titles_200` | 200 | 100 GitHub Discussions + 100 Stack Overflow titles about other tools | no invalid citations, no off-topic answers |

Stripe and Twilio are structure-only sources, so there is nothing of theirs to run. The probe files contain real
third-party text and live **only** in gitignored `data/raw/probes/`. The repo keeps aggregates and trace_ids only
(`eval/results/public_*.json`) plus the method, tables and failure analysis in `eval/public_report.md`.

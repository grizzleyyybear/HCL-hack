# AI-usage disclosure

The hackathon rules (guide section 10) allow AI coding assistants as long as their use is disclosed and every member can explain the code we submit. This page lists what was generated with AI, by which agent, and how each piece was checked. Anything we could not confirm from the repository is marked **to be confirmed by the team**.

## Assistant and how it was used

- **Tool:** Claude Code (Anthropic), model `claude-opus-5-5`. One orchestrator session launched **subagents**, one per area, following [BUILD_PLAN.md](../BUILD_PLAN.md) (Mode B: one machine, parallel subagents). If any subagent ran on a different model, that is to be confirmed by the team.
- **Rules every agent followed** (BUILD_PLAN.md section 1): write only the files it owns (exclusive ownership), never change the frozen contracts in section 3, read every threshold from `policy_registry`, never hard-code answers to demo or eval questions, never use judge-reserved IDs, comment every function, and make it work with `MOCK_LLM=true`. Each agent ended by running its own "Done when" checks.
- **Gates:** after each wave the orchestrator merged the work and ran the gate checks in BUILD_PLAN.md section 7. A reviewer agent (A15) then read the code against CLAUDE.md for requirement gaps, magic numbers, hard-coded answers and PII paths.
- **No LLM at runtime during the build.** Ollama was not installed on the build machine, so every module was built and tested with `MOCK_LLM=true`. The local model (`qwen2.5:7b-instruct`) has not yet been exercised end to end. The team must do that before judging (see "What humans must still do").
- **The cloud-LLM switch was not used.** `LLM_PROVIDER=cloud` exists in `app/llm.py` as a disclosed fallback (README "Cloud-LLM fallback"). No code or data in this repository was produced through it.
- **Design documents.** [CLAUDE.md](../CLAUDE.md) and `docs/design_doc.md` carry the byline "@Mrinal Sharma". Who wrote [BUILD_PLAN.md](../BUILD_PLAN.md), `docs/design_doc.pdf`, `docs/diagrams/` and `docs/pitch/`, and whether AI helped write any of these documents, is to be confirmed by the team.

## Code: agent → files → how it was verified

Test counts are the number of test cases pytest collects for each file (parametrized cases count separately), measured when this page was written: 334 in total. Each file was written by the agent named in the first column. Run `pytest -q` again before the `final` tag. During one run while this page was being written, 1 test in `tests/test_llm.py` failed because another agent was editing `app/llm.py` at the same moment. That failure must be re-checked.

| Agent (owner) | Files produced | How it was verified |
| --- | --- | --- |
| A0 orchestrator (M4) | `app/config.py`, `app/db.py`, `app/schemas.py`, `app/main.py` (routes), `app/graph/state.py`, module stubs, `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini` | Gate G0: dependencies install, `db.init_db()` works, `pytest --collect-only` passes, `GET /health` answers. Every later test imports these contracts |
| A1 public-data (M1) | `scripts/mine_public_data.py`, `data/public/*`, `eval/probes_oos.jsonl`, `eval/probes_tone.jsonl` | `data/public/manifest.csv` lists all 6 sources, with the licence checked on each source page. Anonymisation steps are listed in `docs/data_card.md`. Raw downloads stay in gitignored `data/raw/` |
| A2 kb-author (M1) | `scripts/generate_kb.py`, `data/generation/` (fact sheet, briefs, verbatim prompts, batches, logs), `data/kb/**`, `data/source_register.csv` | Every document is validated with Pydantic plus manifest rules. `data/generation/kb_check.txt` reports **RESULT: PASS**: 73/73 documents valid, all 13 seeded cases present, all 9 policy-number checks match the registry, and every register row has its file |
| A3 account-data (M1) | `scripts/generate_accounts.py`, `scripts/validate_accounts.py`, `scripts/load_accounts.py`, `data/accounts/*`, `data/generation/accounts_*` | `tests/test_accounts.py` (9). `data/accounts/validation_report.txt` shows 0 violations. The loader accepts judge IDs (A9001, INV-J001) |
| A4 retrieval-core + A5 ingest-api (M2) | `app/retrieval.py`, `scripts/ingest_kb.py` | `tests/test_retrieval.py` (24): version parsing, chunking, version-filtered search. `tests/test_ingest.py` (11): live `/ingest` with `JD-` IDs, 422 errors, `/sources`, load-once/skip |
| A6 precedence (M2) | `app/precedence.py` | `tests/test_precedence.py` (13): seeded cases 1–6, deprecation before/after 2026-12-01, one batched LLM call |
| A7 tools-policy (M3) | `app/tools/*.py`, `scripts/seed_policy_registry.py`, `tests/conftest.py` | `tests/test_tools.py` (21): every tool on A1001–A1008, policy change without code change |
| A8 safety (M3) | `app/safety.py` | `tests/test_safety.py` (105): redaction patterns, false positives, authorisation, secret requests, promise scan, redacted logs |
| A9 escalation (M3) | `app/escalation.py` | `tests/test_escalation.py` (62): every A.3 rule, the "do not escalate" cases, the one-revision cap, routing, bundle, SLA message |
| A10 llm-client (M4) | `app/llm.py`, `app/prompts/*.txt` | `tests/test_llm.py` (37): invalid JSON → one retry → fallback against a mocked Ollama, cloud call shape, wrapper-tag stripping, deterministic mock helpers |
| A11 pipeline (M4) | `app/graph/nodes.py`, `app/graph/pipeline.py` | `tests/test_pipeline.py` (19): one request per `answer_type` through `POST /support`, plus the 429, duplicate-charge, outdated-ticket, PII and injection cases |
| A12 api-platform (M4) | `app/main.py` (endpoint bodies), `app/audit.py`, `ui/streamlit_app.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Endpoints are exercised through FastAPI TestClient in the pipeline, ingest and red-team tests. Whether `docker compose up` was checked from a fresh clone is **to be confirmed by the team** (it is a Freeze gate item) |
| A13 eval-runner (M2) | `eval/run_eval.py`, `eval/report.md`, `eval/results/`, `eval/critic_sample.csv` | The runner scores against labels in `eval/eval_set.jsonl` (exact match plus keywords, no LLM-as-judge). The report states that it was measured in MOCK mode, and it lists its failures as observed |
| A14 red-team (M3) | `tests/test_redteam.py`, `scripts/pii_scan.py` | `tests/test_redteam.py` (33): end-to-end attacks, ending with a PII scan of the temp DB and log |
| A15 reviewer | none (reports only) | Gate verdicts with evidence |
| A16 docs (M1) | `docs/data_card.md` | Counts re-checked against the CSVs, the register and the generation logs. Which agent wrote `docs/knowledge_base.md` (A16 or A2) is to be confirmed by the team |
| W6 docs-readme (M1/M4) | `README.md`, `docs/ai_usage_disclosure.md`, `docs/team_contribution.md`, `docs/declaration.md` | Every command, path, env var and endpoint was checked against the code, and the orchestrator reviewed the result |
| Eval cases (everyone) | `eval/eval_set.jsonl` (32 cases, `E-M1-nn` … `E-M4-nn`), `eval/README.md`, `eval/fixtures/` | Labels come from CLAUDE.md, the KB and the account CSVs, never from system output (eval/README.md). Whether each member's 8 cases were drafted by an agent or by the member is **to be confirmed by the team**. Each member must review their own 8 cases |

### Fixes made after integration

Cross-agent integration tests (the pipeline, red-team and eval runs) found problems that no single agent's unit tests showed. The owning agent or the orchestrator then fixed each one, and a test now guards it.

| Problem found | Fix | Where | Guarded by |
| --- | --- | --- | --- |
| "I forgot my password, send the reset link here" was **refused** by the secret-request check, because it mentions a reset link | A reset request skips the secret refusal and goes to `send_password_reset`. The link is never shown in chat | `RESET_REQUEST` in `app/graph/nodes.py` (`pre_checks`) | `tests/test_pipeline.py::test_password_reset_is_sent_by_tool_and_never_shown`, `tests/test_escalation.py::test_password_reset_without_compromise_is_answered` |
| An article covering ALL versions with sections such as "Steps in CloudFlow 3.x" could give a 4.3 customer the 3.x steps (KB-TRB-004, CF-503) | A section whose heading names one major version gets its version range narrowed to that version at ingest time | `_chunk_meta` / `SECTION_VERSION` in `app/retrieval.py`. The template composer also skips other-version sections | `tests/test_retrieval.py::test_section_heading_narrows_version_range`, `tests/test_llm.py::test_troubleshooting_quotes_the_steps_for_the_account_version` |
| "My password is not working" was redacted as if it contained a password (**false positive**) | A negative lookahead skips ordinary words after "password is" | `PASSWORD_RE` in `app/safety.py` | `tests/test_safety.py::test_password_sentence_not_redacted` |
| "Does CloudFlow integrate with SAP Ariba?" scored above `min_relevance` (it matches integration articles), so relevance alone would have **answered** it | A code-only **unsupported-terms check**: named terms in the question that no retrieved source mentions set the critic coverage to `none`, which gives `not_found` (or a handoff when a human outcome is needed) | `unsupported_terms()` and the `critic` / `decide` nodes in `app/graph/nodes.py` | `tests/test_pipeline.py::test_uncovered_named_product_is_not_found`, `::test_named_term_check_leaves_covered_terms_alone`, `::test_critic_coverage_none_means_not_covered` |
| The mock/fallback disagreement heuristic reported **false conflicts** for tickets that agree with the docs | The heuristic in `app/precedence.py` was tightened. As the code reads now, a text's own warnings are ignored when matching, and the low-overlap rule applies only to doc-vs-ticket pairs. The exact before/after change is to be confirmed by the team from the session log | `_heuristic_disagree` / `_warns_against` in `app/precedence.py` | `tests/test_precedence.py::test_agreeing_ticket_is_kept` |

## AI-generated data

All data is synthetic. Emails use `@example.com` only, cards are stored as their last four digits, and no real customer text is stored.

| Data | Generated by | How it was validated |
| --- | --- | --- |
| Knowledge base: 73 documents (34 articles, 3 policies, 2 release notes, 28 tickets, 6 community posts) in 6 batches | Claude Code subagents (`claude-opus-5-5`) acting as the LLM in **replay mode**, following the rendered prompts in `data/generation/prompts/` (our improved Annex F prompt). Outputs are saved verbatim in `data/generation/kb_batches/`, and every document's `provenance` field names the model | `scripts/generate_kb.py`: Pydantic schemas plus manifest rules (fixed IDs, versions, required sections, no reserved IDs, only `@example.com` emails, no SAP/Ariba, no real-looking tokens, no date after 2026-10-06). `kb_check.txt`: PASS, 0 validation errors. The same checks will gate a live 7B run |
| Filler accounts A1009+ (25 rows generated, 23 accepted) | One Claude Code subagent reply in replay mode, from `data/generation/prompts/accounts_v1.md`, saved in `data/generation/accounts_batches/batch_01.json` | Pydantic validation caught 4 mistakes (`data/generation/accounts_generation_log.json`): a reserved ID A9012 (dropped), a non-example.com email (repaired), a full card number in `card_last4` (cut to 4 digits), negative runs (dropped). Edge cases A1001–A1008, plan limits and platform status come from fixed specs in code, and invoices are computed in code. `validate_accounts.py` reports 0 violations |
| 15 tone exemplars and the 15 tone probes | Paraphrased by a Claude Code subagent (`claude-opus-5-5`) from 15 anonymised inbound tweets (Customer Support on Twitter, CC BY-NC-SA 4.0). Stored in `PARAPHRASES` in `scripts/mine_public_data.py`. The original tweet text is not stored | Each line records its provenance. Handles, URLs, emails and numbers were scrubbed before paraphrasing. Raw data stays in gitignored `data/raw/` |
| 20 out-of-scope probes | **Not** AI-generated: real MS MARCO query strings (non-commercial research licence), filtered by an exclusion regex | Listed in `data/public/manifest.csv` |
| Eval fixture `JD-EVAL-001` | Written for the eval runner to simulate unseen judge content. Its provenance says "written by hand". Whether a person or an agent wrote it is to be confirmed by the team | Ingested through `POST /ingest` during the eval run |

Details: [docs/data_card.md](data_card.md) (Annex E), [data/generation/README.md](../data/generation/README.md), [docs/knowledge_base.md](knowledge_base.md).

## What humans must still do

The AI produced a working first version. The team owns it, and each item below is a human responsibility.

1. **Review and understand every file.** Each member reads every file in their area (see [docs/team_contribution.md](team_contribution.md)) and can explain both their own part and the whole pipeline in Q&A, including small live code changes.
2. **Install Ollama and run on the real model.** Run `ollama pull qwen2.5:7b-instruct`, check JSON output (README step 4), run the demo script, and run `python eval/run_eval.py --compare --live`. Fix or document any difference from the MOCK results.
3. **Label the critic-agreement sample.** Two members independently fill `eval/critic_labels.csv` from `eval/critic_sample.csv`, preferably regenerated with the live model, without looking at the critic score first. Then rerun the eval.
4. **Capture samples from real Ollama runs:** three audit records in `docs/sample_audits/` and two handoff bundles in `docs/sample_handoffs/` (not present yet).
5. **Check Docker from a fresh clone:** `docker compose up --build`, `/health` all ok, three curls, loader inside the container.
6. **Commit under your own names.** Git history must show commits from all four members. Agree how AI co-authorship is marked in commit messages (BUILD_PLAN.md section 8).
7. **Resolve every "to be confirmed by the team" item on this page,** fill in [docs/team_contribution.md](team_contribution.md), and sign [docs/declaration.md](declaration.md).

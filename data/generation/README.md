# data/generation: how the CloudFlow knowledge base is generated

Everything in `data/kb/` and `data/source_register.csv` is produced by `scripts/generate_kb.py` from the files in
this folder. Do not edit `data/kb/` by hand: fix the batch file (or the brief) and re-run the script.

| Path | What it is |
| --- | --- |
| `cloudflow_facts.md` | Single source of truth: product facts, versions, plan limits, policies, error codes, and the fixed KB manifest (every allowed ID, title, version and required section) |
| `briefs/<batch>.md` | What one batch must contain (one category per batch: `gs_bil`, `policies_rn`, `api_trb`, `adv`, `tickets`, `community`) |
| `prompts/<batch>.md` | The full prompt for a batch: rules + facts sheet + brief + public-data guidance + JSON schema (the improved Annex F prompt) |
| `prompts/_passthrough.txt` | One-line template (`$prompt`) that lets live mode send a whole prompt through `app.llm.call_json` |
| `kb_batches/<batch>.json` | The generated output of a batch, in the batch file contract shape (see the end of the facts sheet) |
| `kb_generation_log.json` | Per batch: model, temperature, prompt file, documents, valid count, LLM calls and tokens (live mode), validation errors |
| `kb_check.txt` | The KB check: counts vs the guide's minimums, manifest coverage, seeded cases, policy numbers, register files |

## The two modes

**Replay (default, no LLM needed).** Validates every `kb_batches/*.json` and writes the KB:

```
.venv\Scripts\python.exe scripts\generate_kb.py
```

Each document is checked with Pydantic (`SourceMeta` for metadata; Markdown or ticket body) plus extra rules: the ID
is in the manifest, doc_type and authority match the ID prefix, title / product_versions / effective_from match the
manifest, required `## ` sections exist (articles always need `## Applies to`), no judge-reserved IDs (A9000-A9999,
INV-J, JD-), emails only @example.com, no SAP/Ariba, no real-looking `cf_live_`/`cf_test_` tokens, no date after
2026-10-06. Invalid documents are skipped and listed in the log and the check; a missing batch is reported, not fatal.
Old files in `data/kb/articles|tickets|community` are removed first, so the folder always equals the valid batches.

**Live (needs Ollama or the cloud fallback).** Generates one batch with the LLM, one call per document so a 7B model
stays inside its context and the 120-second timeout, retrying an invalid document up to 2 times with the validation
errors appended:

```
ollama pull qwen2.5:7b-instruct          # once
set MOCK_LLM=false                        # PowerShell: $env:MOCK_LLM="false"
.venv\Scripts\python.exe scripts\generate_kb.py --live --batch adv
.venv\Scripts\python.exe scripts\generate_kb.py            # then replay to write the KB
```

Live mode saves `kb_batches/<batch>.json` with the model name, temperature, number of LLM calls, tokens and any
documents that still failed. If Ollama is too slow, set `LLM_PROVIDER=cloud` for generation only and disclose it.

`--render-prompts` rewrites `prompts/<batch>.md` for every brief (live mode does this automatically).

## How the current batches were produced (disclosure)

Ollama was not available on the build machine, so all six batches were written by Claude Code subagents
(model `claude-opus-5-5`, temperature n/a) following the rendered prompt for their batch, and recorded as such in
each batch file and in every document's `provenance`. The same files can be regenerated locally with live mode.
The prompts were re-rendered after `data/public/` was created, so they now include a public-data guidance section;
`gs_bil` and `policies_rn` were authored from the earlier render without that section (the other content agents
read `data/public/` directly where their provenance says "tone/themes from data/public").

## Revisions after generation

- **2026-10-06 — POL-ESC-001 "Answer quality": retrieval relevance minimum 0.35 → 0.65.** After the embedding comparison
  (eval/report.md) chose BAAI/bge-small-en-v1.5, the old 0.35 floor (calibrated on all-MiniLM-L6-v2) never fired. Measured on
  1,050 public-data probes and the 32 core cases: 0.65 removes 62 of 128 off-domain answers and loses 0 of 19 correct in-scope
  answers (the weakest scores 0.74). The change followed the documented rule-change path: edit the policy article (here the
  `policies_rn` batch, last_updated 2026-10-06), regenerate/ingest it, update the registry row RETRIEVAL-MIN-01. The saved
  prompts in prompts/ are left as they were sent, so they still show 0.35.
- **2026-10-06 — POL-ESC-001 "Repeated contact": added the 30-day look-back window.** The history check in
  `app/escalation.py` counted conversations from the last 30 days, but that number was written in the code. It now
  comes from the new registry row ESC-REPEAT-02 (`repeat_contact_window_days <= 30`). The article states the window, so
  the row has a cited source. Same rule-change path as above.

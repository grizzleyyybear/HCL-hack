# Batch brief: adv (advanced-feature articles)

Generate exactly 5 help-center articles (doc_type `article`, authority_level 1). Use only facts from the
CloudFlow fact sheet above; never mention SAP or connectors that are not listed.

| ID | Title (exact) | product_versions | last_updated | Must contain |
| --- | --- | --- | --- | --- |
| KB-ADV-003 | Variables and data mapping | ALL | 2025-06-01..2026-09-30 | Variable syntax for trigger, earlier steps, workspace variables, run details; mapping in 4.x and 3.x; rule that a step can only use the trigger and earlier steps; no secrets in variables |
| KB-ADV-005 | Automatic retries for steps | 4.3+ | on or after 2026-06-08 | `## Steps`: Step → Settings → Retries, up to 5 retries; which CF codes are retried (CF-500/503/504/429) and which are not (CF-401/403); retries are not extra runs; versions before 4.3 have none |
| KB-ADV-006 | Single sign-on (SAML) | ALL | 2025-06-01..2026-09-30 | Business and Enterprise only; CF-403 on Free/Pro; 4.x path Admin → Security, 3.x path Settings → Security; owner fallback login; 2FA on all plans |
| KB-ADV-007 | Exporting workflow run history | 4.2+ | 2026-09-10 | `## Steps`: Workflows → select the workflow → Runs tab → Export → CSV or JSON, up to 100,000 rows, any range within plan retention (Free 7, Pro 30, Business 90, Enterprise 365 days); no need to contact support |
| KB-ADV-007-3X | Exporting workflow run history in CloudFlow 3.x | 3.x | after 2025-06-16 | `## Steps`: Settings → Run history → Download CSV; last 30 days, max 10,000 rows, CSV only; points to KB-ADV-007 for 4.2+ |

## Why

- KB-ADV-007 / KB-ADV-007-3X are the version-matching pair (planned conflict case 1): the same question
  must get different, cited steps for a 4.3 account and a 3.8 account. KB-ADV-007 also contradicts the
  outdated ticket TKT-2025-0455 ("email support for a CSV").
- KB-ADV-005 is version-gated (4.3+) so precedence must exclude it for 3.x and 4.2 customers.
- KB-ADV-006 grounds CF-403 / plan-gated feature answers (ticket TKT-2025-0089).
- KB-ADV-003 grounds the variable tickets (TKT-2025-0236, TKT-2026-0157).

## Format rules

- Markdown: one `# <exact title>`, then several short `## ` sections (Overview, Steps or Details,
  Troubleshooting, plus any listed above) and always `## Applies to` last. Headings are cited verbatim,
  so keep them short and plain.
- 250–600 words per article; simple sentences, numbered steps, bold UI labels.
- Output one JSON batch per the batch file contract: `meta` (SourceMeta fields, provenance
  `LLM: <model>, prompt kb-v1`, synthetic `Y`, tags `;`-separated topic keys incl. error codes) + `markdown`.

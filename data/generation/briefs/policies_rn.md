Batch `policies_rn`: the three policy articles and the two release notes (5 documents). Every number must be
identical to the fact sheet, because the policy registry (thresholds read by code) cites these exact sections and
the plan_limits table must equal the policy table.

Policies: doc_type `policy`, authority_level 1, product_versions `ALL`, last_updated between 2025-12-01 and
2026-09-30, effective_from empty (the registry rows take effect on 2026-01-01). Use exactly the required section
headings below (more sections are allowed, such as `## Overview` and `## Applies to`). Write them as clear, formal
policy text, 250-500 words each.

| ID | Title | Required sections and content |
| --- | --- | --- |
| POL-REFUND-001 | Refund policy | `## Refund window`: a charge can be refunded if no more than 14 days have passed since the charge date (day 14 is inside the window, day 15 is outside). `## Eligibility`: paid invoices only (not failed or already refunded); Pro, Business and Enterprise plans; Free has no charges. `## How refunds are processed`: only the billing team approves and issues refunds; support explains eligibility and hands the request over with the invoice details; nobody else promises an outcome. Duplicate charges are handled under KB-BIL-003 |
| POL-LIMITS-001 | Plan limits policy | `## Plan limits`: the fact-sheet plan table with all seven columns. `## When limits are exceeded`: API → HTTP 429 with CF-429 and Retry-After; monthly runs → new runs queued until the next period or an upgrade; seats → no new members until a seat is freed or the plan is upgraded. State that usage exactly at a limit is allowed and a limit is exceeded only when usage goes above it. Measurement: API calls per workspace per minute, runs per calendar month |
| POL-ESC-001 | Support escalation and response times | `## Answer quality`: answers must be grounded in documentation with a groundedness score of at least 0.70, and sources used must have retrieval relevance of at least 0.35; otherwise a human takes over or the assistant says the topic is not covered. `## Response times`: after a handoff, 24 hours for Free and Pro, 4 hours for Business and Enterprise. `## Repeated contact`: 2 or more contacts about the same issue is repeated contact; with strong negative sentiment it goes to a human. `## Always handled by a human`: refunds, credits, billing disputes, legal matters, security incidents, account deletion, and any explicit request for a human |

Release notes: doc_type `release_note`, authority_level 2, last_updated equal to effective_from.

| ID | Title | product_versions | effective_from | Content |
| --- | --- | --- | --- | --- |
| RN-4.2-001 | CloudFlow 4.2 release notes | 4.2+ | 2026-03-10 | New Export button (Workflows → select the workflow → Runs tab → Export → CSV or JSON, up to 100,000 rows, any date range within the plan's retention); 3.x keeps Settings → Run history → Download CSV (last 30 days, max 10,000 rows) |
| RN-4.4-001 | CloudFlow 4.4: webhooks v2 and webhook v1 deprecation | ALL | 2026-09-15 | Webhooks v2 generally available (v2 URL format, HMAC-SHA256 signature in X-CloudFlow-Signature-256, 5 automatic retries with backoff, "Upgrade to v2" action on the webhook trigger); webhooks v1 (HMAC-SHA1 in X-CloudFlow-Signature) deprecated with 4.4; v1 endpoints stop accepting deliveries on 2026-12-01 and from then return HTTP 410 Gone; 3.x and 4.0-4.3 customers must upgrade to 4.4 to use v2 before that date; migration checklist; links to KB-API-007 and KB-API-008 |

Webhook model shared with batch api_trb: a webhook is a CloudFlow URL that another app calls to start a run; the
sending app signs the raw body with the webhook's signing secret and CloudFlow verifies the signature.

Tags: semicolon topic keys, for example `policy;refund;billing` or `release-note;webhooks;deprecation;4.4`.

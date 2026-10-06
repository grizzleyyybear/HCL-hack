Batch `gs_bil`: getting-started and billing help-center articles (11 documents, doc_type `article`,
authority_level 1). Audience: new CloudFlow admins and account owners. Each article is 250-600 words, starts with
`# <title exactly as in the manifest>`, uses short `## ` headings, and ends with `## Applies to` stating the plans and
product versions covered. Cross-reference other articles by title and ID, for example
"see *Requesting a refund* (KB-BIL-006)". Example people and companies are synthetic (for example
dana.lee@example.com at "Northwind Labs"). Invoice IDs, if shown, look like INV-1234.

Dates: last_updated between 2025-06-01 and 2026-09-30 and never earlier than the release of the newest feature the
article mentions (4.0 = 2025-09-22, 4.2 = 2026-03-10, 4.3 = 2026-06-08, 4.4 = 2026-09-15).
provenance: "LLM: <model>, prompt kb-v1"; synthetic "Y"; effective_from, deprecated_on, supersedes empty.

| ID | Title | product_versions | Must cover |
| --- | --- | --- | --- |
| KB-GS-001 | What is CloudFlow | ALL | Concepts (workspace, workflow, trigger, step, connector, run, run history, variables, schedules, webhooks, API tokens); the supported connector list; a plans-at-a-glance summary that matches the plan table; 3.x legacy UI vs 4.x top navigation and that 4.4 is the current release |
| KB-GS-002 | Creating your first workflow | 4.0+ | 4.x steps: Workflows → New workflow, choose a trigger, add steps, connect an app under Connectors → Add connector if needed, map fields with variables, test run, turn on; where runs appear (Runs); monthly run limits; per-step retries exist from 4.3 |
| KB-GS-003 | Creating your first workflow in CloudFlow 3.x | 3.x | 3.x steps via the left sidebar; connections under Settings → Connections; run history under Settings → Run history; 3.8 is the final 3.x release (supported until 2027-06-30); 3.x has webhooks v1 only, which stops accepting deliveries on 2026-12-01, so webhook-triggered workflows need 4.4; never disable SSL verification |
| KB-GS-004 | Inviting teammates and managing seats | ALL | Seats per plan (1 / 5 / 25 / 200); invite path in 4.x (Admin → Members) and 3.x (Settings → Members); what happens when all seats are used (remove a member or upgrade; upgrades apply immediately and are prorated); roles are managed by workspace admins (do not invent role names) |
| KB-GS-005 | Understanding triggers, steps and runs | ALL | Trigger types (schedule, webhook, app event, manual); steps run in order; the 300-second step timeout (CF-504); run statuses including queued when the monthly run limit is exceeded; run history retention per plan (7 / 30 / 90 / 365 days); where to see runs in 4.x and 3.x; automatic retries only in 4.3+ |
| KB-BIL-001 | Plans and pricing | ALL | A table identical to the fact-sheet plan table (all seven columns); SSO on Business and Enterprise only; 2FA on all plans; how to choose a plan |
| KB-BIL-002 | How billing works | ALL | Monthly billing on the account's billing day; USD or INR; card payments; invoices show only the last four card digits; invoice statuses paid, failed, refunded; where invoices are (4.x Admin → Billing → Invoices, 3.x Settings → Billing); upgrades immediate and prorated, downgrades on the next billing day |
| KB-BIL-003 | Duplicate charges and billing disputes | ALL | A `## Duplicate charges` section: what a duplicate looks like (two charges, same amount, same day), the billing team verifies and reverses the duplicate, reversals appear in 5-7 business days; how to dispute other charges; support cannot issue refunds or reversals itself and hands the case to billing with the invoice details; handoff response times 24 h (Free, Pro) and 4 h (Business, Enterprise) |
| KB-BIL-004 | Failed payments and past-due accounts | ALL | 3 automatic retries over 7 days; status past_due; unpaid after 14 days → suspended (workflows paused, data kept 30 days); updating the card (4.x Admin → Billing → Payment method, 3.x Settings → Billing → Payment method); common failure reasons such as a declined or expired card; what happens after payment succeeds |
| KB-BIL-005 | Changing or cancelling your plan | ALL | Upgrade (immediate, prorated) and downgrade (next billing day, usage must fit the new plan's seats and limits); cancelling (no further charges, data deleted after 30 days); export run history first; account deletion is a separate request handled by a human with a 30-day grace period; refunds follow POL-REFUND-001 |
| KB-BIL-006 | Requesting a refund | ALL | Summary of POL-REFUND-001: 14 days from the charge date, paid invoices, Pro/Business/Enterprise; Free has no charges; how to ask (invoice ID and reason); only the billing team approves and issues refunds, support explains eligibility and hands over; never promise an outcome; a refunded invoice shows status refunded |

Required headings beyond `## Applies to`: KB-BIL-003 must contain `## Duplicate charges` exactly. Tags: semicolon
topic keys such as `getting-started;workflows;4.x` or `billing;duplicate-charge;dispute`.

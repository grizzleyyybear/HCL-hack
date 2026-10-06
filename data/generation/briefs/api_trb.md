# Batch brief: api_trb (API, integrations and troubleshooting articles)

This brief is part of the saved generation prompt for batch `api_trb`. The full prompt is:
`data/generation/cloudflow_facts.md` (facts + manifest + batch file contract) + this brief + the output schema.

## Task for the generator

Write **18 CloudFlow help-center articles** (doc_type `article`, authority_level 1) and return them as ONE
JSON object in the batch file contract shape:

```json
{"batch": "api_trb", "prompt_file": "data/generation/prompts/api_trb.md",
 "model": "<model>", "temperature": "<value or n/a>",
 "documents": [{"meta": {<all SourceMeta fields>}, "markdown": "# <title>\n\n## ...\n..."}]}
```

## Rules for every article

1. Facts must match `cloudflow_facts.md` exactly. Do not invent plan limits, error codes, connectors,
   versions or dates. Where the sheet is silent, keep invented UI detail small and plausible, and never
   contradict the sheet.
2. Markdown: first line `# <exact manifest title>`, then 3+ `## ` sections. Headings are short (1-5 words)
   because citations quote them verbatim. No line inside a code block may start with `#`.
3. Length 250-700 words. Specific, numbered steps; real menu paths per version:
   4.x top navigation **Workflows / Connectors / Runs / Admin**; 3.x left-sidebar **Settings**.
   Re-authorise a connector: 4.x Connectors → select connector → Re-authorise; 3.x Settings → Connections → Reconnect.
   API tokens: 4.x Admin → API tokens; 3.x Settings → API tokens.
4. Every article ends with a `## Applies to` section naming versions and plans.
5. Tokens only as placeholders `cf_live_XXXX...` (never 16+ characters after the prefix). Emails only
   `@example.com` (preferably none at all). Never mention SAP or any connector not on the sheet.
6. Support (human or assistant) never shows reset links, tokens or emails in chat, never asks for a
   token or password, and never promises refunds or account changes.
7. Webhook model used across this batch: a webhook is a CloudFlow URL that another app calls to start a
   run; the sending app signs the raw body with the webhook's signing secret (v1: HMAC-SHA1 hex digest in
   `X-CloudFlow-Signature`; v2: HMAC-SHA256 hex digest in `X-CloudFlow-Signature-256`); CloudFlow verifies
   it and records accepted/rejected deliveries in the webhook's delivery log. v2 queues accepted deliveries
   and retries starting the run up to 5 times with backoff; v1 has no automatic retries. From 2026-12-01
   v1 URLs return HTTP 410 Gone.

## Meta rules

- `doc_type` "article", `authority_level` 1, `synthetic` "Y",
  `provenance` "LLM: claude-opus-5-5 (Claude Code subagent), prompt kb-v1".
- `last_updated` between 2025-06-01 and 2026-09-30 and not earlier than any feature the article
  mentions (4.0: 2025-09-22, 4.2: 2026-03-10, 4.3: 2026-06-08, 4.4: 2026-09-15; overlap rotation 2026-03-01).
- `effective_from`, `deprecated_on`, `supersedes` empty unless stated below.
- `tags`: semicolon-separated lowercase topic keys plus every error code the article covers (e.g. `salesforce;connector;CF-503`).

## Documents

| ID | Title | product_versions | last_updated | Special meta | Required sections | Facts it must state |
| --- | --- | --- | --- | --- | --- | --- |
| KB-API-001 | API overview and authentication | ALL | 2026-04-14 | | Overview, API tokens, Creating a token, Making a request, Rate limits, Keeping tokens safe, Applies to | Base URL `https://api.cloudflow.example/v2`; `Authorization: Bearer <token>`; `cf_live_`/`cf_test_` + 32 chars, shown once; CF-401/CF-403 meaning; plan rate limits; leaked token → revoke, security team |
| KB-API-002 | Connecting Salesforce | ALL | 2026-05-20 | | Overview, Before you start, Steps in CloudFlow 4.x, Steps in CloudFlow 3.x, Troubleshooting, Applies to | OAuth; dedicated integration user (password change ends authorisation → CF-503); 4.x and 3.x connect/re-authorise paths; never disable SSL checks |
| KB-API-003 | Slack and Microsoft Teams connectors | ALL | 2026-02-11 | | Overview, Connecting Slack, Connecting Microsoft Teams, Building messages, Troubleshooting, Applies to | Invite app to private channels; Teams admin consent; workspace rename → re-authorise (anchors TKT-2025-0548); revoked → CF-503 |
| KB-API-005 | API rate limits and 429 errors | ALL | 2026-08-20 | | Overview, Limits by plan, What a 429 looks like, How to handle 429 errors, Checking your usage, Applies to | **Current** limits Free 60 / Pro 300 / Business 1,000 / Enterprise 5,000 per workspace per minute; HTTP 429 + CF-429 + `Retry-After`; backoff 1 s doubling to 32 s; no tight loops; batch; upgrade applies immediately; older answers quoting 120/min for Pro are out of date |
| KB-API-007 | Webhooks v1 (legacy) | ALL | 2026-09-15 | deprecated_on 2026-12-01 | Overview, Deprecation, How v1 works, Signing a delivery, Limitations, Finding your v1 webhooks, Applies to | v1 URL format; HMAC-SHA1; no retries; deprecated in 4.4 (2026-09-15); stops accepting deliveries 2026-12-01; move to v2, which needs 4.4 |
| KB-API-008 | Webhooks v2 | 4.4+ | 2026-09-15 | | Overview, What changed from v1, Signing deliveries, Retries, Migrating from v1, Applies to | v2 URL; HMAC-SHA256 in `X-CloudFlow-Signature-256`; 5 retries with backoff; migration steps; 3.x and 4.0-4.3 must upgrade to 4.4 before 2026-12-01 |
| KB-API-009 | Rotating API tokens | ALL | 2025-11-03 | | Overview, Steps, What to expect, Tips, Troubleshooting, Applies to | OLD procedure: revoke the old token first, then create and deploy a new one; CF-401 errors until deployed. Written before the overlap method existed, so it must not mention it |
| KB-API-010 | Google Sheets and HubSpot connectors | ALL | 2026-07-20 | | Overview, Connecting Google Sheets, Google Sheets quotas, Connecting HubSpot, Mapping HubSpot fields, Troubleshooting, Applies to | Google provider quota is not CF-429; batch rows (anchors TKT-2025-0168, COM-0006); HubSpot custom properties by internal name (anchors TKT-2025-0236); step retries need 4.3+ |
| KB-API-012 | Rotating API tokens with an overlap window | ALL | 2026-03-01 | effective_from 2026-03-01; supersedes KB-API-009 | Overview, Steps, Why the overlap window matters, If a token has leaked, Troubleshooting, Applies to | Create new → deploy → keep both active for a 24-hour overlap window → revoke old; replaces the revoke-first method, which caused downtime (contradicts TKT-2024-0918) |
| KB-TRB-001 | Error code reference | ALL | 2026-07-08 | | Overview, Error codes, Detailed guides, Where to find the code, Before contacting support, Applies to | Full table CF-401, CF-403, CF-429, CF-500, CF-503, CF-504 with the sheet's meanings and fixes; platform status components api, workflow-engine, connectors, billing |
| KB-TRB-002 | Fixing CF-401 authentication errors | ALL | 2026-03-05 | | Overview, Common causes, Steps, Avoiding CF-401 in future, When it is not the token, Applies to | Invalid/expired/revoked token; header format; create a new token with the overlap method (anchors TKT-2025-0047) |
| KB-TRB-003 | Fixing CF-403 permission errors | ALL | 2026-04-22 | | Overview, Check which cause applies, Fixing a role problem, Fixing a plan problem, Still seeing CF-403?, Applies to | Role vs plan; admin grants roles; SSO needs Business or Enterprise (anchors TKT-2025-0089); 2FA on all plans; upgrades immediate and prorated |
| KB-TRB-004 | Salesforce step fails with CF-503 | ALL | 2026-06-30 | | Overview, Check platform status first, **Steps in CloudFlow 4.x**, **Steps in CloudFlow 3.x**, Never disable SSL verification, Preventing repeat failures, Applies to | Expired/revoked Salesforce authorisation (password change, session policy); 4.x Re-authorise, 3.x Reconnect; connectors degraded → wait; **never disable SSL verification**; "Allow insecure SSL" existed only in 3.0-3.3, removed in 3.4; old ticket advice is outdated (contradicts TKT-2025-0142 and COM-0004) |
| KB-TRB-005 | Fixing CF-504 step timeouts | ALL | 2026-07-15 | | Overview, Find the slow step, Fixes, Example, What does not help, Applies to | 300-second per-step limit; pagination, split step, async mode in the HTTP step (anchors TKT-2025-0331) |
| KB-TRB-006 | CF-500 internal errors | ALL | 2026-07-01 | | Overview, Steps, Reducing the impact, What to include when you contact support, Applies to | Retry once; check platform status; contact support with the run ID; step retries up to 5 (4.3+) |
| KB-TRB-007 | Webhook deliveries failing | ALL | 2026-09-18 | | Overview, Check the delivery log, Signature mismatches, v1 URLs after 2026-12-01, Accepted but no run, Applies to | v1 vs v2 signature table; raw-body signing; v1 stops 2026-12-01 (410 Gone); paused workflows; run limit queueing (anchors TKT-2024-0963) |
| KB-TRB-008 | Workflows not running on schedule | ALL | 2026-02-03 | | Overview, Time zones and daylight saving, Paused workflows, Monthly run limits, Other checks, Applies to | Named time zone vs fixed offset (anchors TKT-2024-0857); suspended accounts pause workflows; runs over the monthly limit are queued (Free 500, Pro 10,000, Business 50,000, Enterprise 500,000) |
| KB-TRB-009 | Login problems and password resets | ALL | 2026-08-04 | | Overview, Resetting your password, Reset email not arriving, Two-factor authentication, Single sign-on users, If you think your account is compromised, Applies to | Forgot password; reset email to the owner email on file; links expire after 30 minutes; spam folder (anchors TKT-2025-0290); support never shares links, tokens or emails in chat; lost 2FA → security team (anchors TKT-2025-0846); compromise → security team, revoke tokens |

## Conflict cases this batch anchors (docs must win)

| Planned case | Article (authority 1) | Contradicted source |
| --- | --- | --- |
| CF-503 Salesforce failure | KB-TRB-004 (re-authorise; never disable SSL) | TKT-2025-0142 (disable SSL verification), COM-0004 |
| API rate limit 429 | KB-API-005 (Pro 300/min, Retry-After + backoff) | TKT-2025-0201 (Pro 120/min), COM-0003 (retry immediately in a loop) |
| Deprecation | KB-API-007 deprecated_on 2026-12-01; KB-API-008 4.4+ | RN-4.4-001 announces it; before 2026-12-01 v1 is an upcoming change |
| Supersession | KB-API-012 supersedes KB-API-009 from 2026-03-01 | KB-API-009, TKT-2024-0918 (revoke first) |

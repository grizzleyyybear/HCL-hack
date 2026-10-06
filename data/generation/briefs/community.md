# Batch brief: community (forum posts, untrusted)

Generate exactly 6 community posts COM-0001..COM-0006 (doc_type `community`, authority_level 5,
product_versions `ALL`), titles exactly as in the fact sheet (without the quotation marks).

Format: Markdown with `# <title>`, a one-line byline with synthetic forum handles, then `## Question` and
`## Accepted answer`. 120–300 words each, written in a casual forum voice.

| ID | Title | Advice |
| --- | --- | --- |
| COM-0001 | Formatting Slack messages with blocks | Sensible: Slack step Blocks format, Insert variable, plain-text fallback, Test step |
| COM-0002 | Workaround for schedules across time zones | Sensible: one schedule per office with a named time zone; UTC does not follow daylight saving |
| COM-0003 | Just retry 429s immediately in a loop | **Wrong, stated confidently**: ignore `Retry-After`, retry in a tight loop with no delay, run copies in parallel. Contradicts KB-API-005 |
| COM-0004 | Disable SSL verification to fix CF-503 | **Wrong, stated confidently**: turn on "Allow insecure SSL" / disable certificate verification and leave it off. Contradicts KB-TRB-004 |
| COM-0005 | Tips for moving webhooks to v2 | Sensible and consistent with the fact sheet and api_trb batch: 4.4+, "Upgrade to v2" action and new v2 URL, senders sign the raw body (v1 SHA1 hex in `X-CloudFlow-Signature`, v2 SHA256 in `X-CloudFlow-Signature-256`), 5 retries so tolerate duplicates, Deliveries log, v1 returns 410 Gone from 2026-12-01 |
| COM-0006 | Batching rows into Google Sheets | Sensible: provider quota is not CF-429; collect then append many rows on a schedule |

Tags use the same topic keys as the matching articles (e.g. `api;rate-limit;CF-429`,
`salesforce;connector;CF-503;ssl`) so precedence pairs each post with the authoritative doc.

## Why

Community content is authority level 5 (untrusted). The two wrong posts prove that level 5 is never
authoritative: precedence must drop them in favour of KB-API-005 and KB-TRB-004 and record the conflict,
and the composer must never repeat their advice. The sensible posts add realistic, non-conflicting detail.
If `data/public/themes.json` exists, use its recurring real-world problem themes (auth expiry, webhook retries,
rate limiting, timeouts) to shape the questions; paraphrase, never copy, and add "; tone/themes from
data/public" to provenance. Synthetic handles only, no real usernames, no SAP, no unlisted connectors.

# Article structure templates

Provenance: structure modelled on public Stripe/Twilio help-center conventions; no text copied.
Nothing on this page was scraped or pasted. It describes, in our own words, the layout patterns that
well-run developer help centers use, so the CloudFlow KB generator (scripts/generate_kb.py) can ask
for the same shape. Section headings are short because the API cites them exactly (`section` must
equal the real `##` heading).

## 1. API or integration article

Use for KB-API-* articles (authentication, connectors, webhooks, rate limits).

```
# <Task-oriented title, e.g. "API rate limits and 429 errors">

## Overview
Two or three sentences: what this feature is, who needs it, which plans and versions it applies to.

## Before you start
Bullet list of prerequisites: role needed, plan needed, product version, anything to create first.

## Steps
Numbered steps, one action per step, using the exact UI labels in bold
(4.x: top navigation; 3.x: left-sidebar Settings). If 3.x and 4.x differ, use two sections instead:
"## Steps in CloudFlow 4.x" and "## Steps in CloudFlow 3.x".

## Example
One short request/response or configuration sample with placeholder values only
(cf_live_XXXX..., https://api.cloudflow.example/v2/...). Never a real-looking token.

## Limits
A small table of numeric limits (per plan when they vary). Numbers must equal the policy registry.

## Troubleshooting
Two to four "Symptom - cause - fix" bullets, each pointing to the matching error-code article.

## Applies to
Plans and product versions covered, e.g. "All plans. CloudFlow 4.2 and later."
```

Rate-limit articles add a "## Handling 429 responses" section between Limits and Troubleshooting:
honour the Retry-After header first, otherwise exponential backoff with a cap, batch requests, and
upgrade as the last option. State explicitly what not to do (tight retry loops).

## 2. Troubleshooting article (one error code)

Use for KB-TRB-002 to KB-TRB-009.

```
# Fixing <code> <short meaning>

## Overview
What the customer sees (error code, message text, where it appears: run history, API response).

## Common causes
Bulleted, most likely cause first.

## Steps
Numbered fix, most likely cause first. Version-specific paths in separate sections if they differ.

## What not to do
Unsafe or outdated workarounds that must never be suggested (for example, disabling SSL verification).

## Still not working
When to check platform status, and what to send support (run ID, time, connector), never secrets.

## Applies to
```

## 3. Error-code reference table

Use for KB-TRB-001. One table, one row per code, sorted by code, so the retriever returns the whole
table as one chunk per section.

| Code | HTTP status | Meaning | Typical cause | What to do | Details |
| --- | --- | --- | --- | --- | --- |
| CF-4xx / CF-5xx | numeric | one short phrase | one short phrase | one imperative sentence | KB article ID |

Rules: the "What to do" cell is a single action; longer fixes live in the linked article. Retryable
codes (429, 500, 503, 504) are marked "(retryable)" in the Meaning cell.

## 4. Account and billing FAQ article

Use for KB-BIL-* articles and policy articles' customer-facing wording. Question-led sections,
each answered in the first sentence, then detail.

```
# <Topic, e.g. "Duplicate charges and billing disputes">

## Overview
One paragraph: what this page covers and who can act on it (account owner, billing team).

## <Question phrased as the customer would ask it, kept short as a heading>
First sentence answers the question directly. Then 2-4 sentences or bullets of detail.
Point to the policy article for numbers (refund window, SLAs) instead of repeating them loosely.

## <Next question>
...

## What support can and cannot do
Explicit list: support explains eligibility and hands off to billing; only the billing team approves
refunds, credits or reversals.

## Applies to
```

Billing pages always end with the human-only actions, because the assistant must never promise a
refund or credit.

## 5. Policy article

Use for POL-* articles. Fixed headings (the policy registry cites them as `source_section`), one rule
per section, the numeric value in the first sentence so the registry row and the text never drift.

## 6. Release note with a deprecation

Use for RN-* articles: "## Highlights", "## Changes", "## Deprecations" (each with the exact date the
change takes effect and what customers must do before it), "## Upgrade notes", "## Applies to".

# Webhook deliveries failing

## Overview

When another app calls a CloudFlow webhook URL and no run starts, the delivery was either rejected or could not start the workflow. The most common causes are a signature that does not match, a v1 URL used after the v1 shutdown, or a paused workflow. Start with the delivery log.

## Check the delivery log

- CloudFlow 4.x: **Workflows** → select the workflow → open the webhook trigger → **Deliveries**.
- CloudFlow 3.x: **Settings → Webhooks** → select the webhook → **Deliveries**.

Each delivery shows when it arrived and whether it was accepted or rejected, with the reason.

## Signature mismatches

Webhooks v1 and v2 sign deliveries differently. A sender using the wrong method is rejected with "Signature mismatch".

| | Webhooks v1 | Webhooks v2 (4.4+) |
| --- | --- | --- |
| URL | `https://hooks.cloudflow.example/v1/<id>` | `https://hooks.cloudflow.example/v2/<id>` |
| Algorithm | HMAC-SHA1 | HMAC-SHA256 |
| Header | `X-CloudFlow-Signature` | `X-CloudFlow-Signature-256` |
| Automatic retries | None | 5, with backoff |

Check, in order:

1. The algorithm and header match the URL version. A SHA-1 signature sent to a v2 URL always fails.
2. The secret is the current one. Upgrading a webhook to v2 or regenerating its secret creates a new secret, and the old one stops matching.
3. The signature is computed over the exact raw body that is sent. Parsing and re-serialising the JSON, or changing whitespace or character encoding after signing, breaks the match.
4. The digest is sent as lowercase hex.

## v1 URLs after 2026-12-01

Webhooks v1 stops accepting deliveries on **2026-12-01**. From then on, calls to `/v1/` URLs return HTTP 410 Gone and no run starts. Move to Webhooks v2 before that date. v2 needs CloudFlow 4.4, so 3.x and 4.0-4.3 customers must upgrade first. See "Webhooks v2" for the migration steps.

## Accepted but no run

- **Workflow paused:** check that the workflow is switched on. When an account is suspended, all its workflows are paused.
- **Monthly run limit reached:** runs over the plan's monthly allowance are queued until the next period or an upgrade.
- **Temporary error:** v2 retries up to 5 times automatically, and each attempt shows in the delivery log. v1 does not retry, so the sender must resend.

## Applies to

All plans, CloudFlow 3.x and 4.x. Webhooks v2 needs CloudFlow 4.4 or later.

# Webhooks v2

## Overview

Webhooks v2 is the current way to start a workflow from another app with an HTTP call. It became generally available in CloudFlow 4.4 (2026-09-15) and replaces Webhooks v1, which stops accepting deliveries on 2026-12-01. Each v2 webhook has a URL of the form `https://hooks.cloudflow.example/v2/<id>` and its own signing secret.

## What changed from v1

| | Webhooks v1 | Webhooks v2 |
| --- | --- | --- |
| URL | `hooks.cloudflow.example/v1/<id>` | `hooks.cloudflow.example/v2/<id>` |
| Signature | HMAC-SHA1 in `X-CloudFlow-Signature` | HMAC-SHA256 in `X-CloudFlow-Signature-256` |
| Automatic retries | None | 5, with backoff |
| Versions | 3.x, 4.0-4.4 | 4.4 and later |
| Status | Deprecated; stops 2026-12-01 | Current |

## Signing deliveries

The sending app signs the raw request body with HMAC-SHA256 using the webhook's signing secret and sends the lowercase hex digest in the `X-CloudFlow-Signature-256` header:

```
import hmac, hashlib
signature = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
headers = {"X-CloudFlow-Signature-256": signature}
```

CloudFlow rejects deliveries with a missing or wrong signature and records them in the webhook's delivery log.

## Retries

CloudFlow queues every accepted v2 delivery. If a temporary error stops the run from starting, CloudFlow retries automatically up to 5 times with increasing delays. Each attempt appears in the delivery log, so you can see whether a delivery succeeded on a retry. Deliveries rejected for a bad signature are not retried, because the same request would fail the same way.

## Migrating from v1

1. Make sure the workspace is on CloudFlow 4.4. Customers on 3.x or 4.0-4.3 must upgrade first.
2. Open **Workflows**, select the workflow and open its webhook trigger.
3. Select **Upgrade to v2**. CloudFlow creates a v2 URL and a new signing secret. The v1 URL keeps working until 2026-12-01, so both can run side by side during the move.
4. Update the sending app: send to the v2 URL and sign with HMAC-SHA256 in `X-CloudFlow-Signature-256` using the new secret.
5. Send a test delivery and check that it shows as accepted in the delivery log.
6. When all senders use v2, remove the v1 URL from the trigger.

Complete the move before 2026-12-01. After that date, v1 URLs return HTTP 410 Gone.

## Applies to

CloudFlow 4.4 and later, all plans.

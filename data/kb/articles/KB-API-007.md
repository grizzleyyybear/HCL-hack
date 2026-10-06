# Webhooks v1 (legacy)

## Overview

A webhook gives a workflow a URL that other apps can call to start a run. Webhooks v1 is the original version, available in CloudFlow 3.x and 4.0-4.4. Each v1 webhook has a URL of the form `https://hooks.cloudflow.example/v1/<id>` and a signing secret.

## Deprecation

Webhooks v1 was deprecated with CloudFlow 4.4 on 2026-09-15. **On 2026-12-01, v1 URLs stop accepting deliveries.** From that date, calls to a v1 URL are rejected with HTTP 410 Gone and no run starts.

Until then, v1 webhooks keep working as described below. To keep your integrations running, move each webhook to Webhooks v2 before 2026-12-01. Webhooks v2 needs CloudFlow 4.4, so customers on 3.x or 4.0-4.3 must upgrade to 4.4 first. See "Webhooks v2" for the migration steps.

## How v1 works

1. The sending app makes an HTTP POST to the webhook URL with a JSON body.
2. It signs the raw request body with HMAC-SHA1 using the webhook's signing secret and sends the hex digest in the `X-CloudFlow-Signature` header.
3. CloudFlow checks the signature. If it matches, the delivery is accepted and a run starts with the body available as trigger data. If it does not match, the delivery is rejected.

## Signing a delivery

```
import hmac, hashlib
signature = hmac.new(secret.encode(), raw_body, hashlib.sha1).hexdigest()
headers = {"X-CloudFlow-Signature": signature}
```

Sign the exact bytes you send. Re-serialising the JSON after signing changes the bytes and causes a signature mismatch.

## Limitations

- **No automatic retries.** If a temporary error stops the run from starting, the delivery is dropped and the sending app must send it again.
- **SHA-1 signatures.** HMAC-SHA1 is weaker than the HMAC-SHA256 used by Webhooks v2.
- **Shutdown date.** v1 stops accepting deliveries on 2026-12-01.

## Finding your v1 webhooks

- CloudFlow 4.x: **Workflows** → select the workflow → open the webhook trigger. A v1 URL shows `/v1/` in its path.
- CloudFlow 3.x: **Settings → Webhooks** lists every webhook in the workspace.

## Applies to

CloudFlow 3.x and 4.0-4.4, all plans, until 2026-12-01. After that date this guidance no longer applies; use Webhooks v2.

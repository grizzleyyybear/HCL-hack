# CloudFlow 4.4: webhooks v2 and webhook v1 deprecation

## Overview

CloudFlow 4.4 was released on 2026-09-15. It makes **webhooks v2** generally available and deprecates **webhooks v1**. Webhook v1 endpoints stop accepting deliveries on **2026-12-01**. If any of your workflows start from a v1 webhook, plan the move to v2 now.

## Webhooks v2

A webhook is a CloudFlow URL that another app calls to start a run. Webhooks v2 is available on CloudFlow 4.4 and later:

- **URL format:** `https://hooks.cloudflow.example/v2/<id>`
- **Signature:** the sending app signs the raw request body with the webhook's signing secret using HMAC-SHA256 and sends the result in the `X-CloudFlow-Signature-256` header. CloudFlow verifies it before accepting the delivery.
- **Automatic retries:** if an accepted delivery cannot start its run, CloudFlow retries up to 5 times with backoff.

See *Webhooks v2* (KB-API-008).

## Webhook v1 deprecation

- Webhooks v1 (`https://hooks.cloudflow.example/v1/<id>`, HMAC-SHA1 signature in the `X-CloudFlow-Signature` header, no automatic retries) is deprecated as of 4.4.
- Until 2026-12-01, v1 endpoints keep working as before.
- From **2026-12-01**, v1 endpoints stop accepting deliveries and return **HTTP 410 Gone**. Workflows that are triggered only by a v1 webhook will no longer start.

See *Webhooks v1 (legacy)* (KB-API-007).

## What you need to do

1. **Check your version.** Webhooks v2 needs CloudFlow 4.4. Workspaces on 3.x or on 4.0 to 4.3 must upgrade to 4.4 before 2026-12-01.
2. **Find your v1 webhooks.** List every workflow whose trigger uses a `/v1/` URL.
3. **Upgrade each trigger.** Open the workflow, select the webhook trigger and choose **Upgrade to v2**. Note the new v2 URL and signing secret.
4. **Update the sending apps** to call the v2 URL and to sign deliveries with HMAC-SHA256 in `X-CloudFlow-Signature-256`.
5. **Test** a delivery and confirm that a run starts.
6. **Stop using the v1 URL** once the v2 webhook works, and in any case before 2026-12-01.

## Applies to

All plans. All product versions: 4.4 adds webhooks v2, and the v1 shutdown on 2026-12-01 affects every version, including 3.x and 4.0 to 4.3.

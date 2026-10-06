# Automatic retries for steps

## Overview

From CloudFlow 4.3, each step can retry itself automatically when it fails with a temporary error. A short outage at a connected app or a brief rate limit then no longer fails the whole run. Each step can retry up to 5 times.

## Steps

1. Open **Workflows** and select the workflow.
2. Click the step you want to protect.
3. Open **Settings → Retries**.
4. Set **Number of retries** to a value from 0 to 5. The default is 0, which means retries are off.
5. Choose the **Delay** between attempts: **Fixed** waits the same time before every attempt; **Exponential** doubles the wait after each attempt.
6. Save and publish the workflow.

## Which errors are retried

| Error | Retried | Why |
| --- | --- | --- |
| CF-500 internal error | Yes | Usually temporary |
| CF-503 connector unavailable | Yes | Helps during a short connector incident |
| CF-504 step timeout | Yes | Helps when the connected app was briefly slow |
| CF-429 rate limit exceeded | Yes | The wait honours the `Retry-After` header |
| CF-401 authentication failed | No | A retry cannot fix an invalid or expired token |
| CF-403 permission denied | No | A retry cannot change a role or plan |

If a step still fails with CF-503 after all retries, the connector most likely needs to be re-authorised (see "Salesforce step fails with CF-503"). If CF-504 keeps happening, split the step or use pagination.

## How retries are counted

Retries happen inside the same run. Run history shows each attempt under the step, and a retry does not count as an extra workflow run towards your monthly limit. Attempts that call the CloudFlow API do count towards your plan's API calls per minute.

## Tips

- Make repeated steps safe. A "create record" step can create a duplicate if the first attempt succeeded at the connected app but timed out in CloudFlow. Search for an existing record first, then create only if none is found.
- Prefer **Exponential** delay for rate limits and outages, so attempts spread out instead of piling up.
- Keep the number of retries low for steps that send messages, so customers are not notified several times.

## Earlier versions

Versions before 4.3, including all 3.x releases, have no per-step retry settings. Upgrade to 4.3 or later to use automatic retries.

## Applies to

CloudFlow 4.3 and later, all plans.

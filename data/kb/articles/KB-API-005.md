# API rate limits and 429 errors

## Overview

CloudFlow limits how many API calls a workspace can make per minute. The limit depends on your plan and is shared by every token in the workspace. When you go over it, the API returns **HTTP 429** with error code **CF-429** and a `Retry-After` header. Calls succeed again once the current minute has room.

## Limits by plan

These are the current limits:

| Plan | API calls per minute (per workspace) |
| --- | --- |
| Free | 60 |
| Pro | 300 |
| Business | 1,000 |
| Enterprise | 5,000 |

The same numbers appear in the Plan limits policy. Older support answers that quoted different figures, such as 120 calls per minute on Pro, are out of date; always use the table above.

API rate limits are separate from the monthly workflow-run allowance. Going over your monthly runs does not cause 429 errors; extra runs are queued until the next period or an upgrade.

## What a 429 looks like

```
HTTP/1.1 429 Too Many Requests
Retry-After: 12

{"error": {"code": "CF-429", "message": "Rate limit exceeded"}}
```

`Retry-After` is the number of seconds to wait before trying again.

## How to handle 429 errors

1. **Honour Retry-After.** Wait at least the number of seconds in the header before retrying the same call.
2. **Otherwise back off exponentially.** If no header is present, wait 1 second, then 2, 4, 8, 16 and finally 32 seconds between attempts, and stay at 32 seconds after that.
3. **Never retry in a tight loop.** Immediate retries with no delay keep the workspace over its limit and make the errors last longer.
4. **Batch requests.** Send records in groups rather than one call per record, and cache data you read often.
5. **Spread scheduled jobs.** Several integrations firing at the top of the hour share one per-minute budget.
6. **Upgrade if you need more.** Upgrades apply immediately, so the higher limit is available straight away.

A simple retry loop:

```
delay = 1
for attempt in range(8):
    response = call_api()
    if response.status_code != 429:
        break
    wait = int(response.headers.get("Retry-After", delay))
    time.sleep(wait)
    delay = min(delay * 2, 32)
```

## Checking your usage

CloudFlow support can look up your workspace's peak API calls per minute for the current month and compare it with your plan's limit. If the peak is above the limit, the 429 errors are expected, and the steps above or an upgrade will fix them. If the peak is below the limit, contact support with the time of the errors.

## Applies to

All plans, CloudFlow 3.x and 4.x. Limits apply per workspace, per minute.

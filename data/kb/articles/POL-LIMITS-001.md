# Plan limits policy

## Overview

This policy sets the usage limits of each CloudFlow plan. The values in the table below are binding: billing, support answers and the account tools used by support all use exactly these numbers.

## Plan limits

| Plan | API calls / min | Workflow runs / month | Seats | Support tier | Price / month | Run history retention |
| --- | --- | --- | --- | --- | --- | --- |
| Free | 60 | 500 | 1 | standard | $0 | 7 days |
| Pro | 300 | 10,000 | 5 | standard | $49 | 30 days |
| Business | 1,000 | 50,000 | 25 | priority | $199 | 90 days |
| Enterprise | 5,000 | 500,000 | 200 | priority | $999 | 365 days |

## How usage is measured

- **API calls** are counted per workspace per minute, across all API tokens in the workspace.
- **Workflow runs** are counted per workspace per calendar month. Each execution of a workflow is one run.
- **Seats** are the number of members in the workspace.

Reaching a limit exactly is allowed. A limit is exceeded only when usage goes **above** it. For example, a Pro workspace may complete 10,000 runs in a month; the 10,001st run is over the limit. A peak of 300 API calls in a minute is within the Pro limit; 301 is over it.

## When limits are exceeded

- **API rate limit:** requests above the plan's calls per minute receive **HTTP 429** with error code **CF-429** and a `Retry-After` header. Clients should wait for the time given in `Retry-After`, or back off exponentially. See *API rate limits and 429 errors* (KB-API-005).
- **Monthly workflow runs:** new runs are **queued** until the next period starts or the workspace upgrades.
- **Seats:** no new members can be invited until a seat is freed or the plan is upgraded.

Upgrades apply immediately and are prorated, so higher limits are available as soon as an upgrade is confirmed. See *Changing or cancelling your plan* (KB-BIL-005).

## Applies to

All plans and all product versions.

# CF-500 internal errors

## Overview

Error **CF-500** means something went wrong inside CloudFlow while handling an API call or running a step. It is not caused by your token, role or data format. Most CF-500 errors are brief and succeed on a retry.

## Steps

1. **Retry once.** Re-run the failed run, or repeat the API call after a few seconds. In CloudFlow 4.x open **Runs**, select the run and choose **Re-run**; in CloudFlow 3.x open **Settings → Run history** and run it again.
2. **If it fails again, check platform status.** The CloudFlow status page lists four components: **api**, **workflow-engine**, **connectors** and **billing**. If the relevant component shows degraded or outage, an incident is in progress; wait for it to clear before retrying.
3. **If status is operational and the error persists, contact support** with the run ID, or for API calls the time of the request and the endpoint. The run ID is shown at the top of the run details.

## Reducing the impact

- On CloudFlow 4.3 or later, turn on automatic retries for steps that call other services: open the step, go to **Settings → Retries** and choose up to 5 retries. Brief internal errors then recover without manual re-runs.
- In your own API clients, retry a CF-500 once after a short delay. Do not retry in a tight loop; that adds load during an incident and can push you over your rate limit (CF-429).

## What to include when you contact support

- The error code (CF-500) and the run ID
- The workflow name and the step that failed
- When it started, and whether it happens every time or only sometimes

Never include API tokens or passwords in your message. Support does not need them to investigate.

## Applies to

All plans, CloudFlow 3.x and 4.x. Automatic step retries need CloudFlow 4.3 or later.

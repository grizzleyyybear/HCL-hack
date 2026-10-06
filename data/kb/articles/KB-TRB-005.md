# Fixing CF-504 step timeouts

## Overview

Error **CF-504** means a single step ran for longer than **300 seconds** and CloudFlow stopped it. The limit applies to each step, not to the whole workflow, and it is the same on every plan. Timeouts usually come from an HTTP step calling a slow endpoint, or from a step that tries to process a very large amount of data in one go.

## Find the slow step

- CloudFlow 4.x: open **Runs**, select the failed run and look at the step marked with CF-504. The run details show how long each step took.
- CloudFlow 3.x: open **Settings → Run history** and select the run.

## Fixes

**1. Use pagination.** If the step fetches a large list, for example thousands of records from an API, fetch it page by page. In the HTTP step, request one page, then follow the next-page token or offset until there are no more pages. Each request finishes well inside the limit.

**2. Split the step.** Break one heavy step into several smaller ones, for example fetch, then transform, then write. Each step gets its own 300-second limit.

**3. Use async mode in the HTTP step.** For an endpoint that starts a long job, open the HTTP step's settings and turn on **Async mode**. CloudFlow sends the request and waits for the remote service to call back on the step's callback URL instead of holding the connection open, so the step does not time out while the job runs.

**4. Reduce the data.** Filter records at the source, for example only records changed since the last run, instead of fetching everything and filtering in CloudFlow.

## Example

A workflow that downloaded 50,000 rows from a reporting API in a single HTTP request failed with CF-504 after 300 seconds. Switching to pages of 1,000 rows made each request take a few seconds, and the run completed.

## What does not help

Retrying a step that timed out usually times out again for the same reason. Automatic step retries (CloudFlow 4.3 or later) are useful for brief errors, not for steps that are simply too slow. Fix the step first, then re-run.

## Applies to

All plans, CloudFlow 3.x and 4.x.

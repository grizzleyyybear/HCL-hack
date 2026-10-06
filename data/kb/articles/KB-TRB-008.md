# Workflows not running on schedule

## Overview

A scheduled workflow can start late, start at the wrong hour, or not start at all. The three most common causes are the schedule's time zone, a paused workflow, and the monthly run limit. Check them in that order.

## Time zones and daylight saving

Every schedule runs in the time zone set on its schedule trigger. New schedules default to UTC.

- If a workflow runs a few hours early or late every day, the time zone is probably wrong. Open the schedule trigger and set the time zone you expect.
- If a workflow shifted by exactly one hour after a daylight-saving change, the schedule uses a fixed UTC offset (such as UTC+1) instead of a named time zone. Choose a named zone such as Europe/London or America/New_York; named zones follow daylight-saving changes automatically.

Where to find it: in CloudFlow 4.x, **Workflows** → select the workflow → open the schedule trigger. In CloudFlow 3.x, open the workflow and select its schedule trigger.

## Paused workflows

- A workflow that is switched off does not run on schedule. Check its on/off switch in the workflow list.
- When an account is **suspended**, for example after an invoice stays unpaid, all workflows are paused. They do not run until the account is active again. See "Failed payments and past-due accounts".

## Monthly run limits

Each plan includes a number of workflow runs per month:

| Plan | Workflow runs per month |
| --- | --- |
| Free | 500 |
| Pro | 10,000 |
| Business | 50,000 |
| Enterprise | 500,000 |

When the limit is exceeded, new runs, including scheduled ones, are **queued** until the next period or until you upgrade. Upgrades apply immediately, so queued runs can start once the higher allowance is active.

## Other checks

- **Run history:** check whether runs started and failed (they appear in run history with an error code) or never started at all. A run that started and failed is a step problem, not a schedule problem; see "Error code reference".
- **Platform status:** if the **workflow-engine** component shows degraded or outage, scheduled runs may start late until the incident clears.

## Applies to

All plans, CloudFlow 3.x and 4.x.

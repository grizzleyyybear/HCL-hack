# Understanding triggers, steps and runs

## Overview

Every CloudFlow workflow is built from three ideas: a **trigger** that starts it, **steps** that do the work, and **runs** that record each execution. Understanding them makes it much easier to build reliable workflows and to troubleshoot them.

## Triggers

A workflow has exactly one trigger:

- **Schedule**: runs at a set time or interval, in the time zone you choose.
- **Webhook**: runs when another system calls the workflow's webhook URL.
- **App event**: runs when something happens in a connected app, such as a new HubSpot contact or a new Zendesk ticket.
- **Manual**: runs when someone starts it by hand.

## Steps

Steps run one after another, in the order shown in the editor. Each step uses a connector, such as Salesforce or Slack, or the generic HTTP step. A step can use variables produced by the trigger or by earlier steps.

A single step may run for at most 300 seconds; a longer step fails with **CF-504**. See *Fixing CF-504 step timeouts* (KB-TRB-005).

On CloudFlow 4.3 and later, a step can retry automatically when it fails (Step → Settings → Retries, up to 5 retries). Earlier versions do not retry steps automatically.

## Runs

A run is one execution of a workflow, from the trigger to the last step. Each run has a status, such as running, succeeded or failed, and shows the input, output and result of every step.

Every run counts toward your plan's monthly workflow runs: Free 500, Pro 10,000, Business 50,000, Enterprise 500,000. When the monthly limit is exceeded, new runs are **queued** until the next period or until you upgrade.

## Run history

Run history keeps past runs for a period that depends on your plan:

| Plan | Run history retention |
| --- | --- |
| Free | 7 days |
| Pro | 30 days |
| Business | 90 days |
| Enterprise | 365 days |

Where to find it:

- **CloudFlow 4.x:** open **Runs** in the top navigation for all workflows, or open a workflow and select its **Runs** tab. From 4.2 you can export runs with the **Export** button; see *Exporting workflow run history* (KB-ADV-007).
- **CloudFlow 3.x:** open **Settings → Run history**; see *Exporting workflow run history in CloudFlow 3.x* (KB-ADV-007-3X).

## Applies to

All plans and product versions. Automatic step retries need CloudFlow 4.3 or later; the Export button needs 4.2 or later.

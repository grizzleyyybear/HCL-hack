# What is CloudFlow

## Overview

CloudFlow is a workflow-automation service. You connect the apps your team already uses, describe what should happen when something changes, and CloudFlow carries out those steps for you every time, keeping a record of each run. A typical workflow might create a Jira issue when a Zendesk ticket is tagged "bug", then post a summary to a Slack channel.

## Key concepts

- **Workspace**: your team's home in CloudFlow. Members, connectors, workflows, API tokens and billing all belong to a workspace.
- **Workflow**: a trigger plus an ordered list of steps.
- **Trigger**: what starts a workflow: a schedule, a webhook call, an event in a connected app, or a manual start.
- **Step**: one action, such as "create a HubSpot contact" or "call this URL". Steps run in order.
- **Connector**: an authorised link between your workspace and an external app.
- **Run**: one execution of a workflow. Every run is recorded in **run history** with its status and the result of each step.
- **Variables**: values passed between steps, for example an email address from the trigger that a later step uses.
- **Schedules**, **webhooks** and **API tokens**: ways to start workflows on a timetable, from another system, or from your own code through the CloudFlow API.

## Supported connectors

CloudFlow connects to Salesforce, HubSpot, Slack, Microsoft Teams, Google Sheets, Jira, Zendesk, Stripe and PostgreSQL. A generic HTTP step lets a workflow call any service that offers a web API.

## Plans at a glance

| Plan | API calls / min | Workflow runs / month | Seats | Price / month |
| --- | --- | --- | --- | --- |
| Free | 60 | 500 | 1 | $0 |
| Pro | 300 | 10,000 | 5 | $49 |
| Business | 1,000 | 50,000 | 25 | $199 |
| Enterprise | 5,000 | 500,000 | 200 | $999 |

Support tiers, run history retention and single sign-on also differ by plan. See *Plans and pricing* (KB-BIL-001) for the full table.

## Product versions

CloudFlow 4.4, released on 2026-09-15, is the current release. Versions 4.0 and later use a top navigation bar with **Workflows**, **Connectors**, **Runs** and **Admin**. Version 3.x uses the legacy interface, where most administration lives under **Settings** in the left sidebar. CloudFlow 3.8 is the final 3.x release and is supported until 2027-06-30.

Help articles state the versions they cover in their *Applies to* section. Some tasks, such as exporting run history, have separate articles for 3.x and 4.x because the menus differ.

## Applies to

All plans. All product versions (3.x and 4.x).

# Creating your first workflow in CloudFlow 3.x

## Overview

This guide is for workspaces on CloudFlow 3.x, which uses the legacy interface with a left sidebar. Most administration lives under **Settings**. If your workspace runs 4.0 or later, use *Creating your first workflow* (KB-GS-002) instead, because the menus are different.

## Before you start

Connect the apps you need first. In the left sidebar, open **Settings → Connections**, select the app and sign in to authorise it. Connections you create here are available to every workflow in the workspace.

## Steps

1. In the left sidebar, select **Workflows**, then **Create workflow**.
2. Name the workflow, for example "New HubSpot contact to Slack".
3. Choose a trigger: a schedule, a webhook, an event in a connected app, or a manual start.
4. Select **Add step**, choose the connection and the action, and fill in the fields. Insert variables from the trigger wherever you need its values.
5. Add further steps in the order they should run, then select **Save**.
6. Select **Test** to run the workflow once and check each step's result, then switch the workflow to **Active**.

## Checking runs

Runs are listed under **Settings → Run history**. Open a run to see each step's status. You can also download a CSV of the last 30 days (up to 10,000 rows); see *Exporting workflow run history in CloudFlow 3.x* (KB-ADV-007-3X).

## Webhook triggers and the 2026-12-01 deadline

CloudFlow 3.x supports webhooks v1 only. Webhooks v1 is deprecated, and v1 endpoints stop accepting deliveries on 2026-12-01. Workflows that start from a webhook must move to webhooks v2 before that date, and v2 requires CloudFlow 4.4. See *CloudFlow 4.4: webhooks v2 and webhook v1 deprecation* (RN-4.4-001).

## Troubleshooting

- **A step fails with CF-503:** the connection's authorisation has usually expired or been revoked. Open **Settings → Connections**, select the connection and choose **Reconnect**. Never disable SSL verification to work around it; see *Salesforce step fails with CF-503* (KB-TRB-004).
- **Nothing runs:** check that the workflow is **Active** and that the workspace has workflow runs left this month.

## Supported versions

CloudFlow 3.8 is the final 3.x release and is supported until 2027-06-30. We recommend planning an upgrade to 4.x, which adds the self-service Export button, per-step automatic retries and webhooks v2.

## Applies to

All plans. CloudFlow 3.x (3.0 to 3.8).

# Creating your first workflow

## Overview

This guide walks you through building, testing and switching on a simple workflow in CloudFlow 4.x. As an example, we post a Slack message whenever a new row is added to a Google Sheet. The same pattern works for any trigger and connector.

## Before you start

- You need a CloudFlow 4.x workspace and permission to create workflows. If you cannot see **New workflow**, ask a workspace admin for access.
- Have the accounts for the apps you want to connect ready; in this example, Google Sheets and Slack.

## Steps

1. In the top navigation, open **Workflows** and select **New workflow**.
2. Give the workflow a clear name, for example "New sheet row to Slack".
3. Choose a trigger: a schedule, a webhook, an event in a connected app, or a manual start. For this example, choose the Google Sheets event "New row".
4. If the app is not connected yet, CloudFlow asks you to connect it. You can also do this in advance: open **Connectors → Add connector**, choose the app and authorise it with your account.
5. Select **Add step** and choose the action, here Slack "Send message", then pick the channel.
6. Map fields with variables. Click into the message field and insert values from the trigger, such as the row's name and email columns. Variables are filled in when the workflow runs.
7. Select **Save**.

## Testing your workflow

Select **Test run** to run the workflow once with sample data. Each step shows its input, output and status, so you can fix a mapping before going live. When the test succeeds, switch the workflow **On**. From then on, every run appears under **Runs** in the top navigation and in the workflow's **Runs** tab.

On CloudFlow 4.3 and later you can also set automatic retries for an individual step (Step → Settings → Retries, up to 5 retries). See *Automatic retries for steps* (KB-ADV-005).

## Troubleshooting

- **The workflow never starts:** check that it is switched on and that your workspace has not used up its monthly workflow runs. When the monthly limit is exceeded, new runs are queued until the next period or an upgrade. See *Workflows not running on schedule* (KB-TRB-008).
- **A step fails with an error code:** look the code up in the *Error code reference* (KB-TRB-001). For example, CF-503 usually means a connector must be re-authorised under **Connectors**.
- **A step stops after five minutes:** a step that runs longer than 300 seconds fails with CF-504. See *Fixing CF-504 step timeouts* (KB-TRB-005).

## Applies to

All plans. CloudFlow 4.0 and later; automatic step retries need 4.3 or later. For the legacy interface, see *Creating your first workflow in CloudFlow 3.x* (KB-GS-003).

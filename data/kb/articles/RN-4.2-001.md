# CloudFlow 4.2 release notes

## Overview

CloudFlow 4.2 was released on 2026-03-10. The headline change is a self-service **Export** button for workflow run history, so you no longer need to ask support for a copy of your runs.

## New: export run history

You can now export the run history of any workflow yourself:

1. Open **Workflows** and select the workflow.
2. Open the **Runs** tab.
3. Select **Export** and choose **CSV** or **JSON**.
4. Pick the date range. Any range within your plan's run history retention is available (Free 7 days, Pro 30 days, Business 90 days, Enterprise 365 days).

Each export can contain up to **100,000 rows**. Full steps are in *Exporting workflow run history* (KB-ADV-007).

## Teams on 3.x

Nothing changes in CloudFlow 3.x. Workspaces on 3.x continue to export from **Settings → Run history → Download CSV**, which covers the last 30 days and up to 10,000 rows. See *Exporting workflow run history in CloudFlow 3.x* (KB-ADV-007-3X). Upgrading to 4.2 or later gives you the Export button and the larger export limits.

## Upgrade notes

- Exports follow your plan's retention: runs older than the retention period are no longer stored and cannot be exported.
- Earlier advice to email support for a CSV of your run history is replaced by the Export button.

## Applies to

CloudFlow 4.2 and later, all plans.

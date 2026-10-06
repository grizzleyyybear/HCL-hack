# Exporting workflow run history

## Overview

From CloudFlow 4.2 you can export the run history of any workflow yourself, as a CSV or JSON file. Exports are useful for audits, reporting and investigating failed runs. You do not need to contact support for an export.

## Before you start

- You need CloudFlow 4.2 or later. On CloudFlow 3.x, see "Exporting workflow run history in CloudFlow 3.x" (KB-ADV-007-3X).
- You need permission to view the workflow.
- The date range you can export is limited by your plan's run history retention:

| Plan | Run history retention |
| --- | --- |
| Free | 7 days |
| Pro | 30 days |
| Business | 90 days |
| Enterprise | 365 days |

## Steps

1. In the top navigation, open **Workflows**.
2. Select the workflow.
3. Open the **Runs** tab.
4. Optional: set a date range and a status filter, for example only failed runs.
5. Click **Export**.
6. Choose **CSV** or **JSON** and confirm. The file downloads in your browser.

Each export can contain up to 100,000 rows, for any date range within your plan's retention.

## What the export contains

One row (CSV) or one object (JSON) per run, with the run ID, status, start and finish time, duration, trigger type, and, for failed runs, the failed step and its error code. Step input and output data is not included, so the file does not contain the records your workflow processed.

## Troubleshooting

- **There is no Export button:** check your product version. The button was added in CloudFlow 4.2. On 3.x, use the steps in KB-ADV-007-3X.
- **Older runs are missing:** runs older than your plan's retention are no longer stored and cannot be exported.
- **You have more than 100,000 runs in the range:** split the export into several smaller date ranges.

## Applies to

CloudFlow 4.2 and later, all plans. The date range is limited by the plan's run history retention.

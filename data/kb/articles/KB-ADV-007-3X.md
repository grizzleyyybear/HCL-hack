# Exporting workflow run history in CloudFlow 3.x

## Overview

In CloudFlow 3.x, run history is exported as a CSV file from the **Settings** area in the left sidebar. The 3.x export covers the last 30 days of runs and is limited to 10,000 rows.

## Steps

1. Open **Settings** in the left sidebar.
2. Select **Run history**.
3. Optional: use the **Workflow** filter to export a single workflow.
4. Click **Download CSV**.

The file downloads in your browser and contains runs from the last 30 days, up to 10,000 rows.

## Limits

- **Last 30 days only.** On the Free plan run history is kept for 7 days, so the file covers at most 7 days.
- **At most 10,000 rows.** If you have more runs, filter by workflow and download one workflow at a time.
- **CSV only.** JSON export is not available in 3.x.

## Need more?

CloudFlow 4.2 and later add an **Export** button (Workflows → select the workflow → Runs tab → Export) that supports CSV or JSON, up to 100,000 rows, and any date range within your plan's retention. See "Exporting workflow run history" (KB-ADV-007). CloudFlow 3.8 is the final 3.x release and is supported until 2027-06-30, so plan your upgrade before then.

## Troubleshooting

- **Download CSV is greyed out:** there are no runs in the last 30 days for the selected filter. Clear the Workflow filter.
- **The file opens with all values in one column:** open it with your spreadsheet tool's import option and choose comma as the separator.

## Applies to

CloudFlow 3.x (3.0 to 3.8), all plans. For CloudFlow 4.2 and later, see KB-ADV-007.

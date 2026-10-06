# Maintenance windows for scheduled workflows

## Overview

A maintenance window pauses scheduled workflows for a planned period, for example while you upgrade a database that your workflows write to. From CloudFlow 4.3, workspace admins can create maintenance windows instead of switching each workflow off and on again by hand.

## Steps

1. In the top navigation, open **Admin → Maintenance windows**.
2. Select **New window**.
3. Enter a name, the start and end time, and the time zone. A window can last at most 12 hours.
4. Choose **All scheduled workflows** or select individual workflows.
5. Select **Save**. The window appears in the list with the status **Planned**, then **Active** while it runs.

## What happens during a window

- Scheduled runs that fall inside the window are **skipped**, not queued. They do not count towards your monthly workflow runs.
- Manual runs and webhook-triggered workflows are not affected and run as normal.
- When the window ends, the next scheduled run starts at its usual time.

## Troubleshooting

- **The Maintenance windows option is missing:** check that the workspace is on CloudFlow 4.3 or later and that you are a workspace admin.
- **A run still started during the window:** it was a manual or webhook run, or the workflow was not selected in the window.

## Applies to

CloudFlow 4.3 and later, all plans. Maintenance windows are not available in CloudFlow 3.x.

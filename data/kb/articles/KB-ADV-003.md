# Variables and data mapping

## Overview

Variables let a step use data that the trigger or an earlier step produced in the same run. Data mapping means filling a step's input fields with those variables, for example putting the email field from a form submission into a HubSpot contact or a Salesforce lead. Variables are resolved when the run reaches the step, so every run uses its own values.

## Variable syntax

- `{{trigger.<field>}}`: data from the trigger, for example `{{trigger.body.order_id}}` for a webhook trigger.
- `{{steps.<step_key>.<field>}}`: the output of an earlier step, for example `{{steps.find_contact.id}}`.
- `{{vars.<name>}}`: a workspace variable, a fixed value shared by all workflows, such as a default Slack channel.
- `{{run.id}}` and `{{run.started_at}}`: details of the current run.

Paths are case-sensitive. Use dots for nested fields and a number for list items, for example `{{steps.search.results.0.id}}`. A step can only use the trigger and steps that run before it.

## Mapping fields in CloudFlow 4.x

1. Open **Workflows** and select the workflow.
2. Click the step you want to configure.
3. Click into an input field and choose **Insert variable**.
4. Pick the trigger or an earlier step, then the field. CloudFlow inserts the full path for you.
5. Click **Test step** to see the resolved value before you publish.

## Mapping fields in CloudFlow 3.x

Open the workflow from the left sidebar and select the step. The **Variables** panel on the right lists the trigger and earlier steps. Drag a field into an input, or type the path by hand using the same syntax as above. Save, then use **Run once** to check the result.

## Workspace variables

Create workspace variables under **Admin → Variables** in 4.x or **Settings → Variables** in 3.x. Do not store API tokens or passwords in variables; connectors keep their own authorisation, and variable values are visible to every workspace member who can edit workflows.

## Troubleshooting

- **The output shows the literal text, such as `{{steps.lookup.name}}`:** the path does not match any data. Check spelling and case, and make sure the referenced step runs before the current one.
- **The value is empty:** the earlier step returned no data for this run. Add a condition step that checks the value before you use it.
- **A number arrives as text:** some connectors expect numbers. Map the raw field, not a field that was already combined with other text.

## Applies to

All CloudFlow versions (3.x and 4.x) and all plans. Menu paths differ by version as shown above.

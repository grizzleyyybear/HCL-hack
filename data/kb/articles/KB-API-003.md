# Slack and Microsoft Teams connectors

## Overview

The Slack and Microsoft Teams connectors post messages from a workflow, for example a run summary, a new-lead alert or a failure notice. Both use OAuth: someone with access to the chat workspace approves CloudFlow once, and every Slack or Teams step in your CloudFlow workspace then uses that authorisation.

## Connecting Slack

1. In CloudFlow 4.x open **Connectors → Add connector → Slack**. In CloudFlow 3.x open **Settings → Connections → Add connection → Slack**.
2. Sign in to Slack, choose the Slack workspace and select **Allow**.
3. Name the connector and save.
4. For a private channel, invite the CloudFlow app to the channel in Slack (type `/invite @CloudFlow` in the channel). Public channels work without an invite.

## Connecting Microsoft Teams

1. In CloudFlow 4.x open **Connectors → Add connector → Microsoft Teams**. In CloudFlow 3.x open **Settings → Connections → Add connection → Microsoft Teams**.
2. Sign in with your Microsoft 365 account and accept the requested permissions.
3. If your organisation requires admin consent for new apps, a Microsoft 365 administrator must approve CloudFlow before the connector can post.
4. In the Teams step, choose the team and the channel.

## Building messages

- Add the Slack or Teams step after the step that produces the data you want to send.
- Insert values from earlier steps with the variable picker instead of typing them, so the names match exactly. If a variable appears as literal text in the message, it was typed by hand or refers to a step that did not run; see "Variables and data mapping".
- Keep alerts short and include a link to the run in CloudFlow for details.

## Troubleshooting

- **Messages stopped after renaming the Slack workspace or channel:** the authorisation still points at the old name. Re-authorise the connector (4.x: Connectors → select the connector → Re-authorise; 3.x: Settings → Connections → Reconnect) and re-select the channel in the step.
- **Step fails with CF-503:** the authorisation was revoked in Slack or Teams, for example when the app was removed or the person who connected it lost access. Re-authorise the connector.
- **"Channel not found":** the app is not a member of the private channel. Invite it, then re-run the workflow.
- **Teams step fails right after connecting:** admin consent is still pending in Microsoft 365.

## Applies to

All plans, CloudFlow 3.x and 4.x.

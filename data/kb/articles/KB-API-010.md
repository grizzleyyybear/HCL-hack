# Google Sheets and HubSpot connectors

## Overview

The Google Sheets connector reads and writes rows in a spreadsheet, and the HubSpot connector creates and updates CRM records such as contacts, companies and deals. Both connect with OAuth, so CloudFlow never stores your Google or HubSpot password.

## Connecting Google Sheets

1. In CloudFlow 4.x open **Connectors → Add connector → Google Sheets**. In CloudFlow 3.x open **Settings → Connections → Add connection → Google Sheets**.
2. Sign in with the Google account that can open the spreadsheet and select **Allow**.
3. In a Google Sheets step, choose the spreadsheet and the sheet (tab). The first row is treated as column headers.

## Google Sheets quotas

Google limits how many requests each account can make per minute. A workflow that writes one row per call can hit this provider quota on busy days; the step then fails with Google's quota message in the run details. This is Google's limit, not your CloudFlow API rate limit (CF-429).

To avoid it:

- Use the **Add multiple rows** action to write rows in batches instead of one at a time.
- Spread large imports across a schedule rather than one burst.
- On CloudFlow 4.3 or later, enable automatic retries on the step (Step → Settings → Retries) so short quota spikes clear on their own.

## Connecting HubSpot

1. In CloudFlow 4.x open **Connectors → Add connector → HubSpot**. In CloudFlow 3.x open **Settings → Connections → Add connection → HubSpot**.
2. Sign in to HubSpot, choose the HubSpot account and approve the requested access.
3. In a HubSpot step, choose the object (contact, company or deal) and the action.

## Mapping HubSpot fields

- Map each HubSpot property to a value from an earlier step using the variable picker.
- Custom properties are matched by their internal name, not the label shown in HubSpot. If a value never appears in HubSpot, check the property's internal name in HubSpot's property settings.
- Dates must be in ISO format (YYYY-MM-DD); convert them in an earlier step if the source uses another format.

## Troubleshooting

- **CF-503 on either connector:** the authorisation was revoked or expired, for example after a password change or when the connected user lost access. Re-authorise it (4.x: Connectors → select the connector → Re-authorise; 3.x: Settings → Connections → Reconnect).
- **Spreadsheet not found:** the connected Google account cannot open that spreadsheet. Share it with that account, then re-run.

## Applies to

All plans, CloudFlow 3.x and 4.x. Automatic step retries need CloudFlow 4.3 or later.

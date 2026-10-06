# Salesforce step fails with CF-503

## Overview

A Salesforce step that fails with **CF-503 (connector unavailable)** almost always means CloudFlow's authorisation at Salesforce has expired or been revoked. Common triggers are a password change on the Salesforce user that authorised the connector, a Salesforce session policy that ends long-lived sessions, the connected app being revoked by a Salesforce admin, or the integration user being deactivated. The fix is to re-authorise the connector.

## Check platform status first

If the CloudFlow status page shows the **connectors** component as degraded or in an outage, the CF-503 errors come from the incident, not from your authorisation. Wait for the incident to clear, then re-run the failed runs. If connectors are operational, continue below.

## Steps in CloudFlow 4.x

1. Open **Connectors** in the top navigation.
2. Select the Salesforce connector used by the failing step.
3. Choose **Re-authorise**, sign in to Salesforce and select **Allow**.
4. Open **Runs**, select the failed run and choose **Re-run**.

## Steps in CloudFlow 3.x

1. Open **Settings** in the left sidebar and go to **Connections**.
2. Find the Salesforce connection and choose **Reconnect**.
3. Sign in to Salesforce and select **Allow**.
4. Open **Settings → Run history**, find the failed run and run it again.

## Never disable SSL verification

Do not disable SSL verification or look for an "insecure SSL" option to make a CF-503 go away. Turning off certificate checks exposes your Salesforce data to interception and does not fix an expired authorisation. Older advice, including some past support tickets, suggested enabling "Allow insecure SSL" on the connector; that advice is outdated and unsafe. The toggle existed only in CloudFlow 3.0-3.3 and was removed in 3.4 for security. If you are still on 3.0-3.3, upgrade to 3.8 or 4.x.

## Preventing repeat failures

- Authorise the connector with a dedicated Salesforce integration user whose password does not change with staff turnover.
- Ask your Salesforce admin to exempt the CloudFlow connected app from short session timeouts.
- On CloudFlow 4.3 or later, automatic step retries help with brief provider outages, but they cannot fix an expired authorisation.

## Applies to

All plans, CloudFlow 3.x and 4.x. Menu paths differ by version as shown above.

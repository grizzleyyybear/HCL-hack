# Connecting Salesforce

## Overview

The Salesforce connector lets workflows read and write Salesforce records, for example creating a lead when a form is submitted or updating an opportunity when an invoice is paid. CloudFlow connects to Salesforce with OAuth: you sign in to Salesforce once, approve access, and CloudFlow stores an authorisation that every Salesforce step in the workspace uses. CloudFlow never stores your Salesforce password.

## Before you start

- You need a Salesforce user with API access enabled (a Salesforce profile permission).
- We recommend a dedicated integration user. If the connector is authorised with a personal account, a password change or a Salesforce session policy on that account can end the authorisation, and Salesforce steps then fail with **CF-503**.
- Decide whether you are connecting a production org or a sandbox org. Each needs its own connector.

## Steps in CloudFlow 4.x

1. Open **Connectors** in the top navigation and select **Add connector**.
2. Choose **Salesforce**, then pick **Production** or **Sandbox**.
3. Sign in to Salesforce in the window that opens and select **Allow**.
4. Back in CloudFlow, give the connector a clear name (for example "Salesforce - production") and save.
5. In a workflow, add a Salesforce step and choose this connector.

To renew an existing authorisation, open **Connectors**, select the Salesforce connector and choose **Re-authorise**.

## Steps in CloudFlow 3.x

1. Open **Settings** in the left sidebar and go to **Connections**.
2. Select **Add connection**, choose **Salesforce** and pick **Production** or **Sandbox**.
3. Sign in to Salesforce and select **Allow**.
4. Name the connection and save. It is now available to Salesforce steps.

To renew an existing authorisation, open **Settings → Connections**, find the Salesforce connection and choose **Reconnect**.

## Troubleshooting

- **CF-503 on a Salesforce step:** the authorisation at Salesforce has expired or been revoked. Re-authorise the connector as described above. Full steps are in "Salesforce step fails with CF-503".
- **CF-403 when editing the connector:** your CloudFlow role does not allow managing connectors. Ask a workspace admin.
- **Sign-in window closes without connecting:** allow pop-ups for CloudFlow in your browser and try again.

Never turn off SSL certificate verification to make a connection work. CloudFlow always connects to Salesforce over verified TLS, and there is no supported way to disable it.

## Applies to

All plans, CloudFlow 3.x and 4.x. Menu paths differ by version as shown above.

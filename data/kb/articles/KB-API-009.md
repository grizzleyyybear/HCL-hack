# Rotating API tokens

## Overview

Rotating an API token means replacing it with a new one, for example when a team member leaves, when a token is close to its expiry date, or as part of a regular security schedule. This article explains how to replace a token in CloudFlow.

## Steps

1. Open the token list. In CloudFlow 4.x go to **Admin → API tokens**; in CloudFlow 3.x go to **Settings → API tokens**.
2. Find the token you want to replace and select **Revoke**. Confirm the prompt. The token stops working immediately.
3. Select **Create token**, enter a name and optionally an expiry date.
4. Copy the new token. It looks like `cf_live_XXXX...` and is shown only once.
5. Update every integration and script that used the old token with the new value.
6. Make one test API call to confirm the integration works again.

## What to expect

Between revoking the old token and deploying the new one, requests from your integrations fail with **CF-401** because the old token is no longer valid. Plan the rotation for a quiet period, tell the owners of each integration in advance, and have the new value ready to deploy as quickly as possible.

## Tips

- Give each integration its own token so you only have to update one system per rotation.
- Record where each token is used in its name, for example "warehouse-sync".
- Keep tokens in a secrets manager rather than in code or configuration files.
- Never share tokens in chat or email.

## Troubleshooting

- **Still seeing CF-401 after the rotation:** the new value has not reached every integration, or the header is malformed. It must read `Authorization: Bearer <token>`.
- **Lost the new token before saving it:** tokens cannot be shown again. Revoke it and create another one.

## Applies to

All plans, CloudFlow 3.x and 4.x.

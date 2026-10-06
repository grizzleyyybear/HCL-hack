# Rotating API tokens with an overlap window

## Overview

This is the current procedure for replacing a CloudFlow API token, effective 2026-03-01. You create the new token first, deploy it, keep both tokens active for a **24-hour overlap window**, and only then revoke the old token. Your integrations keep working throughout.

It replaces the earlier procedure ("Rotating API tokens"), which revoked the old token before creating the new one. That order caused CF-401 errors and downtime until the new token was deployed, so it should no longer be used.

## Steps

1. Open the token list: **Admin → API tokens** in CloudFlow 4.x, or **Settings → API tokens** in CloudFlow 3.x.
2. Select **Create token**. Use a name that shows what it replaces, for example "billing-sync-2026-10", and optionally set an expiry date.
3. Copy the new token (it looks like `cf_live_XXXX...`). It is shown only once.
4. Deploy the new token to every integration and script that used the old one.
5. Keep both tokens active for 24 hours. During this overlap window, check that traffic has moved to the new token: the token list shows a **Last used** time for each token.
6. After the 24-hour overlap, when the old token shows no recent use, select **Revoke** on the old token.

## Why the overlap window matters

Most integrations run on several servers or pick up new secrets on a schedule. During the overlap window some requests may still use the old token while others already use the new one; because both are valid, none of them fail. Revoking first cuts every caller off at once.

## If a token has leaked

Do not wait for an overlap window. Revoke the leaked token immediately, create a new one, accept a short interruption, and contact support so the security team can review recent activity. Never paste a token into a support chat.

## Troubleshooting

- **CF-401 after rotating:** some caller is still using a revoked token, or the header is malformed. It must read `Authorization: Bearer <token>`.
- **Old token still in use after 24 hours:** find the integration from the token's name and update it before you revoke the old token.

## Applies to

All plans, CloudFlow 3.x and 4.x. Effective 2026-03-01; replaces the revoke-first procedure.

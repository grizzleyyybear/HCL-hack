# Fixing CF-401 authentication errors

## Overview

Error **CF-401** means CloudFlow could not authenticate an API request: the token is invalid, expired or revoked, or it was not sent in the expected format. The response is HTTP 401 with `{"error": {"code": "CF-401", ...}}`.

## Common causes

- The token has passed its expiry date.
- Someone revoked the token, for example during a rotation or when its owner left the workspace.
- The header is malformed: `Bearer` is missing, the token is wrapped in quotes, or a line break was copied with it.
- The token was copied incompletely. A full token is `cf_live_` or `cf_test_` followed by 32 characters.

## Steps

1. **Check the header.** It must be exactly `Authorization: Bearer cf_live_XXXX...` with one space after `Bearer` and no quotes around the token.
2. **Check the token status.** Open **Admin → API tokens** (CloudFlow 4.x) or **Settings → API tokens** (CloudFlow 3.x). Find the token by name and check whether it shows as active, expired or revoked.
3. **If it is expired or revoked, create a new token** and deploy it. Follow "Rotating API tokens with an overlap window": create the new token, deploy it, keep both active for 24 hours while the old one still works, then revoke the old one.
4. **Test with a single call:**

```
curl https://api.cloudflow.example/v2/workflows \
  -H "Authorization: Bearer cf_live_XXXX..."
```

A JSON list of workflows means the token works.

## Avoiding CF-401 in future

- Set a reminder before a token's expiry date and rotate with the overlap window instead of letting it expire.
- Do not revoke a token before its replacement is deployed. Revoking first is the most common cause of CF-401 outages.
- Give each integration its own token so a rotation affects only one system.

## When it is not the token

If the token is active and the header is correct but calls still fail with CF-401, the user who created the token may have been removed from the workspace, which invalidates their tokens. Create a new token from an active user. If you suspect a token was leaked, revoke it immediately and contact support; the security team will review recent activity. Never send the token itself to support.

## Applies to

All plans, CloudFlow 3.x and 4.x.

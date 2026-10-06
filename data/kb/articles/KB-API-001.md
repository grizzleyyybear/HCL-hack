# API overview and authentication

## Overview

The CloudFlow REST API lets you manage workflows, start runs and read run history from your own code. Every request goes to the base URL below and must carry an API token in the `Authorization` header. The API is the same for CloudFlow 3.x and 4.x; only the place where you create tokens in the app differs.

- Base URL: `https://api.cloudflow.example/v2`
- Format: JSON request and response bodies, UTF-8
- Authentication: bearer token in the `Authorization` header

## API tokens

An API token identifies your workspace and the user who created it. A token can do only what that user's role allows, so a token created by a user without admin rights cannot change workspace settings.

Tokens start with a prefix that tells you their type:

| Prefix | Use |
| --- | --- |
| `cf_live_` | Production integrations |
| `cf_test_` | Development and testing |

The prefix is followed by 32 characters. In our documentation tokens are shown as placeholders such as `cf_live_XXXX...`. The full token is shown only once, when you create it, so store it in a secrets manager straight away.

## Creating a token

1. In CloudFlow 4.x, open **Admin → API tokens**. In CloudFlow 3.x, open **Settings → API tokens**.
2. Select **Create token**, give it a name that says where it will be used (for example "billing-sync"), and optionally set an expiry date.
3. Copy the token and store it securely. You cannot view it again later.

To replace a token without downtime, follow "Rotating API tokens with an overlap window".

## Making a request

Send the token as a bearer token:

```
curl https://api.cloudflow.example/v2/workflows \
  -H "Authorization: Bearer cf_live_XXXX..."
```

The header must be exactly `Authorization: Bearer <token>`, with a single space after `Bearer`. A missing, invalid, expired or revoked token returns error code **CF-401**. A token whose user lacks the required role, or a plan without the feature, returns **CF-403**.

Errors come back as JSON with a CloudFlow error code:

```
{"error": {"code": "CF-401", "message": "Authentication failed"}}
```

See "Error code reference" for every code and its fix.

## Rate limits

API calls are limited per workspace per minute according to your plan: Free 60, Pro 300, Business 1,000 and Enterprise 5,000. Going over returns HTTP 429 with error code CF-429 and a `Retry-After` header. See "API rate limits and 429 errors".

## Keeping tokens safe

- Never paste a token into a support chat, ticket or email. CloudFlow support will never ask for it.
- Do not commit tokens to source control or share them between integrations.
- If a token may have leaked, revoke it immediately under API tokens and create a new one, then contact support so the security team can review recent activity.

## Applies to

All plans, CloudFlow 3.x and 4.x.

# Plans and pricing

## Overview

CloudFlow has four plans: Free, Pro, Business and Enterprise. They differ in API rate limit, monthly workflow runs, seats, support tier and how long run history is kept. Paid plans are billed monthly.

## Plans and limits

| Plan | API calls / min | Workflow runs / month | Seats | Support tier | Price / month | Run history retention |
| --- | --- | --- | --- | --- | --- | --- |
| Free | 60 | 500 | 1 | standard | $0 | 7 days |
| Pro | 300 | 10,000 | 5 | standard | $49 | 30 days |
| Business | 1,000 | 50,000 | 25 | priority | $199 | 90 days |
| Enterprise | 5,000 | 500,000 | 200 | priority | $999 | 365 days |

API limits apply per workspace per minute. Workflow runs are counted per month. The binding values are set in the *Plan limits policy* (POL-LIMITS-001).

## Included in every plan

- All supported connectors and the generic HTTP step.
- Two-factor authentication (2FA) for every member.
- Run history, schedules, webhooks and API access, within the plan's limits.

## Business and Enterprise only

- **Single sign-on (SAML).** On Free and Pro, SSO settings are not available and SSO actions fail with CF-403. See *Single sign-on (SAML)* (KB-ADV-006).
- **Priority support.** After a conversation is handed to our team, Business and Enterprise customers get a response within 4 hours, compared with 24 hours on Free and Pro.

## Choosing a plan

- **Free** suits trying CloudFlow on your own: one seat and 500 runs a month.
- **Pro** suits small teams of up to 5 members with moderate volumes.
- **Business** adds SSO, priority support, 90 days of run history and room for 25 members.
- **Enterprise** is for high volumes: 5,000 API calls per minute, 500,000 runs a month and 200 seats.

You can change plans at any time. Upgrades apply immediately and are prorated; downgrades apply at the next billing day. See *Changing or cancelling your plan* (KB-BIL-005).

## Applies to

All plans and product versions. Prices are per workspace per month.

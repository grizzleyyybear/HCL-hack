# Single sign-on (SAML)

## Overview

Single sign-on (SSO) lets workspace members sign in to CloudFlow through your company's identity provider using SAML 2.0. **SSO is available on the Business and Enterprise plans only.** On Free and Pro the option is not available, and trying to enable it returns **CF-403** (permission denied). Two-factor authentication (2FA) is available on all plans.

## Before you start

- Your workspace is on the Business or Enterprise plan. Upgrades apply immediately and are prorated.
- You are a workspace admin.
- You can create a SAML 2.0 application in your identity provider's admin console.

## Steps in CloudFlow 4.x

1. Open **Admin → Security → Single sign-on**.
2. Copy the **ACS URL** and **Entity ID** that CloudFlow shows.
3. In your identity provider, create a SAML 2.0 application, paste both values, and map the user's email address to the `email` attribute.
4. Download the identity provider's metadata XML file and upload it in CloudFlow.
5. Click **Test sign-in** and sign in with a test user.
6. When the test succeeds, turn on **Enforce SSO** so members must sign in through your identity provider.

## Steps in CloudFlow 3.x

Open **Settings → Security → Single sign-on** from the left sidebar and follow the same steps: copy the ACS URL and Entity ID, create the SAML application, and upload the metadata XML. Test by signing in from a private browser window before you enforce SSO.

## Keep a fallback

While SSO is enforced, the workspace owner can still sign in with a password and 2FA. Keep this login so you can fix the configuration if your identity provider is unavailable or its certificate changes.

## Troubleshooting

- **The SSO option is missing or you see CF-403:** check that the plan is Business or Enterprise and that you are a workspace admin.
- **"SAML response invalid" after it worked before:** your identity provider probably rotated its signing certificate. Download the new metadata XML and upload it again.
- **A new member cannot sign in:** every SSO user takes a seat. If all seats on your plan are in use, free a seat or upgrade.

## Applies to

All CloudFlow versions (3.x and 4.x), Business and Enterprise plans only.

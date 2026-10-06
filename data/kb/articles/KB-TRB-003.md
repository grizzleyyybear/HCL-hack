# Fixing CF-403 permission errors

## Overview

Error **CF-403** means the request was authenticated but is not allowed. There are two causes: the user (or the user who created the API token) does not have the workspace role needed for the action, or the workspace's plan does not include the feature.

## Check which cause applies

The error message tells you which one it is:

- "Your role does not allow this action" means a role problem.
- "Your plan does not include this feature" means a plan problem.

## Fixing a role problem

1. Ask a workspace admin to review your role. In CloudFlow 4.x admins manage members under **Admin → Members**; in CloudFlow 3.x under **Settings → Members**.
2. The admin grants the role needed for the action, for example permission to edit connectors or manage API tokens.
3. Sign out and back in, then retry. API tokens use their creator's current role, so the same token works once the role is updated.

Role changes must come from an admin of your workspace.

## Fixing a plan problem

Some features are only on higher plans. The most common example is single sign-on (SAML), which needs the **Business** or **Enterprise** plan. On Free or Pro the SSO settings are unavailable, and API calls to configure SSO return CF-403.

| Feature | Free | Pro | Business | Enterprise |
| --- | --- | --- | --- | --- |
| SSO (SAML) | No | No | Yes | Yes |
| Two-factor authentication (2FA) | Yes | Yes | Yes | Yes |
| Priority support | No | No | Yes | Yes |

To get a plan feature, an admin can upgrade the plan. Upgrades apply immediately and are prorated. See "Changing or cancelling your plan".

## Still seeing CF-403?

- Check that you are in the right workspace. Roles are set per workspace.
- If the error appears when editing a connector, your role may not allow managing connectors. Ask an admin.
- If the error appears for an API call made with a token, check the role of the user who created the token, not your own.

## Applies to

All plans, CloudFlow 3.x and 4.x.

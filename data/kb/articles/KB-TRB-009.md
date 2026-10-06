# Login problems and password resets

## Overview

This article covers the most common sign-in problems: a forgotten password, a reset email that does not arrive, an expired reset link, and a lost two-factor authentication (2FA) device.

## Resetting your password

1. On the CloudFlow login page, select **Forgot password**.
2. Enter the email you sign in with. CloudFlow sends a reset email to the address on file for that user.
3. Open the link in the email and choose a new password.

Reset links **expire after 30 minutes**. If the link has expired, request a new one; only the most recent link works.

You can also ask CloudFlow support to trigger a reset. Support sends the reset email to the owner email on file for the account. For your security, support never shows a reset link, token or email address in chat, and cannot send the link to a different address. If you no longer have access to the email on file, the security team must verify your identity first.

## Reset email not arriving

- Wait a few minutes, then check your spam or junk folder.
- Check that you entered the email you sign in with; a typo or a different work address is a common cause.
- Ask your IT team whether a mail filter quarantines automated emails, and allow messages from CloudFlow.
- Request a new reset if more than 30 minutes have passed, because the earlier link no longer works.

## Two-factor authentication

2FA is available on all plans and strongly recommended. If you lose your 2FA device:

1. Sign in with one of the recovery codes you saved when you turned on 2FA.
2. If you have no recovery codes, contact support. The request goes to the security team, which verifies your identity before resetting 2FA. This cannot be done in chat.

## Single sign-on users

If your workspace uses SSO (SAML, available on the Business and Enterprise plans), you sign in through your company's identity provider. Your password is managed there, so ask your IT team to reset it.

## If you think your account is compromised

If you see sign-ins you do not recognise, or you believe a password or API token has leaked, contact support straight away. The case goes to the security team. Revoke any leaked API tokens immediately under API tokens.

Never share your password, a reset link or an API token with anyone, including CloudFlow support.

## Applies to

All plans, CloudFlow 3.x and 4.x.

# Changing or cancelling your plan

## Overview

You can upgrade, downgrade or cancel your CloudFlow plan at any time. Plan changes are made by a workspace admin.

## Upgrading

Upgrades apply immediately. You are charged a prorated amount for the rest of the current billing period, and the new limits for API calls, monthly runs and seats are available straight away.

- **CloudFlow 4.x:** open **Admin → Billing → Change plan**, choose the new plan and confirm.
- **CloudFlow 3.x:** open **Settings → Billing → Change plan**.

## Downgrading

Downgrades apply at your next billing day; until then you keep your current plan. Before the change takes effect, make sure your workspace fits the new plan:

- **Seats:** remove members so you are within the new plan's seat count (Free 1, Pro 5, Business 25).
- **Single sign-on:** SSO is available only on Business and Enterprise.
- **Run history:** retention becomes shorter (Free 7 days, Pro 30 days, Business 90 days). Export older runs first if you need them.

## Cancelling

When you cancel, the account status becomes **cancelled** and no further charges are made. Your workspace data is kept for 30 days and then permanently deleted.

Before you cancel, export anything you want to keep:

- **CloudFlow 4.2 and later:** Workflows → select the workflow → **Runs** tab → **Export** (CSV or JSON). See *Exporting workflow run history* (KB-ADV-007).
- **CloudFlow 3.x:** **Settings → Run history → Download CSV**. See *Exporting workflow run history in CloudFlow 3.x* (KB-ADV-007-3X).

## Cancelling is not deleting

Cancelling stops billing. Deleting your account and all its data is a separate request: the account owner asks support, a person on our team handles it, and there is a 30-day grace period before the deletion happens.

## Refunds

Changing or cancelling a plan does not refund past charges automatically. Refunds follow the *Refund policy* (POL-REFUND-001): a paid charge on Pro, Business or Enterprise can be considered within 14 days of the charge date, and only the billing team can approve it. See *Requesting a refund* (KB-BIL-006).

## Applies to

All plans. All product versions; menu paths are given for 4.x and 3.x, and the Export button needs 4.2 or later.

# Failed payments and past-due accounts

## Overview

If we cannot charge your card on your billing day, the invoice is marked **failed** and your account enters a grace period. This article explains the timeline and how to fix the payment before your workflows are affected.

## Timeline after a failed payment

| When | What happens |
| --- | --- |
| Billing day | The charge fails. The invoice status is **failed** and the account status becomes **past_due**. |
| Next 7 days | We retry the charge automatically 3 times. Your workflows keep running. |
| 14 days unpaid | The account is **suspended**: workflows are paused. Your data is kept for 30 days. |

If an account is cancelled instead, no further charges are made and its data is deleted after 30 days.

## Common reasons a payment fails

- The bank declined the card, for example because of a spending limit or a fraud check.
- The card has expired.
- There were insufficient funds.

The invoice shows the failure reason and the card's last four digits only.

## Updating your payment method

- **CloudFlow 4.x:** open **Admin → Billing → Payment method** and add a new card.
- **CloudFlow 3.x:** open **Settings → Billing → Payment method**.

After you update the card, the next automatic retry uses it. Once the outstanding invoice is paid, the account returns to **active**.

## After a suspension

When the overdue invoice is paid, the account becomes active again. Check your workflows afterwards and make sure the ones you need are switched on.

## Need help?

If you believe a payment failed in error, contact support with the invoice ID. Requests that need a billing decision, such as a refund or a credit, are handed to the billing team.

## Applies to

Pro, Business and Enterprise plans. All product versions; menu paths are given for 4.x and 3.x.

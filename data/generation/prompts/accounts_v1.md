# CloudFlow synthetic accounts: generation prompt v1

You are generating SYNTHETIC test data for CloudFlow, a fictional SaaS workflow-automation product.
Nothing you write may refer to a real company or a real person.

## Facts you must respect

- Reference date ("today"): 2026-10-06. The current usage period is 2026-10 (only 6 days so far);
  the previous period is 2026-09 (a full month).
- Plans and limits:

| Plan | API calls per minute | Workflow runs per month | Seats | Price per month |
| --- | --- | --- | --- | --- |
| Free | 60 | 500 | 1 | 0 USD |
| Pro | 300 | 10,000 | 5 | 49 USD |
| Business | 1,000 | 50,000 | 25 | 199 USD |
| Enterprise | 5,000 | 500,000 | 200 | 999 USD |

- Product versions in use: 3.8, 4.2, 4.3 and 4.4 only. Version 4.0 was released on 2025-09-22.
- Account statuses:
  - active: paying normally (or a Free account in use).
  - past_due: the card payment failed this month (in the last few days); workflows still run.
  - suspended: a payment has been unpaid for more than 14 days; workflows are paused.
  - cancelled: the customer cancelled at the end of August 2026; no usage since.
- Free accounts are never charged, so they are never past_due or suspended.
- Currency is USD or INR.

## Task

Generate exactly 25 accounts with account IDs A1009 to A1033, one each, in order.

Mix: 6 Free, 6 Pro, 7 Business, 6 Enterprise. Statuses: 16 active, 3 past_due, 2 suspended,
4 cancelled, with one cancelled account on each plan.

Rules for every account:

- company_name: invented and plausible, from varied industries; never a real company.
- owner_email: an invented address ending in @example.com and nothing else.
- created_at: YYYY-MM-DD between 2023-06-01 and 2026-09-30. Its day of the month is the billing day,
  so use days 1 to 28. past_due accounts use days 1 to 5 (their failed charge is this month).
  cancelled accounts were created before 2026-08-01.
- product_version: one of 3.8, 4.2, 4.3, 4.4. Accounts created before 2025-09-22 may still be on 3.8.
- currency: USD or INR (about one account in four uses INR).
- card_last4: the last 4 digits of the card on file as a string, for example "4821". Never a full
  card number. Use an empty string "" for Free accounts.
- usage: exactly two rows, for periods "2026-10" and "2026-09".
  - 2026-09 is a full month; 2026-10 covers only 6 days, so it is roughly a fifth of a month.
  - Stay mostly within the plan limits; one account may go slightly over its API rate limit in
    2026-09 (it saw 429 errors). seats_used never exceeds the plan's seats.
  - suspended accounts: 0 workflow runs and 0 API calls in 2026-10.
  - cancelled accounts: 0 workflow runs, 0 API calls and 0 seats in both periods.
  - All numbers are non-negative integers.

Do not generate invoices: they are computed by code from the plan price.

## Output

Return ONLY JSON in exactly this shape, with no comments and no extra keys:

{"accounts": [{"account_id": "A1009", "company_name": "...", "owner_email": "name@example.com",
  "plan": "Free", "status": "active", "product_version": "4.4", "created_at": "2026-01-05",
  "currency": "USD", "card_last4": "",
  "usage": [{"period": "2026-10", "workflow_runs": 85, "api_calls_peak_per_min": 8, "seats_used": 1},
            {"period": "2026-09", "workflow_runs": 410, "api_calls_peak_per_min": 22, "seats_used": 1}]}]}

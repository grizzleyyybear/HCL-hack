# Error code reference

## Overview

When an API call or a workflow step fails, CloudFlow returns an error code that starts with `CF-`. The code appears in the API response body, in the run details for a failed step, and in failure notifications. Use the table below to find what the code means and how to fix it.

## Error codes

| Code | Meaning | Fix |
| --- | --- | --- |
| CF-401 | Authentication failed: the API token is invalid, expired or revoked | Create a new token (see "Rotating API tokens with an overlap window") and check the header is `Authorization: Bearer <token>` |
| CF-403 | Permission denied: your role, or your plan, does not include the feature | Ask a workspace admin for the role you need. Some features, such as SSO, need the Business or Enterprise plan |
| CF-429 | Rate limit exceeded | Honour the `Retry-After` header, use exponential backoff (1 s doubling up to 32 s), batch requests, or upgrade for a higher limit |
| CF-500 | Internal error | Retry once. If it persists, check platform status and contact support with the run ID |
| CF-503 | Connector unavailable: usually the connector's authorisation at the provider expired or was revoked (for Salesforce, often after a password change or session policy) | Re-authorise the connector (4.x: Connectors → select → Re-authorise; 3.x: Settings → Connections → Reconnect). If platform status shows connectors degraded, wait for the incident to clear. Never disable SSL verification |
| CF-504 | Step timeout: the step ran longer than 300 seconds | Split the step, use pagination, or use async mode in the HTTP step |

## Detailed guides

- CF-401: "Fixing CF-401 authentication errors"
- CF-403: "Fixing CF-403 permission errors"
- CF-429: "API rate limits and 429 errors"
- CF-500: "CF-500 internal errors"
- CF-503: "Salesforce step fails with CF-503" (the same re-authorise fix applies to other connectors)
- CF-504: "Fixing CF-504 step timeouts"

## Where to find the code

- **API:** the JSON body contains `{"error": {"code": "CF-...", "message": "..."}}`.
- **Workflow runs in 4.x:** **Runs** → select the failed run → select the step marked as failed.
- **Workflow runs in 3.x:** **Settings → Run history** → select the run.

Each run has a run ID. Include it when you contact support so the team can find the exact failure.

## Before contacting support

1. Note the error code and the run ID.
2. Check platform status. If a component (api, workflow-engine, connectors or billing) shows degraded or outage, the error may clear when the incident ends.
3. Try the fix in the table once.

## Applies to

All plans, CloudFlow 3.x and 4.x.

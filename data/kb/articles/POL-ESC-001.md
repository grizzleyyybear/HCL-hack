# Support escalation and response times

## Overview

CloudFlow support combines an AI support assistant with human specialists. This policy defines when an answer may be given directly, when a conversation is handed to a person, and how quickly a person responds after a handoff.

## Answer quality

The assistant answers only from CloudFlow documentation and from account data returned by CloudFlow's own tools.

- An answer may be sent only if its groundedness score (how well every statement is supported by the cited documentation) is at least **0.70**. A draft that scores below 0.70 is revised once; if it still scores below 0.70, the conversation is handed to a person.
- A document is used only if its retrieval relevance score is at least **0.35**. If no document reaches 0.35, the assistant says the topic is not covered and offers a handoff.

## Response times

After a conversation is handed to a person, the customer receives a response within:

| Plan | Response time after handoff |
| --- | --- |
| Free | 24 hours |
| Pro | 24 hours |
| Business | 4 hours |
| Enterprise | 4 hours |

The assistant tells the customer the response time for their plan and never promises a faster one.

## Repeated contact

A customer who has contacted support **2 or more** times about the same issue is a repeated contact. A repeated contact combined with strong negative sentiment, such as an angry message, is handed to a person instead of being answered automatically.

## Always handled by a human

The following are always handed to a person, even when the documentation covers the topic:

- refunds and credits (billing team);
- billing disputes, including duplicate charges (billing team);
- legal matters (legal team);
- security incidents, such as a suspected account compromise or a leaked API token (security team);
- account deletion (security team);
- any explicit request to speak to a human.

A routine password reset is not a security incident: the assistant triggers the reset email to the address on file and never shows a reset link, token or email address in chat. A reported compromise is a security incident.

## Applies to

All plans and all product versions.

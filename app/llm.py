"""LLM client: JSON calls validated by Pydantic (one retry, then a safe fallback), plus MOCK_LLM mode.

Area: API and orchestration.
- call_json() talks to Ollama (default) or an OpenAI-compatible cloud API (LLM_PROVIDER=cloud,
  fallback only, disclosed in README). Output is validated with Pydantic; one retry with the
  validation error appended; then the caller's fallback. Connection errors also use the fallback.
- keyword_intent(), template_compose() and overlap_critique() are deterministic helpers. They are
  the MOCK_LLM behaviour and the safe fallbacks, so the pipeline always produces an answer.
- The LLM never does arithmetic or eligibility: tool_fact_lines() turns tool outputs into plain
  sentences in code, and the composer prompt receives those sentences.

Prompt files live in app/prompts/<name>.txt and use $variable placeholders.
"""
import json
import os
import pathlib
import re
import sqlite3
import string
from typing import Callable

import requests
from pydantic import BaseModel, ValidationError

from app import db, safety
from app.config import settings
from app.schemas import Critique, Draft, Intent

PROMPTS = pathlib.Path(__file__).resolve().parent / "prompts"

# Tags that wrap untrusted content in every prompt; stripped from variables so text cannot break out.
_WRAPPER_TAGS = re.compile(r"</?\s*(documents|customer_message|draft|history)\s*>", re.IGNORECASE)


# Fill a prompt template's $placeholders with the given variables (wrapper tags removed from values).
# A placeholder the caller did not pass (e.g. $history on a first message) reads "(none)".
def render(prompt_name: str, variables: dict) -> str:
    template = string.Template((PROMPTS / f"{prompt_name}.txt").read_text(encoding="utf-8"))
    values = {name: "(none)" for name in template.get_identifiers()}
    values.update({k: _WRAPPER_TAGS.sub("", str(v)) for k, v in variables.items()})
    return template.safe_substitute(values)


# Send one prompt to Ollama asking for JSON; returns (text, usage dict).
# keep_alive keeps the model loaded between requests (a cold load takes ~1 minute on a laptop GPU);
# the long timeout covers 7B models that run partly on the CPU.
def _ollama_chat(prompt: str) -> tuple[str, dict]:
    resp = requests.post(
        f"{settings.OLLAMA_BASE_URL}/api/chat",
        json={"model": settings.OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}],
              "format": "json", "stream": False, "keep_alive": "60m", "options": {"temperature": 0.1}},
        timeout=300,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = {"prompt_tokens": body.get("prompt_eval_count", 0),
             "completion_tokens": body.get("eval_count", 0)}
    return body["message"]["content"], usage


# Send one prompt to an OpenAI-compatible cloud API (fallback provider); returns (text, usage dict).
def _cloud_chat(prompt: str) -> tuple[str, dict]:
    base_url = os.getenv("CLOUD_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('CLOUD_API_KEY', '')}"},
        json={"model": os.getenv("CLOUD_MODEL", "gpt-4o-mini"),
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.1, "response_format": {"type": "json_object"}},
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    tokens = body.get("usage") or {}
    usage = {"prompt_tokens": tokens.get("prompt_tokens", 0),
             "completion_tokens": tokens.get("completion_tokens", 0)}
    return body["choices"][0]["message"]["content"], usage


# Name of the model in use, recorded in usage and the audit.
def _model_name() -> str:
    if settings.LLM_PROVIDER == "cloud":
        return os.getenv("CLOUD_MODEL", "gpt-4o-mini")
    return settings.OLLAMA_MODEL


# Turn a Pydantic error into a short, input-free message the model can fix on the retry.
def _short_error(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors())[:600]


# Ask the LLM for JSON matching `schema`. Invalid output gets ONE retry with the error appended;
# after that (or if the server is unreachable) the caller's fallback() is used.
# Returns (validated object, usage) so the caller can record tokens in the audit.
def call_json(prompt_name: str, variables: dict, schema: type[BaseModel],
              fallback: Callable[[], BaseModel]) -> tuple[BaseModel, dict]:
    if settings.MOCK_LLM:
        return fallback(), {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "model": "mock"}

    chat = _cloud_chat if settings.LLM_PROVIDER == "cloud" else _ollama_chat
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "model": _model_name()}
    prompt = render(prompt_name, variables)
    for _attempt in range(2):
        try:
            text, tokens = chat(prompt)
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            break  # no server or a broken response envelope: go straight to the fallback
        usage["calls"] += 1
        usage["prompt_tokens"] += tokens["prompt_tokens"] or 0
        usage["completion_tokens"] += tokens["completion_tokens"] or 0
        try:
            return schema.model_validate_json(text), usage
        except ValidationError as exc:
            prompt = (render(prompt_name, variables)
                      + f"\n\nYour previous output was invalid: {_short_error(exc)}. "
                        "Return only JSON matching the schema.")
    usage["fallback"] = True
    return fallback(), usage


# Report LLM readiness for GET /health: "ok", "ok (mock)", "ok (cloud)", "error" or
# "error: model <name> not pulled" (Ollama answers but the configured model is missing).
def health() -> str:
    if settings.MOCK_LLM:
        return "ok (mock)"
    if settings.LLM_PROVIDER == "cloud":
        return "ok (cloud)" if os.getenv("CLOUD_API_KEY") else "error"
    try:
        resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        models = resp.json().get("models") or []
    except (requests.RequestException, ValueError, AttributeError):
        return "error"
    model = settings.OLLAMA_MODEL
    pulled = {m.get(key) for m in models if isinstance(m, dict) for key in ("name", "model")}
    if model in pulled or f"{model}:latest" in pulled:
        return "ok"
    return f"error: model {model} not pulled"


# --- Deterministic helpers: MOCK_LLM behaviour and safe fallbacks. ---------------------------------

# PII detection ("is there any PII?") reuses safety.redact so both modules agree on what counts.

# CloudFlow domain vocabulary (from data/generation/cloudflow_facts.md). No match -> out of scope.
_DOMAIN = re.compile(
    r"\b(?:cloudflow|workflow|workspace|run|running|connector|connection|integrat\w*|api|token|"
    r"webhook|invoice|plan|pricing|billing|bill|billed|refund|charge|payment|paid|"
    r"subscription|credit|account|password|login|log ?in|sign ?in|seat|teammate|export|"
    r"error|cf-\d{3}|salesforce|hubspot|slack|teams|jira|zendesk|stripe|"
    r"postgres\w*|sheets?|schedule|trigger|step|variable|sso|saml|2fa|retry|retries|"
    r"limit|quota|usage|upgrade|downgrade|cancel\w*|version|admin|role|permission|outage|incident|429)"
    r"(?:s|es|ed|d|ing)?\b",
    re.IGNORECASE,
)
# First/second person words: a legal or "human" keyword only counts when someone is talking about their
# own situation ("I'll sue", "get me a manager"), not in a general question ("what is a court of appeal").
_PERSONAL = re.compile(r"\b(?:i|i'm|i've|i'll|me|my|mine|we|our|us|you|your)\b", re.IGNORECASE)

# Creative or general-knowledge requests: always out of scope, even if a domain word appears.
_CREATIVE = re.compile(r"\b(?:poem|joke|story|recipe|song|lyrics|haiku|limerick|essay)s?\b", re.IGNORECASE)
# General-knowledge questions: out of scope when no CloudFlow vocabulary is present.
_GENERAL = re.compile(r"\b(?:weather|capital of|who (?:is|was)|president|football|movie)\b", re.IGNORECASE)

# Intent keyword rules, checked in this order (first match wins for the type).
_COMPROMISE = re.compile(r"\b(?:hacked|compromised|unknown login|suspicious login|unauthori[sz]ed "
                         r"(?:access|login)|someone (?:else )?(?:logged|accessed)|leaked)\b", re.IGNORECASE)
_PASSWORD = re.compile(r"\b(?:password|reset (?:link|email)|locked out|can'?t log ?in|cannot log ?in|"
                       r"unable to log ?in|can'?t sign ?in)\b", re.IGNORECASE)
_DELETION = re.compile(r"\b(?:delete|close|remove|erase) (?:my |our |the )?(?:whole )?account\b", re.IGNORECASE)
_LEGAL = re.compile(r"\b(?:lawyer|legal|sue|suing|lawsuit|attorney|court)\b", re.IGNORECASE)
_BILLING_SUBTYPES = [  # (pattern, subtype) checked in order
    (re.compile(r"\b(?:charged (?:me )?twice|double[- ]charge\w*|duplicate\w*|charged two times)\b", re.I),
     "duplicate_charge"),
    (re.compile(r"\b(?:refund\w*|money back)\b", re.I), "refund"),
    (re.compile(r"\bcredit\b(?!\s*card)", re.I), "credit"),
    (re.compile(r"\b(?:dispute\w*|chargeback)\b", re.I), "dispute"),
]
_BILLING = re.compile(r"\b(?:invoice|billing|billed|charged?|payment|paid|subscription)s?\b", re.IGNORECASE)
_ACCOUNT = re.compile(r"\b(?:429|cf-429|rate[- ]limit\w*|usage|quota|limits?|plan|seats?|upgrade|downgrade)\b",
                      re.IGNORECASE)
_TROUBLE = re.compile(r"\b(?:cf-\d{3}|errors?|fail\w*|not working|doesn'?t work|isn'?t working|broken|"
                      r"stopped|crash\w*|bug)\b", re.IGNORECASE)
_HOW_TO = re.compile(r"\b(?:how do i|how to|how can i|where|can i)\b", re.IGNORECASE)

_HUMAN = re.compile(r"\b(?:manager|human|real person|a person|agent|supervisor|someone in charge|escalat\w*|"
                    r"(?:speak|talk) to (?:a |someone|somebody))\b", re.IGNORECASE)
_STRONG_REPEAT = re.compile(r"\b(?:second|third|fourth|fifth) time\b|\b(?:multiple|several|many) times\b",
                            re.IGNORECASE)
_REPEAT = re.compile(r"\b(?:again|still|keep|keeps|already (?:wrote|asked|contacted))\b", re.IGNORECASE)
_ANGRY = re.compile(r"\b(?:unacceptable|ridiculous|furious|worst|outrageous|disgusting|scam)\b|!!!",
                    re.IGNORECASE)
_NEGATIVE = re.compile(r"\b(?:frustrat\w*|annoy\w*|disappoint\w*|upset|terrible|awful|useless|"
                       r"fed up|sick of|nobody|no one|waste)\b", re.IGNORECASE)
_VAGUE = re.compile(r"\b(?:not working|doesn'?t work|isn'?t working|broken|help|error|issue|problem|"
                    r"wrong|stuck|fails?)\b", re.IGNORECASE)
# Specific product nouns: if one appears, the message is not vague.
_SPECIFIC = re.compile(r"\b(?:cf-\d{3}|workflow|connector|api|token|webhook|invoice|export|salesforce|"
                       r"hubspot|slack|teams|jira|zendesk|stripe|postgres\w*|sheets?|schedule|step|"
                       r"password|login|sso|2fa|plan|refund|charge\w*|429)s?\b", re.IGNORECASE)
_VERSION = re.compile(r"\b[34]\.\d{1,2}\b")

# Which tools each intent needs (code safety net for small models).
_TOOLS = {
    "billing": ["get_invoices", "check_refund_eligibility"],
    "account": ["lookup_account", "get_usage", "get_plan_limits"],
    "troubleshooting": ["check_platform_status"],
}
_DISPUTE_SUBTYPES = ("refund", "credit", "dispute", "duplicate_charge")


# True when most letters are capitals (shouting), e.g. "WHY IS THIS BROKEN AGAIN".
def _mostly_caps(message: str) -> bool:
    letters = [c for c in message if c.isalpha()]
    return len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.6


# Pick (type, subtype) from the keyword rules, in priority order; None type means "no rule matched".
def _type_and_subtype(message: str) -> tuple[str | None, str | None]:
    if _COMPROMISE.search(message):
        return "security", "compromise"
    if _DELETION.search(message):
        return "account", "deletion"
    if _LEGAL.search(message) and (_PERSONAL.search(message) or _DOMAIN.search(message)):
        return "complaint", "legal"
    # Billing disputes come before password resets: "can't log in AND charged twice" must reach billing.
    for pattern, subtype in _BILLING_SUBTYPES:
        if pattern.search(message):
            return "billing", subtype
    if _PASSWORD.search(message):
        return "security", "password_reset"
    if _BILLING.search(message):
        return "billing", None
    if _ACCOUNT.search(message):
        return "account", None
    if _TROUBLE.search(message):
        return "troubleshooting", None
    if _HOW_TO.search(message):
        return "how_to", None
    return None, None


# Classify a message with keyword rules; confidence 0 marks it as a fallback (R1).
def keyword_intent(message: str) -> Intent:
    text = message or ""
    intent_type, subtype = _type_and_subtype(text)
    human = bool(_HUMAN.search(text)) and bool(_PERSONAL.search(text) or _DOMAIN.search(text))
    strong_repeat = bool(_STRONG_REPEAT.search(text))
    repeated = strong_repeat or bool(_REPEAT.search(text))
    if _ANGRY.search(text) or _mostly_caps(text):
        sentiment = "angry"
    elif _NEGATIVE.search(text) or strong_repeat:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    words = re.findall(r"[\w'-]+", text)
    is_vague = len(words) <= 6 and bool(_VAGUE.search(text)) and not _SPECIFIC.search(text)
    # How-to phrasing alone ("where do X come from?") is not a support signal; it needs CloudFlow words.
    has_support_signal = (intent_type not in (None, "how_to")) or human or repeated or sentiment != "neutral" or is_vague

    if _CREATIVE.search(text) or (_GENERAL.search(text) and not _DOMAIN.search(text)):
        intent_type, subtype = "out_of_scope", None
    elif not _DOMAIN.search(text) and not has_support_signal:
        intent_type, subtype = "out_of_scope", None
    elif intent_type is None:
        # In-domain but no specific rule: angry/human-request messages are complaints,
        # vague ones are troubleshooting, everything else is a general how-to question.
        if human or sentiment == "angry":
            intent_type = "complaint"
        elif is_vague:
            intent_type = "troubleshooting"
        else:
            intent_type = "how_to"

    tools = list(_TOOLS.get(intent_type, []))
    if subtype == "password_reset":
        tools = ["send_password_reset"]
    if subtype == "compromise":
        urgency = "urgent"
    elif sentiment == "angry" or subtype in _DISPUTE_SUBTYPES or subtype == "legal":
        urgency = "high"
    elif intent_type == "how_to":
        urgency = "low"
    else:
        urgency = "normal"
    version = _VERSION.search(text)
    return Intent(
        type=intent_type, subtype=subtype, urgency=urgency, sentiment=sentiment,
        product_version=version.group(0) if version else None,
        pii_detected=safety.redact(text)[1], explicit_human_request=human,
        repeated_contact=repeated, tools_needed=tools, confidence=0.0,
        is_vague=is_vague and intent_type != "out_of_scope",
    )


# Show retrieved chunks as the <documents> body of a prompt, each labelled with its chunk_id.
def format_documents(chunks: list[dict]) -> str:
    blocks = []
    for c in chunks:
        m = c.get("meta", {})
        blocks.append(f"[chunk_id: {c.get('chunk_id')}] {m.get('title', '')} | section: {m.get('section', '')} "
                      f"| versions: {m.get('product_versions', '')} | type: {m.get('doc_type', '')}\n"
                      f"{c.get('text', '')}")
    return "\n\n".join(blocks) if blocks else "(no documents)"


# Find the output of the first successful call of a tool, or None.
def _tool_output(tool_results: list[dict], name: str):
    for call in tool_results or []:
        if call.get("tool") == name and call.get("status", "ok") == "ok" and "error" not in (call.get("output") or {}):
            return call.get("output")
    return None


# True when a usage value is over its limit: prefer the tool's flag, else compare (over = strictly greater).
def _is_over(limits: dict, flag_names: list[str], used, limit) -> bool:
    flags = dict(limits)
    if isinstance(limits.get("over_limit"), dict):
        flags.update(limits["over_limit"])
    for name in flag_names:
        if name in flags:
            return bool(flags[name])
    return used is not None and limit is not None and used > limit


# Collect invoice IDs from a possible_duplicates value of any reasonable shape.
def _duplicate_ids(possible_duplicates) -> list[str]:
    ids = []
    for item in possible_duplicates or []:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.extend(item.get("invoice_ids") or [item.get("invoice_id")])
        elif isinstance(item, (list, tuple)):
            ids.extend(x if isinstance(x, str) else x.get("invoice_id") for x in item)
    return [i for i in dict.fromkeys(ids) if i]


# Friendly wording for a tool that failed: "I wasn't able to check your invoices just now."
_TOOL_ACTIONS = {"lookup_account": "look up your account", "get_usage": "check your usage",
                 "get_plan_limits": "check your plan limits", "get_invoices": "check your invoices",
                 "check_refund_eligibility": "check refund eligibility",
                 "check_platform_status": "check our platform status", "send_password_reset": "send the password reset"}
# Plain-English refund reasons from check_refund_eligibility "reasons" (the window reason is told with the days).
_REFUND_REASONS = {"plan_not_eligible": "your plan isn't covered by the refund policy",
                   "no_paid_invoice": "there's no paid invoice to refund",
                   "invoice_not_paid": "that invoice wasn't paid"}
# One row per usage-vs-limit check: keys, the tool's over-limit flag names, the three sentence shapes,
# and whether the "within limit" sentence is worth saying in a short customer answer.
_USAGE_CHECKS = [
    ("api_calls_peak_per_min", "api_rate_limit_per_min", ["api_rate_over"],
     "You've used {used} API calls per minute at peak this month, which is over {plan} limit of {limit}. "
     "That's why some of your calls are getting 429 errors.",
     "Your peak this month is {used} API calls per minute, within {plan} limit of {limit}.",
     "{Plan} limit is {limit} API calls per minute.", True),
    ("workflow_runs", "monthly_workflow_runs", ["workflow_runs_over", "runs_over"],
     "You've used {used} workflow runs this month, which is over {plan} limit of {limit}.",
     "You've used {used} of your {limit} workflow runs this month.",
     "{Plan} limit is {limit} workflow runs a month.", True),
    ("seats_used", "seats", ["seats_over"],
     "You're using {used} seats, which is over {plan} limit of {limit}.",
     "You're using {used} of your {limit} seats.",
     "{Plan} limit is {limit} seats.", False),
]
_NUMBER_WORDS = {2: "two", 3: "three", 4: "four"}


# "1 day" / "15 days": a count with its noun in the right form.
def _count(n, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


# Show an amount like 49.0 as "49.00 USD" (same value, money format).
def _money(amount, currency=None) -> str:
    value = f"{amount:.2f}" if isinstance(amount, float) else str(amount)
    return f"{value} {currency}" if currency else value


# Join IDs as "A and B" or "A, B and C".
def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# Sentences comparing usage with the plan limits (numbers copied exactly from the tools).
def _usage_lines(usage: dict, limits: dict, plan: str | None, brief: bool) -> list[str]:
    plan_words = f"your {plan} plan's" if plan else "your plan's"
    lines = []
    for used_key, limit_key, flags, over, within, limit_only, always in _USAGE_CHECKS:
        used, limit = usage.get(used_key), limits.get(limit_key)
        words = {"used": used, "limit": limit, "plan": plan_words, "Plan": plan_words[0].upper() + plan_words[1:]}
        if limit is None or (used is None and brief):
            continue
        if used is None:
            lines.append(limit_only.format(**words))
        elif _is_over(limits, flags, used, limit):
            lines.append(over.format(**words))
        elif used == limit:
            lines.append(within.format(**words) + " That's right at your limit, but not over it.")
        elif always or not brief:
            lines.append(within.format(**words))
    return lines


# Sentences about invoices: failed payments, possible duplicates, else the most recent invoice.
def _invoice_lines(invoices) -> list[str]:
    rows = invoices.get("invoices", []) if isinstance(invoices, dict) else invoices
    rows = [r for r in rows or [] if isinstance(r, dict)]
    by_id = {r.get("invoice_id"): r for r in rows}
    lines = []
    for inv in rows:
        if inv.get("status") == "failed":
            reason = (inv.get("failure_reason") or "unknown reason").replace("_", " ")
            lines.append(f"Your payment of {_money(inv.get('amount'), inv.get('currency'))} on {inv.get('charged_on')} "
                         f"(invoice {inv.get('invoice_id')}) failed: {reason}.")
    duplicates = invoices.get("possible_duplicates") if isinstance(invoices, dict) else None
    for item in duplicates or []:
        ids = _duplicate_ids([item])
        if len(ids) < 2:
            continue
        first = by_id.get(ids[0], {})
        amount = item.get("amount", first.get("amount")) if isinstance(item, dict) else first.get("amount")
        date = (item.get("charged_on") if isinstance(item, dict) else None) or first.get("charged_on")
        if amount is not None and date:
            lines.append(f"I can see {_NUMBER_WORDS.get(len(ids), len(ids))} charges of "
                         f"{_money(amount, first.get('currency'))} on {date} ({_join(ids)}), "
                         "which looks like a duplicate charge.")
        else:
            lines.append(f"Invoices {_join(ids)} have the same amount and charge date, which looks like a duplicate charge.")
    if not lines and rows:
        latest = max(rows, key=lambda r: (r.get("charged_on") or "", r.get("invoice_id") or ""))
        lines.append(f"Your most recent invoice is {latest.get('invoice_id')} for "
                     f"{_money(latest.get('amount'), latest.get('currency'))}, charged on {latest.get('charged_on')} "
                     f"({latest.get('status')}).")
    elif not lines:
        lines.append("I don't see any invoices on your account.")
    return lines


# One sentence on refund eligibility from check_refund_eligibility (never a promise: billing decides).
def _refund_line(refund: dict) -> str:
    days, window = refund.get("days_since_charge"), refund.get("window_days")
    reasons = refund.get("reasons") or ([refund["reason"]] if refund.get("reason") else [])
    why = [_REFUND_REASONS[r] for r in reasons if r in _REFUND_REASONS]
    if days is not None and window is not None:
        outside = "outside_refund_window" in reasons if "reasons" in refund else days > window
        subject = f"Your charge on invoice {refund['invoice_id']}" if refund.get("invoice_id") else "Your charge"
        line = f"{subject} was {_count(days, 'day')} ago, which is {'outside' if outside else 'within'} our {window}-day refund window"
        if refund.get("eligible"):
            line += ", so it meets our refund policy."
        elif why:
            line += f", {'and' if outside else 'but'} {' and '.join(why)}, so it doesn't meet our refund policy."
        else:
            line += ", so it doesn't meet our refund policy."
    else:
        line = "I couldn't match a charge to our refund policy" + (f" because {' and '.join(why)}." if why else ".")
    return line + " Refunds are reviewed and issued only by our billing team, so I can't issue one myself."


# Sentences about platform components that are not operational (or one line saying all is well).
def _status_lines(status) -> list[str]:
    rows = status if isinstance(status, list) else status.get("components") or [status]
    bad = [r for r in rows if isinstance(r, dict) and r.get("status") not in (None, "operational")]
    lines = []
    for r in bad:
        name = {"api": "API"}.get(r.get("component"), str(r.get("component", "")).replace("-", " "))
        problem = "an outage" if r.get("status") == "outage" else "degraded performance"
        incident = f" (incident {r['incident_id']})" if r.get("incident_id") else ""
        lines.append(f"We're currently seeing {problem} on our {name} service{incident}.")
    if rows and not bad:
        lines.append("All CloudFlow systems are running normally right now.")
    return lines


# Turn tool outputs into natural fact sentences, computed in code (never by the LLM); numbers are exact.
# brief=True (customer-facing MOCK answers) skips facts that would only be noise, e.g. "you're on Pro".
def tool_fact_lines(tool_results: list[dict], brief: bool = False) -> list[str]:
    lines = []
    for call in tool_results or []:
        output = call.get("output")
        failed = call.get("status") == "error" or (isinstance(output, dict) and "error" in output)
        if failed and call.get("tool") != "create_handoff":
            lines.append(f"I wasn't able to {_TOOL_ACTIONS.get(call.get('tool'), 'check that')} just now.")

    account = _tool_output(tool_results, "lookup_account") or {}
    if account and not brief:
        lines.append(f"You're on the {account.get('plan')} plan, running CloudFlow {account.get('product_version')}.")
    if account.get("status") and account["status"] != "active":
        lines.append(f"Your account is currently {account['status'].replace('_', ' ')}.")

    limits = _tool_output(tool_results, "get_plan_limits")
    if isinstance(limits, dict):
        usage = {**(_tool_output(tool_results, "get_usage") or {}), **(limits.get("usage") or {})}
        lines.extend(_usage_lines(usage, limits, limits.get("plan") or account.get("plan"), brief))

    invoices = _tool_output(tool_results, "get_invoices")
    if invoices is not None:
        lines.extend(_invoice_lines(invoices))

    refund = _tool_output(tool_results, "check_refund_eligibility")
    if refund:
        lines.append(_refund_line(refund))

    status = _tool_output(tool_results, "check_platform_status")
    if status is not None:
        lines.extend(_status_lines(status))

    reset = _tool_output(tool_results, "send_password_reset")
    if reset and reset.get("status") == "reset_email_sent":
        lines.append("We've sent a password reset link to the email on file.")
    return lines


_NUMBERED = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
_PROCEDURE_HEADING = re.compile(r"steps|fix|resolution|how to|\bupdat|\bchang|\bresolv|\breconnect", re.IGNORECASE)
# Source IDs never appear in answer text (the UI lists the sources separately).
_SOURCE_IDS = re.compile(r"\s*\((?:KB|POL|RN|TKT|COM|JD)-[\w.-]*\w\)|\b(?:KB|POL|RN|TKT|COM|JD)-[\w.-]*\w")
# Titles or headings that mark a troubleshooting article ("Salesforce step fails with CF-503").
_TROUBLE_DOC = re.compile(r"\bCF-\d{3}\b|error|fail|not working|problem|troubleshoot|fix|resolv", re.IGNORECASE)
# Headings whose first sentence explains a cause, so it can open a troubleshooting answer.
_CAUSE_HEADING = re.compile(r"overview|cause|mean|symptom|why|what", re.IGNORECASE)


# Readable body lines of a chunk: no title, headings, table rows, bold markers, bullets or source IDs.
def _clean_lines(chunk: dict) -> list[str]:
    title = chunk["meta"].get("title", "")
    lines = [ln.strip().replace("**", "") for ln in chunk.get("text", "").splitlines()]
    lines = [_SOURCE_IDS.sub("", ln.lstrip("-* ")) for ln in lines
             if ln and ln != title and not ln.startswith(("#", "|"))]
    return [re.sub(r"\s+([.,;:])", r"\1", ln).strip() for ln in lines]


# The numbered steps of a chunk (at most 8).
def _steps(chunk: dict) -> list[str]:
    return [ln for ln in _clean_lines(chunk) if _NUMBERED.match(ln)][:8]


# The first n prose sentences of a chunk (numbered steps left out).
# A leading fragment (lowercase start, left over from the ~800-character chunk split) is skipped.
def _sentences(chunk: dict, n: int) -> str:
    prose = " ".join(ln for ln in _clean_lines(chunk) if not _NUMBERED.match(ln))
    sentences = re.split(r"(?<=[.!?])\s+", prose)
    if sentences and sentences[0][:1].islower():
        sentences = sentences[1:]
    return " ".join(sentences[:n]).strip()[:500]


# True when a chunk holds instructions: a Steps/Fix/Resolution heading or a numbered list.
def _is_procedure(chunk: dict) -> bool:
    return bool(_PROCEDURE_HEADING.search(chunk["meta"].get("section", "")) or _NUMBERED.search(chunk.get("text", "")))


# True when a chunk comes from a troubleshooting article (KB-TRB-*, or an error/fix title or heading).
def _is_troubleshooting(chunk: dict) -> bool:
    meta = chunk["meta"]
    return meta.get("source_id", "").startswith("KB-TRB") or bool(
        _TROUBLE_DOC.search(f"{meta.get('title', '')} {meta.get('section', '')}"))


# True when a section is written for another major version, e.g. "Steps in CloudFlow 3.x" for a 4.3 account.
def _other_version(chunk: dict, account_version: str) -> bool:
    match = re.search(r"\b(\d)\.x\b", chunk["meta"].get("section", ""))
    return bool(match and account_version and not account_version.startswith(match.group(1) + "."))


# Pick at most 2 chunks to quote: docs (authority 1-2) first, tickets only when there are no docs,
# never community. Chunks of the best-scoring source are taken together, instructions first
# (Steps/Fix/Resolution heading or numbered list), so a how-to quotes the steps, not the overview.
def _choose_chunks(chunks: list[dict], tool_results: list[dict]) -> list[dict]:
    docs = [c for c in chunks if c["meta"].get("authority_level", 5) <= 2]
    pool = docs or [c for c in chunks if c["meta"].get("authority_level") == 4]
    account_version = str((_tool_output(tool_results, "lookup_account") or {}).get("product_version") or "")
    pool = [c for c in pool if c["meta"].get("section", "").lower() != "applies to"
            and not _other_version(c, account_version)] or pool
    pool = sorted(pool, key=lambda c: (c["meta"].get("authority_level", 5), -c.get("score", 0)))
    if not pool:
        return []
    best = pool[0]["meta"].get("source_id")
    same_source = sorted((c for c in pool if c["meta"].get("source_id") == best),
                         key=lambda c: not _is_procedure(c))  # stable: keeps score order otherwise
    ranked = same_source + [c for c in pool if c["meta"].get("source_id") != best]
    # One piece per section: a long section split into ::0 and ::1 would only repeat itself.
    sections = {}
    for c in ranked:
        sections.setdefault((c["meta"].get("source_id"), c["meta"].get("section")), c)
    return list(sections.values())[:2]


# Opening line for how-to steps: "Here are the steps for exporting workflow run history:".
def _how_to_lead(title: str) -> str:
    first_word = title.split(" ", 1)[0]
    if first_word.lower().endswith("ing") and len(first_word) > 4:
        return f"Here are the steps for {title[0].lower()}{title[1:]}:"
    return "Here's what to do:"


# The documentation part of the answer, phrased like a support agent (no titles, IDs or section names):
# how-to -> lead + steps + one extra sentence; troubleshooting -> cause sentence + "Here's how to fix it:" + steps;
# no steps -> the key sentences.
def _doc_answer(chosen: list[dict]) -> str:
    procedure = next((c for c in chosen if _is_procedure(c)), None)
    rest = [c for c in chosen if c is not procedure]
    if procedure is None:
        return " ".join(p for p in (_sentences(rest[0], 2), _sentences(rest[1], 1) if len(rest) > 1 else "") if p)
    body = "\n".join(_steps(procedure)) or _sentences(procedure, 2)
    extra = _sentences(rest[0], 1) if rest else ""
    after = f"\n\n{extra}" if extra else ""
    if _is_troubleshooting(procedure):
        if extra and _CAUSE_HEADING.search(rest[0]["meta"].get("section", "")):
            return f"{extra} Here's how to fix it:\n{body}"  # the overview sentence explains the cause
        return f"Here's how to fix it:\n{body}{after}"
    return f"{_how_to_lead(procedure['meta'].get('title', ''))}\n{body}{after}"


# A friendly line for an upcoming change, without source IDs.
def _heads_up(change: str) -> str:
    text = _SOURCE_IDS.sub("", change).replace(" stops applying on ", " is being retired on ").strip().rstrip(".")
    return f"Heads-up: {text}, so it's worth planning ahead."


# Build a cited MOCK/fallback answer that reads like a support agent: account facts first, then the
# documented answer, then platform status and any upcoming changes. Citations are the chosen chunk_ids.
def template_compose(chunks: list[dict], tool_results: list[dict], upcoming_changes: list[str]) -> Draft:
    chosen = _choose_chunks(chunks, tool_results)
    calls = tool_results or []
    facts = " ".join(tool_fact_lines([t for t in calls if t.get("tool") != "check_platform_status"], brief=True))
    status = " ".join(tool_fact_lines([t for t in calls if t.get("tool") == "check_platform_status"], brief=True))
    docs = _doc_answer(chosen) if chosen else ("" if facts else "I couldn't find this in our documentation.")
    parts = [facts, docs, status] + [_heads_up(c) for c in upcoming_changes or []]
    return Draft(answer="\n\n".join(p for p in parts if p), cited_chunk_ids=[c["chunk_id"] for c in chosen])


# Common words and template connectives that are not factual claims (ignored by the overlap score).
_STOPWORDS = set("""
about above after again also according always because been before being below between both cannot
could does doing done down during each either else even every from further have having here into
itself just more most much must need only other over same section should since some such than that
their them then there these they this those through under until very want were what when where which
while will with within would your yours you're please thank thanks help note following via
couldn't documentation find upcoming change here's heads-up ahead planning worth it's
""".split())
_PROMISES = re.compile(
    r"refund (?:has|have) been (?:issued|processed|approved|sent)|(?:i|we)(?: have|'ve| will|'ll) "
    r"(?:refunded|credited|issue (?:a|the|your) refund|refund you|process(?:ed)? (?:a|the|your) refund)"
    r"|i have credited|credit (?:has|have) been (?:applied|issued|added)|refund (?:is|was) approved"
    r"|approved (?:your|the) refund|you will (?:receive|get) (?:a|your) (?:full )?refund"
    r"|your (?:account|plan) (?:has been|was) (?:changed|updated|upgraded|downgraded|deleted|cancelled)",
    re.IGNORECASE,
)


# Lowercase content words (length >= 4, not stopwords), commas removed from numbers, plural "s" trimmed.
def _content_words(text: str) -> set[str]:
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    words = re.findall(r"[a-z0-9]+(?:[-.'][a-z0-9]+)*", text)
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w
            for w in words if len(w) >= 4 and w not in _STOPWORDS}


# Read the critic groundedness minimum from policy_registry; None if the registry is unavailable.
def _critic_min() -> float | None:
    try:
        return float(db.get_policy("critic_min_groundedness")[0])
    except (KeyError, ValueError, sqlite3.Error):
        return None


# Score groundedness as the share of the draft's content words found in its cited chunks or tool outputs.
def overlap_critique(draft: Draft, chunks: list[dict], tool_results: list[dict] | None = None) -> Critique:
    cited = [c for c in chunks if c.get("chunk_id") in set(draft.cited_chunk_ids)]
    evidence = " ".join(f"{c.get('text', '')} {c['meta'].get('title', '')} {c['meta'].get('section', '')} "
                        f"{c['meta'].get('source_id', '')}" for c in cited)
    evidence += " " + json.dumps([t.get("output") for t in tool_results or []], default=str)
    evidence += " " + " ".join(tool_fact_lines(tool_results or []))
    draft_words = _content_words(draft.answer)
    grounded = draft_words & _content_words(evidence)
    groundedness = round(len(grounded) / len(draft_words), 2) if draft_words else 0.0

    issues = []
    minimum = _critic_min()
    if minimum is None:
        issues.append("critic threshold unavailable in policy_registry")
    elif groundedness < minimum:
        issues.append(f"groundedness {groundedness} below {minimum}")
    if not cited:
        issues.append("no citations")
    promise = _PROMISES.search(draft.answer)
    if promise:
        issues.append(f"promise phrase: {promise.group(0)}")
    pii_risk = "high" if safety.redact(draft.answer)[1] else "none"
    if pii_risk == "high":
        issues.append("possible PII or secret in draft")

    if not cited and not tool_results:
        coverage = "none"
    elif minimum is not None and groundedness >= minimum:
        coverage = "complete"
    else:
        coverage = "partial"
    ok = minimum is not None and groundedness >= minimum and not promise and pii_risk == "none"
    return Critique(groundedness=groundedness, coverage=coverage, pii_risk=pii_risk,
                    policy_risk="promise_made" if promise else "none",
                    decision="answer" if ok else "revise", issues=issues)

"""PII/secret redaction, authorisation checks and promise detection, all in plain code. Area: safety, critic and eval.

Everything here is regex + simple Python, so it works even when the LLM misbehaves.
"""
import logging
import re

from pydantic import BaseModel

from app import db
from app.config import ROOT

# Where setup_logging() writes the log file (tests point this at a temp folder).
LOG_FILE = ROOT / "logs" / "insightdesk.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# ---------------------------------------------------------------- redaction patterns

# Matches "password is X", "pwd: X", "my password: X"; group 1 is the lead-in we keep, group 2 the value.
# The lookahead skips ordinary words so "my password is not working" is left alone.
PASSWORD_RE = re.compile(
    r"\b((?:password|passwd|pwd|passcode)\s*(?:(?:is|was)\s*[:=]?|[:=])\s*)"
    r"(?!(?:not|wrong|incorrect|invalid|expired|correct|reset|being|still|too|now|the|a|an|my|"
    r"missing|required|weak|locked|changed|working|managed|set|stored|handled|controlled|kept|saved|synced|enforced)\b)"
    r"([^\s,;]*[^\s,;.!?])",
    re.IGNORECASE,
)

# Matches CloudFlow and Stripe-style keys: cf_live_..., cf_test_..., sk_live_..., rk_test_... (16+ chars).
PREFIXED_KEY_RE = re.compile(r"\b(?:cf|sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}")

# Matches OpenAI-style keys: sk-... followed by 16+ characters.
SK_DASH_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")

# Matches "Bearer <token>"; group 1 ("Bearer ") is kept, the token is replaced.
BEARER_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)

# Matches a long random-looking value (16+ chars, has a letter AND a digit) right after key/token/secret.
SECRET_AFTER_WORD_RE = re.compile(
    r"\b((?:api[\s_-]?)?key|token|secret)(\s*(?:is|=|:)?\s*)"
    r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{16,}",
    re.IGNORECASE,
)

# Matches an email address like jane.doe+test@example.com.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Matches 13-19 digits with optional single spaces/dashes between them (card candidates; Luhn decides).
CARD_RE = re.compile(r"(?<![\w+-])\d(?:[ -]?\d){12,18}(?![\w-])")

# Matches phone candidates: optional +, digit groups split by one space/dash, or "(415)" style groups.
# Separators are mandatory between plain digit groups, which keeps the regex fast (no backtracking blow-up).
PHONE_RE = re.compile(r"(?<![\w+-])\+?(?:\(\d+\)|\d+)(?:[ -]?\(\d+\)|[ -]\d+|(?<=\))\d+)*(?![\w-])")

# Digit runs glued to letters ("line07700900123", "card4111111111111111") that the patterns above skip
# because of their word-boundary lookbehind: 13-19 digits (Luhn-checked) are cards, 10-12 digits phones.
GLUED_CARD_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
GLUED_PHONE_RE = re.compile(r"(?<!\d)\d{10,12}(?!\d)")

# Digit groups behind a letter prefix ("ref VT-123456-7890"). PHONE_RE skips them on purpose so IDs such as
# TKT-2025-0142 (8 digits) survive; 10 or more digits in total are treated as a phone number.
PREFIXED_DIGITS_RE = re.compile(r"(?<=[A-Za-z]-)\d+(?:[ -]\d+)+")

# Matches an ISO date (2026-10-06); a run of dates must never be mistaken for a phone or card.
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


# Standard Luhn checksum used by card networks; filters out random digit runs that are not cards.
def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value = value * 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


# Replace a card candidate with [CARD] only when it passes Luhn and is not a list of dates.
def _card_sub(match: re.Match) -> str:
    text = match.group()
    digits = re.sub(r"\D", "", text)
    if DATE_RE.search(text) or not _luhn_ok(digits):
        return text
    return "[CARD]"


# A long digit run glued to letters: [CARD] when it passes Luhn, otherwise still hidden as [PHONE]
# (an order or tracking number, or a mistyped card; never shown either way).
def _glued_long_sub(match: re.Match) -> str:
    return "[CARD]" if _luhn_ok(match.group()) else "[PHONE]"


# Replace a phone candidate with [PHONE] when it has 10+ digits and is not a list of dates.
def _phone_sub(match: re.Match) -> str:
    text = match.group()
    digits = re.sub(r"\D", "", text)
    if len(digits) < 10 or DATE_RE.search(text):
        return text
    return "[PHONE]"


# Replace emails, phones, card numbers, API keys and passwords with [EMAIL]/[PHONE]/[CARD]/[SECRET].
# Returns (redacted_text, pii_found). Order matters: secrets first, then emails, cards, phones.
def redact(text: str) -> tuple[str, bool]:
    if not text or not isinstance(text, str):
        return text, False
    out = PASSWORD_RE.sub(r"\1[SECRET]", text)
    out = PREFIXED_KEY_RE.sub("[SECRET]", out)
    out = SK_DASH_KEY_RE.sub("[SECRET]", out)
    out = BEARER_RE.sub(r"\1[SECRET]", out)
    out = SECRET_AFTER_WORD_RE.sub(r"\1\2[SECRET]", out)
    out = EMAIL_RE.sub("[EMAIL]", out)
    out = CARD_RE.sub(_card_sub, out)
    out = PHONE_RE.sub(_phone_sub, out)
    out = PREFIXED_DIGITS_RE.sub(_phone_sub, out)
    out = GLUED_CARD_RE.sub(_glued_long_sub, out)
    out = GLUED_PHONE_RE.sub("[PHONE]", out)
    return out, out != text


# Redact every string inside a nested dict/list structure and return the redacted copy.
# Dict keys are left as they are; numbers, booleans, dates and None pass through unchanged.
def redact_obj(obj):
    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    if isinstance(obj, str):
        return redact(obj)[0]
    if isinstance(obj, dict):
        return {key: redact_obj(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_obj(item) for item in obj)
    return obj


# ---------------------------------------------------------------- authorisation (R8)

# Matches an account ID like A1004 (case-insensitive, compared upper-cased).
ACCOUNT_ID_RE = re.compile(r"\b[Aa]\d{4}\b")

# Words that mean "account data" (used by the other-person and email checks).
_DATA_WORDS = r"(?:accounts?|invoices?|usage|billing|plan|data|details|subscription|payments?|charges?)"

# Matches someone else's account: "my colleague's account", "another customer's invoices", "someone else's usage".
OTHER_PERSON_RE = re.compile(
    r"\b(?:colleague|co-?worker|friend|boss|teammate|client|partner|husband|wife|"
    r"someone\s+else|somebody\s+else|(?:another|other|different)\s+(?:customer|company|client|person|user))"
    r"(?:'s|s'|s)?\s+" + _DATA_WORDS + r"\b",
    re.IGNORECASE,
)

# Capitalised words that are not company names (plans, months, days, connectors, product words).
_NOT_COMPANIES = (
    r"(?:CloudFlow|I|My|Our|The|This|That|Today|Yesterday|Tomorrow|Free|Pro|Business|Enterprise|API|"
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"Salesforce|HubSpot|Slack|Microsoft|Teams|Google|Sheets|Jira|Zendesk|Stripe|PostgreSQL|HTTP)\b"
)

# Matches a named company: "the account of Acme Corp", "invoices for Globex", "Initech's usage".
# The name must look like a word ("Acme"), so IDs such as INV-6002 or CF-503 never count.
# ponytail: capitalisation heuristic; company names stored in our DB are checked exactly in other_account_requested.
NAMED_COMPANY_RE = re.compile(
    r"(?i:\b(?:account|invoices?|usage|billing|subscription|plan)\s+(?:of|for|belonging\s+to)\s+(?:the\s+)?)"
    r"(?!" + _NOT_COMPANIES + r")[A-Z][a-z][\w&-]*(?:\s+[A-Z][\w&-]+)*"
    r"|\b(?!" + _NOT_COMPANIES + r")[A-Z][a-z][\w&-]*(?:\s+[A-Z][\w&-]+)*'s\s+(?i:" + _DATA_WORDS + r")\b"
)

# Matches account data asked "for/of" an email: "invoices for bob@example.com", "bob@example.com's plan".
EMAIL_DATA_RE = re.compile(
    _DATA_WORDS + r"\s+(?:of|for|on|under|belonging\s+to|linked\s+to|registered\s+to|associated\s+with)\s+"
    r"(?:the\s+)?(?:email\s+|user\s+|address\s+)?" + EMAIL_RE.pattern
    + r"|" + EMAIL_RE.pattern + r"'s\s+" + _DATA_WORDS,
    re.IGNORECASE,
)


# Read (account_id, company_name, owner_email) for every account; empty list if the DB is not ready.
def _account_rows() -> list[tuple[str, str, str]]:
    try:
        with db.connect() as conn:
            rows = conn.execute("SELECT account_id, company_name, owner_email FROM accounts").fetchall()
    except Exception:  # noqa: BLE001 - no DB yet means nothing to compare against
        return []
    return [(r["account_id"].upper(), (r["company_name"] or "").lower(), (r["owner_email"] or "").lower()) for r in rows]


# True when `name` appears in `text` as a whole phrase (both already lower-cased).
def _has_phrase(text: str, name: str) -> bool:
    return bool(name) and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text) is not None


# True when the message asks about a different account (another A#### ID, company, person or email).
def other_account_requested(message: str, header_account: str | None) -> bool:
    message = message or ""
    header = (header_account or "").strip().upper()
    mentioned_ids = {found.upper() for found in ACCOUNT_ID_RE.findall(message)}
    if any(found != header for found in mentioned_ids):  # also true when there is no header
        return True
    if OTHER_PERSON_RE.search(message):
        return True
    rows = _account_rows()
    own_company, own_email = next(((c, e) for a, c, e in rows if a == header), ("", ""))
    # A named company or an email used "for" account data counts, unless it is the caller's own.
    for match in list(NAMED_COMPANY_RE.finditer(message)) + list(EMAIL_DATA_RE.finditer(message)):
        text = match.group().lower()
        if not (_has_phrase(text, own_company) or _has_phrase(text, own_email)):
            return True
    # Any other account's exact company name or owner email from our DB (judge accounts included).
    lowered = message.lower()
    return any(_has_phrase(lowered, c) or _has_phrase(lowered, e) for a, c, e in rows if a != header)


# ---------------------------------------------------------------- secret requests

# Verbs that put something on screen in this chat.
_SHOW = r"(?:show|display|reveal|tell|give|paste|print|share|read(?:\s+out)?|copy|provide|expose|post|output|repeat|write)"
# Verbs that deliver something (fine for a reset email, never fine for a key or password).
_SEND = r"(?:send|email|e-mail|text|dm|message|forward)"
# Up to 4 filler words between verb and noun ("show me my", "give us the"), but never "how/why/about/reset...".
_GAP = (r"(?:\s+(?!(?:how|where|when|why|what|about|to|if|whether|reset|change|rotate|regenerate|update|"
        r"create|revoke)\b)[\w'-]+){0,4}?\s+")
# Secret nouns: API keys, tokens, passwords, credentials ("password reset" is a normal request, not a secret).
_KEY_NOUN = (r"(?:api[\s_-]?(?:key|token)|access[\s_-]?token|auth(?:entication)?[\s_-]?token|token|"
             r"password(?!\s*reset)|passcode|secret(?:\s+key)?|private\s+key|credentials?)")
# Link nouns: the reset link/URL/token/code that must only ever go to the email on file.
_LINK_NOUN = r"(?:(?:password\s+)?(?:reset|recovery|login|sign[\s-]?in|magic|verification)\s+(?:link|url|token|code))"
# Words after a noun that make it a docs question ("the API token format") rather than a request.
_DOC_TAIL = r"(?!\s+(?:format|rotation|docs?|documentation|header|policy|length|expiry|scopes?|permissions?|settings?|page))"

# "show me my API key", "paste the reset link", "tell me my password".
SHOW_SECRET_RE = re.compile(r"\b" + _SHOW + _GAP + r"(?:" + _KEY_NOUN + "|" + _LINK_NOUN + r")\b" + _DOC_TAIL, re.I)
# "send me my API key", "email me the password".
SEND_KEY_RE = re.compile(r"\b" + _SEND + _GAP + _KEY_NOUN + r"\b" + _DOC_TAIL, re.I)
# "send the reset link here / in chat / to bob@example.com" (sending it to the email on file is fine).
SEND_LINK_HERE_RE = re.compile(
    r"\b" + _SEND + _GAP + _LINK_NOUN + r"\b[^.?!]{0,30}?"
    r"(?:\bhere\b|\bin\s+(?:the\s+|this\s+)?chat\b|\bin\s+(?:your|the|this)\s+(?:reply|response|message|conversation)\b|"
    + EMAIL_RE.pattern + r")",
    re.I,
)
# "what's my password", "what is the reset link".
WHAT_IS_SECRET_RE = re.compile(
    r"\bwhat(?:'s|\s+is|\s+are|\s+was)\s+(?:my|the|our)\s+(?:" + _KEY_NOUN + "|" + _LINK_NOUN + r")\b" + _DOC_TAIL, re.I
)
# "what's the email on file", "which email address do you have registered", "show me the email on file".
EMAIL_ON_FILE_RE = re.compile(
    r"\b(?:what|which|tell|show|give|read|reveal|display)\b[^.?!]{0,40}?\bemail(?:\s+address)?\b[^.?!]{0,30}?"
    r"\b(?:on\s+file|registered|associated|linked|you\s+have)",
    re.I,
)
_SECRET_REQUEST_PATTERNS = [SHOW_SECRET_RE, SEND_KEY_RE, SEND_LINK_HERE_RE, WHAT_IS_SECRET_RE, EMAIL_ON_FILE_RE]


# True when the message asks us to reveal a key, token, password, reset link or the email on file.
def asks_for_secret(message: str) -> bool:
    return any(pattern.search(message or "") for pattern in _SECRET_REQUEST_PATTERNS)


# ---------------------------------------------------------------- promises (never promise refunds/changes)

# Phrases that claim a refund, credit or account change was done (or certainly will be). One regex per idea.
_PROMISE_PATTERNS = [
    # "refund has been issued", "credit has been applied", "reversal has been processed"
    r"\b(?:refund|credit|reimbursement|reversal|chargeback)s?\s+(?:has|have)\s+been\s+"
    r"(?:issued|processed|approved|sent|completed|initiated|applied|granted|credited|added|made)",
    # "the refund was issued", "credits were applied"
    r"\b(?:refund|credit)s?\s+(?:was|were)\s+(?:issued|processed|approved|sent|applied|granted)",
    # "your refund is on its way", "your money will be back", "your refund will be issued"
    r"\byour\s+(?:refund|credit|money)\s+(?:is|will\s+be)\s+"
    r"(?:on\s+its\s+way|being\s+processed|issued|processed|credited|applied|sent|back)",
    # "I have refunded", "I've credited", "I approved the refund", "I went ahead and cancelled"
    r"\bI(?:\s+have|'ve|\s+just|\s+went\s+ahead\s+and)?\s+(?:issued|approved|refunded|credited|reversed|"
    r"cancell?ed|changed|upgraded|downgraded|unlocked|unsuspended|reactivated|deleted|waived)\b",
    # "we have refunded", "we've cancelled your subscription"
    r"\bwe(?:\s+have|'ve)\s+(?:issued|approved|refunded|credited|reversed|cancell?ed|changed|"
    r"upgraded|downgraded|unlocked|reactivated|deleted|waived)\b",
    # "your account has been upgraded", "subscription has been cancelled", "plan has been changed"
    r"\b(?:account|subscription|plan)\s+(?:has|have)\s+been\s+(?:changed|upgraded|downgraded|unlocked|"
    r"unsuspended|reactivated|restored|cancell?ed|deleted|credited|refunded)",
    # "your account is now unlocked", "your plan was upgraded"
    r"\byour\s+(?:account|subscription|plan)\s+(?:is\s+now|was)\s+(?:upgraded|downgraded|unlocked|"
    r"reactivated|cancell?ed|changed)",
    # "I will refund you", "I'll issue a refund", "I'll cancel it"
    r"\bI(?:\s+will|'ll)\s+(?:refund|credit|issue\s+(?:a|the|your)\s+refund|cancel|upgrade|downgrade|unlock|waive)",
]
PROMISE_RE = re.compile("|".join(_PROMISE_PATTERNS), re.IGNORECASE)


# True when text promises a refund, credit or account change ("refund has been issued", ...).
def makes_promise(text: str) -> bool:
    return bool(PROMISE_RE.search((text or "").replace("\u2019", "'")))


# ---------------------------------------------------------------- logging (R9: logs are redacted too)

class RedactingFilter(logging.Filter):
    """Logging filter that redacts every log message before it is written."""

    # Format the message with its %-args first, redact the result, and drop the args so nothing raw survives.
    # Records without PII are left untouched, so formatters that need record.args (uvicorn access logs) still work.
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - bad %-args must not crash logging
            message = str(record.msg)
        redacted, found = redact(message)
        if found:
            record.msg = redacted
            record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))[0]
        return True


# Set up console + file logging once, then put RedactingFilter on every handler of every logger
# (root, uvicorn, ...), so redaction happens no matter which logger emits. Safe to call twice.
def setup_logging() -> None:
    root = logging.getLogger()
    if not any(getattr(handler, "insightdesk", False) for handler in root.handlers):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        for handler in (logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")):
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            handler.insightdesk = True
            root.addHandler(handler)
        root.setLevel(logging.INFO)
    loggers = [root] + [lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger)]
    for logger in loggers:
        for handler in logger.handlers:
            if not any(isinstance(f, RedactingFilter) for f in handler.filters):
                handler.addFilter(RedactingFilter())

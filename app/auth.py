"""Customer sign-in for the CloudFlow web app: a password check and a signed, expiring session token.

The token is stateless: base64(JSON {"sub": account_id, "exp": unix time}) + "." + HMAC-SHA256 signature,
so the server needs no session table and a tampered or expired token is simply rejected.
POST /support still takes the account from the X-Account-Id header (API contract). When a token is sent too,
main.py checks that it belongs to that same account.

ponytail: every account signs in with one shared DEMO_PASSWORD, because judge-loaded accounts arrive without
passwords. A real deployment would store a salted hash per user (or use SSO) and rate-limit failed sign-ins.
"""
import base64
import datetime
import hashlib
import hmac
import json
import re
import secrets
import time

from app import db
from app.config import settings

ACCOUNT_ID = re.compile(r"^A\d{4}$", re.IGNORECASE)
_PROCESS_SECRET = secrets.token_bytes(32)  # used when AUTH_SECRET is not set: tokens then end with the process


class NotConfigured(Exception):
    """Sign-in is switched off because the server has no DEMO_PASSWORD."""


# The key that signs tokens: AUTH_SECRET from the environment, else a random per-process key.
def _key() -> bytes:
    return settings.AUTH_SECRET.encode() if settings.AUTH_SECRET else _PROCESS_SECRET


# Find the account for a sign-in name: an account ID (A1001) or the owner email, both case-insensitive.
def find_account(login: str) -> dict | None:
    login = login.strip()
    column, value = ("account_id", login.upper()) if ACCOUNT_ID.match(login) else ("lower(owner_email)", login.lower())
    with db.connect() as conn:
        row = conn.execute("SELECT account_id, company_name, plan, status, product_version, created_at "
                           f"FROM accounts WHERE {column} = ?", (value,)).fetchone()
    return dict(row) if row else None


# Check the password and return a session, or None. Unknown account and wrong password look the same.
def login(login_name: str, password: str) -> dict | None:
    if not settings.DEMO_PASSWORD:
        raise NotConfigured("set DEMO_PASSWORD on the server to enable sign-in")
    account = find_account(login_name)
    password_ok = hmac.compare_digest(password.encode(), settings.DEMO_PASSWORD.encode())
    if not (account and password_ok):
        return None
    expires = int(time.time()) + settings.SESSION_HOURS * 3600
    return {"token": make_token(account["account_id"], expires), "token_type": "bearer",
            "expires_at": datetime.datetime.fromtimestamp(expires, datetime.timezone.utc).isoformat(),
            "account": {k: account[k] for k in ("account_id", "company_name", "plan", "status", "product_version")}}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


# Build a signed token for an account that expires at the given unix time.
def make_token(account_id: str, expires: int) -> str:
    payload = _b64(json.dumps({"sub": account_id, "exp": expires}).encode())
    return f"{payload}.{_sign(payload)}"


# The account ID inside a valid, unexpired token; None for anything tampered, malformed or expired.
def verify_token(token: str) -> str | None:
    payload, _, signature = token.partition(".")
    # bytes, not str: compare_digest raises on non-ASCII str, and a header can carry any character
    if not payload or not hmac.compare_digest(signature.encode(), _sign(payload).encode()):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    return claims.get("sub") if claims.get("exp", 0) > time.time() else None

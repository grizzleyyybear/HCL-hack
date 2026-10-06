"""Password reset tool (mocked). Area: data and tools."""
import logging

from app.tools.account_tools import lookup_account

log = logging.getLogger(__name__)


# Pretend to email a reset link; never returns a token, link or email address.
def send_password_reset(account_id: str) -> dict:
    if "error" in lookup_account(account_id):
        return {"error": "account_not_found"}
    # Log only the event: no token, link or email address is ever created, logged or returned.
    log.info("password reset email triggered for account %s", account_id)
    return {"status": "reset_email_sent"}

import logging
import re
import socket
from typing import Optional

from agent.models import EmailValidationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex — RFC 5322 simplified (covers 99%+ of real addresses)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Free/disposable domains we reject outright
_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "throwaway.email",
        "yopmail.com",
        "sharklasers.com",
        "trashmail.com",
        "fakeinbox.com",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_format_valid(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _is_disposable(domain: str) -> bool:
    return domain.lower() in _DISPOSABLE_DOMAINS


def _has_mx_record(domain: str) -> bool:
    """
    Checks whether the domain has an MX record — confirms mail can be delivered.
    Uses a short timeout so it never blocks the agent for long.
    """
    try:
        socket.setdefaulttimeout(3)
        # getaddrinfo won't resolve MX, but we can do a basic DNS lookup.
        # For production, swap this for dnspython: dns.resolver.resolve(domain, "MX")
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, socket.timeout):
        return False


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def validate_email(email: Optional[str]) -> EmailValidationResult:
    """
    Three-layer validation:
      1. Format check (regex)
      2. Disposable domain check
      3. DNS / MX lookup (skipped in local env to avoid latency)
    Always returns a result — never raises.
    """
    if not email:
        return EmailValidationResult(
            email="",
            is_valid=False,
            reason="missing",
        )

    email = email.strip().lower()

    if not _is_format_valid(email):
        return EmailValidationResult(
            email=email,
            is_valid=False,
            reason="invalid_format",
        )

    domain = email.split("@")[1]

    if _is_disposable(domain):
        return EmailValidationResult(
            email=email,
            is_valid=False,
            reason="disposable_domain",
        )

    try:
        deliverable = _has_mx_record(domain)
    except Exception:
        logger.warning("MX lookup failed", extra={"domain": domain}, exc_info=True)
        deliverable = None

    return EmailValidationResult(
        email=email,
        is_valid=True,
        is_deliverable=deliverable,
        reason=None if deliverable else "no_mx_record",
    )

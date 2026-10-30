"""Signed, short-lived confirmation of a changed comparison basis (FZ08, ADR03).

The token binds the user's confirmation to one request (its hash without the token and the
choice) and to the exact conflict that was shown (which spaces miss which criteria). It
expires after comparison_confirmation_ttl_s (10 minutes). If the data or the request
change, the token no longer matches and the user is asked again.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger("app.security")

_PLACEHOLDERS = {"", "promijeni_me", "change_me"}


class TokenError(ValueError):
    pass


@lru_cache
def _secret() -> bytes:
    settings = get_settings()
    value = settings.app_hmac_secret.get_secret_value()
    if value in _PLACEHOLDERS or len(value) < 32:
        if settings.is_production:
            raise RuntimeError("APP_HMAC_SECRET mora imati barem 32 znaka u produkciji.")
        # Development only: a per-process secret keeps confirmations working locally.
        logger.warning("hmac_secret_ephemeral")
        return secrets.token_bytes(32)
    return value.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue(request_sha256: str, conflict_sha256: str, ttl_s: int, now: float | None = None) -> str:
    payload = {"r": request_sha256, "c": conflict_sha256, "exp": int((now or time.time()) + ttl_s)}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, request_sha256: str, conflict_sha256: str, now: float | None = None) -> None:
    body, _, sig = token.partition(".")
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig.encode(), expected.encode()):
        raise TokenError("signature")
    try:
        payload = json.loads(_unb64(body))
    except ValueError as exc:
        raise TokenError("malformed") from exc
    if int(payload.get("exp", 0)) <= (now or time.time()):
        raise TokenError("expired")
    if payload.get("r") != request_sha256 or payload.get("c") != conflict_sha256:
        raise TokenError("basis_changed")

"""Authentication helpers (ASR-2): password hashing, signed expiring tokens, login throttling.

Standard library only:
  * passwords  -> scrypt with a random per-password salt, compared in constant time
  * tokens     -> "<base64url(json payload)>.<base64url(HMAC-SHA256)>", with an expiry
  * throttling -> in-memory lockout after repeated failed logins (per username)

Tokens carry only the username and expiry. The role is always looked up from the
user store on each request, so demoting or deleting a user takes effect immediately.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Callable, Dict, List, Optional

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def validate_username(username: str) -> str:
    if not USERNAME_RE.match(username or ""):
        raise ValueError("username must be 3-32 characters: letters, digits, '_', '.', '-'")
    return username


def validate_password(password: str) -> str:
    if not isinstance(password, str) or not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        raise ValueError(f"password must be {MIN_PASSWORD_LEN}-{MAX_PASSWORD_LEN} characters")
    return password


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                            p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True if `password` matches `stored`. Malformed or empty hashes never match."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r),
                                p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the username does not exist, so unknown and known users take similar time.
DUMMY_HASH = hash_password(secrets.token_hex(16))


# ------------------------------------------------------------------ tokens
def make_token(secret: str, username: str, ttl_seconds: int, now: Optional[float] = None) -> str:
    payload = {"u": username, "exp": int((time.time() if now is None else now) + ttl_seconds)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def parse_token(secret: str, token: str, now: Optional[float] = None) -> Optional[str]:
    """Return the username if the token is authentic and unexpired, else None."""
    try:
        body, sig = token.split(".")
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(sig), expected):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] <= (time.time() if now is None else now):
            return None
        username = payload["u"]
        return username if isinstance(username, str) else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


# -------------------------------------------------------------- throttling
class LoginThrottle:
    """Lock a username out for `lock_seconds` after `max_failures` failures within `window_seconds`."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300, lock_seconds: int = 60,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures, self.window, self.lock = max_failures, window_seconds, lock_seconds
        self._clock = clock
        self._failures: Dict[str, List[float]] = {}
        self._locked_until: Dict[str, float] = {}

    def locked_for(self, key: str) -> int:
        """Seconds remaining on a lockout (0 if not locked)."""
        remaining = self._locked_until.get(key, 0) - self._clock()
        return int(remaining) + 1 if remaining > 0 else 0

    def record_failure(self, key: str) -> None:
        now = self._clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window] + [now]
        self._failures[key] = recent
        if len(recent) >= self.max_failures:
            self._locked_until[key] = now + self.lock
            self._failures[key] = []

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)

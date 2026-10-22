"""Salted scrypt password hashing.

Format: scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
"""

import base64
import hashlib
import hmac
import os

_N, _R, _P = 16384, 8, 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """Return a new scrypt hash string in the format above (random salt, n=16384, r=8, p=1)."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def check_password(password: str, stored: str) -> bool:
    """True if password matches the stored scrypt hash string.

    Returns False, never raises, for anything that is not a well-formed scrypt string.
    """
    try:
        parts = stored.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        if n <= 0 or r <= 0 or p <= 0:
            return False
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
            dklen=len(expected) or _DKLEN, maxmem=128 * 1024 * 1024,
        )
        return bool(expected) and hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError, OverflowError, MemoryError):
        return False

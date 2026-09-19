from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """Return `iterations$salt_hex$digest_hex` for storage."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return f"{_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison against a hash produced by `hash_password`."""
    try:
        iterations_str, salt, expected_hex = stored.split("$")
        iterations = int(iterations_str)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(digest.hex(), expected_hex)

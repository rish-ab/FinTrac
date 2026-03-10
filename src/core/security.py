# =============================================================
# src/core/security.py
#
# Two responsibilities:
#   1. Password hashing — bcrypt via passlib
#   2. JWT creation and verification — HS256 via python-jose
#
# WHY BCRYPT?
# Bcrypt is deliberately slow — it takes ~100ms to hash a
# password. This makes brute-force attacks 1000x harder than
# fast algorithms like MD5 or SHA-256. The "work factor" is
# configurable — we use 12, which is the current recommended
# minimum.
#
# HOW JWT WORKS:
# 1. User logs in with email + password
# 2. We verify the password, create a JWT signed with SECRET_KEY
# 3. Client stores the JWT and sends it in every request header:
#    Authorization: Bearer <token>
# 4. get_current_user() verifies the signature and extracts user_id
# 5. No DB lookup needed to verify the token — the signature
#    proves it was issued by us and hasn't been tampered with
#
# The token contains: user_id (sub), expiry (exp)
# It does NOT contain: password, email, any sensitive data
# =============================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

# ── PASSWORD HASHING ───────────────────────────────────────────
# CryptContext manages the hashing algorithm and auto-upgrades
# old hashes if you ever change the algorithm in the future.

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password. Returns the bcrypt hash string."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored hash.
    Returns True if they match, False otherwise.
    Timing-safe — takes the same time regardless of whether
    the password is correct, preventing timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT CONFIG ─────────────────────────────────────────────────
# SECRET_KEY should be a long random string — never hardcode it.
# In production this comes from an environment variable.
# Generate a good one with: openssl rand -hex 32

from src.config import settings
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours for dev; use 15 min in production


def create_access_token(user_id: str) -> tuple[str, int]:
    """
    Create a signed JWT for a user.

    Returns (token_string, expires_in_seconds).

    Payload:
      sub → subject (user_id) — standard JWT claim
      exp → expiry timestamp — standard JWT claim
      iat → issued at — standard JWT claim
    """
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire        = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode and verify a JWT. Returns user_id (sub) if valid.
    Returns None if the token is expired, tampered, or malformed.
    Never raises — all errors are caught and return None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        return user_id
    except JWTError:
        return None
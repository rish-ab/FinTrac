# =============================================================
# src/api/schemas/auth.py
#
# Pydantic schemas for authentication endpoints.
# These define the shape of requests and responses — completely
# separate from the SQLAlchemy models in src/db/models.py.
#
# WHY SEPARATE SCHEMAS FROM ORM MODELS?
# The ORM model (UserIdentity) contains the password_hash —
# you never want that field appearing in any API response.
# Pydantic schemas let you define exactly what goes in and
# out of each endpoint, independent of the DB structure.
# =============================================================

from pydantic import BaseModel, EmailStr, field_validator


# ── REQUEST SCHEMAS ────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 characters or fewer")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


# ── RESPONSE SCHEMAS ───────────────────────────────────────────

class UserResponse(BaseModel):
    """
    Safe user representation — never includes password_hash.
    model_config from_attributes=True lets Pydantic read from
    SQLAlchemy ORM objects directly (obj.id, obj.email etc.)
    """
    id:         str
    email:      str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token:  str
    token_type:    str = "bearer"
    expires_in:    int             # seconds until expiry
    user:          UserResponse
# =============================================================
# src/api/routes/auth.py
#
# Three endpoints:
#   POST /register  → create account
#   POST /token     → login, get JWT
#   GET  /me        → verify token, return user info
#
# /token uses OAuth2 form format (username + password fields)
# so it works with FastAPI's built-in /docs "Authorize" button.
# This makes manual testing much easier during development.
# =============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.auth import RegisterRequest, TokenResponse, UserResponse
from src.core.dependencies import get_current_user
from src.core.security import create_access_token, hash_password, verify_password
from src.db.models import UserIdentity
from src.db.session import get_db

router = APIRouter()


# ── POST /register ─────────────────────────────────────────────

@router.post(
    "/register",
    response_model = UserResponse,
    status_code    = status.HTTP_201_CREATED,
    summary        = "Create a new account",
)
async def register(
    body: RegisterRequest,
    db:   AsyncSession = Depends(get_db),
) -> UserResponse:

    # Check if email already exists
    existing = await db.execute(
        select(UserIdentity).where(UserIdentity.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = "An account with this email already exists",
        )

    user = UserIdentity(
        email         = body.email,
        password_hash = hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"New user registered: {user.email} (id: {user.id})")
    return UserResponse.model_validate(user)


# ── POST /token ────────────────────────────────────────────────
# OAuth2PasswordRequestForm reads username + password from form data.
# The field is called "username" by the OAuth2 spec even though
# we use email — this is a spec quirk, not a bug.

@router.post(
    "/token",
    response_model = TokenResponse,
    summary        = "Login and get access token",
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db:   AsyncSession              = Depends(get_db),
) -> TokenResponse:

    # Look up user by email (form.username = email in our case)
    result = await db.execute(
        select(UserIdentity).where(UserIdentity.email == form.username)
    )
    user = result.scalar_one_or_none()

    # Same error for "user not found" and "wrong password" —
    # never tell an attacker which one failed (user enumeration)
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Incorrect email or password",
            headers     = {"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(user.id)

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token = token,
        expires_in   = expires_in,
        user         = UserResponse.model_validate(user),
    )


# ── GET /me ────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model = UserResponse,
    summary        = "Get current user info",
)
async def get_me(
    user: UserIdentity = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(user)
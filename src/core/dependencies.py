# =============================================================
# src/core/dependencies.py
#
# FastAPI dependencies — reusable functions injected into routes
# via Depends().
#
# get_current_user() is the auth gate. Any route that includes
# `user: UserIdentity = Depends(get_current_user)` will:
#   1. Extract the Bearer token from the Authorization header
#   2. Decode and verify the JWT
#   3. Look up the user in the DB
#   4. Inject the UserIdentity ORM object into the route
#   5. Return 401 if any step fails
#
# Usage in a route:
#   @router.get("/me")
#   async def get_me(user = Depends(get_current_user)):
#       return {"id": user.id, "email": user.email}
# =============================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import decode_access_token
from src.db.models import UserIdentity
from src.db.session import get_db

# OAuth2PasswordBearer extracts the Bearer token from the
# Authorization header automatically. tokenUrl tells the
# /docs UI where to send login requests for the "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str           = Depends(oauth2_scheme),
    db:    AsyncSession  = Depends(get_db),
) -> UserIdentity:
    """
    Decode the JWT, look up the user, return the ORM object.
    Raises 401 if token is invalid or user doesn't exist.
    """
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail      = "Invalid or expired token",
        headers     = {"WWW-Authenticate": "Bearer"},
    )

    user_id = decode_access_token(token)
    if not user_id:
        raise credentials_exception

    result = await db.execute(
        select(UserIdentity).where(UserIdentity.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    return user
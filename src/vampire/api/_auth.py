"""Optional bearer-token enforcement for the Vampire control API."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vampire.config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_control_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    token = get_settings().auth_token
    if not token:
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error()
    if not hmac.compare_digest(credentials.credentials, token):
        raise _auth_error()


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="missing or invalid bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )

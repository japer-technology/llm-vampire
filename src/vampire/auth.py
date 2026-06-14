"""Bearer-token authentication for configured Vampire gateway tokens."""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse

from vampire.config import get_settings


class AuthError(Exception):
    """Raised when a request lacks the configured gateway bearer token."""


async def auth_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the OpenAI-style authentication error envelope."""
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": str(exc) or "Missing or invalid bearer token.",
                "type": "vampire_auth_error",
                "code": "missing_or_invalid_token",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(request: Request) -> None:
    """Reject requests lacking a valid bearer token when one is configured."""
    token = get_settings().auth_token
    if not token:
        return

    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise AuthError("Missing bearer token.")
    if not hmac.compare_digest(presented, token):
        raise AuthError("Invalid bearer token.")

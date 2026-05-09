from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Cookie, HTTPException, status

from app.config import settings


SESSION_COOKIE_NAME = "dtm_session"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload: str) -> str:
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def verify_admin_credentials(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password,
        settings.admin_password,
    )


def create_session_token(username: str) -> str:
    expires_at = int(time.time()) + settings.session_expire_hours * 3600
    payload = _base64url_encode(
        json.dumps(
            {
                "username": username,
                "exp": expires_at,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload)}"


def read_session_token(token: str) -> dict[str, Any] | None:
    try:
        payload, signature = token.split(".", 1)
    except ValueError:
        return None

    if not hmac.compare_digest(signature, _sign(payload)):
        return None

    try:
        data = json.loads(_base64url_decode(payload).decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None

    if int(data.get("exp", 0)) < int(time.time()):
        return None
    if data.get("username") != settings.admin_username:
        return None

    return data


def require_admin_session(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    if session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "failed",
                "error_code": "unauthorized",
                "message": "login is required",
            },
        )

    session = read_session_token(session_token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "failed",
                "error_code": "unauthorized",
                "message": "session is invalid or expired",
            },
        )

    return session

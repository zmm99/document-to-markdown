from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.config import settings
from app.core.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    require_admin_session,
    verify_admin_credentials,
)
from app.core.response_text import api_error_detail, status_text


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict[str, str]:
    if not verify_admin_credentials(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=api_error_detail("invalid_credentials", "用户名或密码错误"),
        )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(payload.username),
        max_age=settings.session_expire_hours * 3600,
        httponly=True,
        samesite="lax",
    )
    return {
        "status": "success",
        "status_text": status_text("success"),
        "username": payload.username,
    }


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"status": "success", "status_text": status_text("success")}


@router.get("/me")
def me(session: dict[str, Any] = Depends(require_admin_session)) -> dict[str, str]:
    return {
        "status": "success",
        "status_text": status_text("success"),
        "username": str(session["username"]),
    }

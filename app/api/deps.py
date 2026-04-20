from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyCookie

from app.services.auth_service import decode_session_token
from app.services.user_service import get_user_profile

cookie_scheme = APIKeyCookie(name="session_id", auto_error=False)


def require_session_payload(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(cookie_scheme),
):
    """
    Валидирует JWT из cookie `session_id` ДО вызова эндпоинта.

    - Кладёт payload в `request.state.jwt_payload`
    - При отсутствии/битом токене чистит cookie и возвращает 401 (с сигналом на переавторизацию)
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No session",
            headers={"X-Reauthorize": "1", "WWW-Authenticate": "Session"},
        )

    payload = decode_session_token(token)
    if not payload:
        response.delete_cookie(key="session_id")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"X-Reauthorize": "1", "WWW-Authenticate": "Session"},
        )

    request.state.jwt_payload = payload
    return payload  # { "user_id": ..., "username": ..., "exp": ... }


def get_current_user_profile(payload: dict = Depends(require_session_payload)):
    """Возвращает профиль пользователя из БД по user_id из JWT."""
    profile = get_user_profile(payload["user_id"])
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

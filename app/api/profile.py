from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_profile, require_session_payload

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me")
def profile_me(
    profile:  dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Достаёт данные из JWT ДО вызова эндпоинта (через dependency) и возвращает профиль.

    `_payload` здесь не используется напрямую — он нужен, чтобы гарантировать
    `request.state.jwt_payload` для кода ниже/внутренних функций при расширении логики.
    """
    return profile


from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_profile, require_session_payload

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me")
def profile_me(
    profile: dict  = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить профиль текущего авторизованного пользователя.
    
    Возвращает:
        - 200: {
            "id": <user_id>,
            "username": "<username>",
            "balance": <balance>,
            "created_at": "<datetime>",
            "is_bot": <bool>,
            "is_admin": <bool>   // если есть поле в токене
          }
        - 401: Неавторизован (отсутствует или неверный токен)
    """
    return profile
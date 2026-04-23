from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user_profile, require_session_payload
from app.services.user_service import get_user_game_history, get_user_current_game

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


@router.get("/history")
def profile_history(
    limit: int = Query(20, ge=1, le=100),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить историю игр текущего пользователя.
    """
    history = get_user_game_history(profile["id"], limit=limit)
    return {
        "user_id": profile["id"],
        "count": len(history),
        "items": history,
    }


@router.get("/current_game")
def profile_current_game(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить текущую активную игру пользователя для возврата в неё.
    """
    current_game = get_user_current_game(profile["id"])
    return {
        "user_id": profile["id"],
        "has_active_game": bool(current_game),
        "item": current_game,
    }

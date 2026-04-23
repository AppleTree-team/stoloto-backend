from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_profile, require_session_payload, ensure_admin
from app.services.analytic_service import get_game_popularity_with_dynamics, get_bots_status
from app.services.pattern_service import get_loss_warning_pattern_id

router = APIRouter(prefix="/analytic", tags=["Analytic"])


@router.get("/game-popularity")
def get_game_popularity(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить популярность игр: процент игроков за последние 7 дней и динамику к предыдущей неделе.

    **Требования:** права администратора.

    Возвращает:
        - 200: [
            {
                "game": "plinko",
                "percent": 45.5,
                "dynamics_percent": 5.2
            },
            ...
          ]
        - 401: Неавторизован
        - 403: Доступ запрещён (не администратор)
    """
    ensure_admin(profile)
    games = get_game_popularity_with_dynamics()
    return games

@router.get("/patterns-top")
def get_top_patterns(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить топ 10 самых популярных паттернов (по количеству реальных игроков).

    **Требования:** права администратора.

    Возвращает:
        - 200: [
            {
                "id": 3,
                "game": "wheel",
                "real_players": 234,
                "join_cost": 100,
                "profit": 12450
            },
            ...
          ]
        - 401: Неавторизован
        - 403: Доступ запрещён (не администратор)
    """
    ensure_admin(profile)
    paterns = get_top_patterns()
    return paterns

@router.get("/loss-warning")
def get_loss_warning(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить ID паттерна, который убыточен 7 дней подряд (если есть).

    **Требования:** права администратора.

    Возвращает:
        - 200: { "pattern_id": 5 }  // если есть убыточный паттерн
        - 401: Неавторизован
        - 403: Доступ запрещён (не администратор)
    """
    ensure_admin(profile)
    pattern_id = get_loss_warning_pattern_id()
    return {"pattern_id": pattern_id}

@router.get("/bots-status")
def get_bots_status_endpoint(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить статус ботов: количество активных и общее количество.

    **Требования:** права администратора.

    Возвращает:
        - 200: { "active_bots": 87, "total_bots": 100 }
        - 401: Неавторизован
        - 403: Доступ запрещён (не администратор)
    """
    ensure_admin(profile)
    return get_bots_status()
from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.deps import get_current_user_profile, require_session_payload, ensure_admin
from app.services.analytic_service import (
    get_game_popularity_with_dynamics,
    get_bots_status,
    get_top_patterns as get_top_patterns_service,
    get_kpi as get_kpi_service,
    get_funnel as get_funnel_service,
    get_revenue_series as get_revenue_series_service,
    get_top_players as get_top_players_service,
    get_top_rooms as get_top_rooms_service,
)
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
    patterns = get_top_patterns_service(limit=10)
    return patterns


@router.get("/kpi")
def get_kpi(
    days: int = Query(7, ge=1, le=365),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return get_kpi_service(days=days)


@router.get("/funnel")
def get_funnel(
    days: int = Query(7, ge=1, le=365),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return get_funnel_service(days=days)


@router.get("/revenue-series")
def get_revenue_series(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day", description="day | hour"),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    if bucket not in ("day", "hour"):
        raise HTTPException(status_code=400, detail="bucket must be 'day' or 'hour'")
    return get_revenue_series_service(days=days, bucket=bucket)  # type: ignore[arg-type]


@router.get("/top-players")
def get_top_players(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=200),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return get_top_players_service(days=days, limit=limit)


@router.get("/top-rooms")
def get_top_rooms(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=200),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return get_top_rooms_service(days=days, limit=limit)





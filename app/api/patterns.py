from typing import Optional
from fastapi import APIRouter, Depends, Body, HTTPException, Query

from app.services import pattern_service
from app.api.deps import get_current_user_profile, require_session_payload, ensure_admin


router = APIRouter(prefix="/patterns", tags=["Patterns"])


def check_pattern_exists(pattern_id):
    """ Проверяем наличие паттерна """
    existing = pattern_service.get_pattern_by_id(pattern_id)
    if not existing or not existing["is_active"]:
        raise HTTPException(status_code=404, detail="Pattern not found")


@router.get("/limit")
def get_limit(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить текущее максимальное количество комнат (лимит).

    **Требования:** права администратора.

    Возвращает:
        - 200: { "status": "success", "max_room_count": <int> }
        - 401: Неавторизован
        - 403: Доступ запрещён (не администратор)
    """
    ensure_admin(profile)
    count = pattern_service.get_max_rooms_count()
    return {
        "status": "success",
        "max_room_count": count
    }


@router.put("/limit/{new_limit}")
def update_limit(
    new_limit: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Установить новое максимальное количество комнат (лимит).

    **Параметр пути:**
        - `new_limit` (int): Новое значение лимита.

    **Требования:** права администратора.
    """
    ensure_admin(profile)
    pattern_service.set_max_rooms_count(new_limit)
    return {
        "status": "success",
        "message": "Max rooms count updated"
    }


@router.get("/")
def get_patterns(
    disabled: Optional[str] = Query(None, description="Используйте ?disabled или ?disabled=true для неактивных"),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить все паттерны (только для администратора).
    """
    ensure_admin(profile)
    if disabled is not None:
        return pattern_service.get_all_disabled_patterns()
    return pattern_service.get_all_active_patterns()


@router.post("/")
def create_pattern(
    data: dict = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Создать новый паттерн (только для администратора).

    Тело запроса (JSON):
    - game (str): название игры
    - join_cost (int): стоимость входа
    - max_members_count (int): максимум участников
    - rank (float): рейк казино в процентах
    - waiting_lobby_stage (int): время ожидания в lobby
    - waiting_shop_stage (int): время ожидания в shop
    - max_rooms_count (int): максимум комнат для паттерна
    - weight (float): вес для матчмейкинга, должен быть > 0
    - boost_cost_per_point (int): стоимость 1 поинта буста
    - winner_payout_percent (int): историческое поле, сейчас используется как 100
    """
    ensure_admin(profile)
    try:
        pattern_id = pattern_service.create_pattern(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "message": "Pattern created successfully",
        "id": pattern_id
    }


@router.put("/{pattern_id}")
def update_pattern(
    pattern_id: int,
    data: dict = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Полностью обновить существующий паттерн (только для администратора).
    """
    ensure_admin(profile)
    check_pattern_exists(pattern_id)
    try:
        updated_id = pattern_service.update_pattern(pattern_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "message": "Pattern updated successfully",
        "id": updated_id
    }


@router.delete("/{pattern_id}")
def delete_pattern(
    pattern_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Мягкое удаление паттерна по ID (только для администратора).
    """
    ensure_admin(profile)
    check_pattern_exists(pattern_id)
    pattern_service.delete_pattern(pattern_id)
    return {
        "status": "success",
        "message": "Sucessfully deleted",
        "id": pattern_id
    }

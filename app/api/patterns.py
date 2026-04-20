from fastapi import APIRouter, Depends, Body, HTTPException
from app.services import pattern_service
from app.api.deps import get_current_user_profile, require_session_payload, ensure_admin

router = APIRouter(prefix="/patterns", tags=["Patterns"])



def check_pattern_exists(pattern_id):
    """ Check if pattern exists """
    existing = pattern_service.get_pattern_by_id(pattern_id)
    if not existing or not existing["is_active"]:
        raise HTTPException(status_code=404, detail="Pattern not found")






def check_pattern_exists(pattern_id):
    """Проверяет, существует ли паттерн и активен ли он."""
    existing = pattern_service.get_pattern_by_id(pattern_id)
    if not existing or not existing["is_active"]:
        raise HTTPException(status_code=404, detail="Pattern not found")


@router.get("/")
def get_patterns(
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """
    Получить все паттерны (только для администратора).

    Возвращает список всех паттернов (комнат) в системе.
    Требуется JWT токен и права администратора.

    Ответы:
        - 200: Список паттернов.
        - 401: Неавторизован (неверный или отсутствует токен).
        - 403: Доступ запрещён (не администратор).
        - 500: Внутренняя ошибка сервера.
    """
    ensure_admin(profile)
    return pattern_service.get_all_patterns()


@router.post("/")
def create_pattern(
        data: dict = Body(...),
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """
    Создать новый паттерн (только для администратора).

    Тело запроса (JSON):
    - game (str): Название игры (например, "poker")
    - join_cost (int): Стоимость входа
    - max_members_count (int): Максимум участников (2-10)
    - rank (str): Ранг комнаты (например, "beginner")
    - min_bots_count (int): Минимальное количество ботов
    - max_bots_count (int): Максимальное количество ботов
    - waiting_lobby_stage (int): Время ожидания в лобби (секунды)
    - waiting_shop_stage (int): Время ожидания в магазине (секунды)
    - max_rooms_count (int): Максимальное количество комнат
    - weight (float): Вес для матчинга (0-1)

    Возвращает:
        - 200: { "status": "success", "message": "...", "id": <id_паттерна> }
        - 400: Неверные данные
        - 401: Неавторизован
        - 403: Доступ запрещён
    """
    ensure_admin(profile)
    pattern_id = pattern_service.create_pattern(data)
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

    Параметр пути:
        - pattern_id (int): ID обновляемого паттерна.

    Тело запроса: те же поля, что и в POST /patterns (все обязательны).

    Возвращает:
        - 200: { "status": "success", "message": "...", "id": <id_новой_версии> }
        - 404: Паттерн не найден или неактивен
        - 401: Неавторизован
        - 403: Доступ запрещён
    """
    ensure_admin(profile)
    check_pattern_exists(pattern_id)
    updated_id = pattern_service.update_pattern(pattern_id, data)
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

    Параметр пути:
        - pattern_id (int): ID удаляемого паттерна.

    Помечает паттерн как неактивный (мягкое удаление). Остаётся в базе данных для истории.

    Возвращает:
        - 200: { "status": "success", "message": "...", "id": <pattern_id> }
        - 404: Паттерн не найден или уже неактивен
        - 401: Неавторизован
        - 403: Доступ запрещён
    """
    ensure_admin(profile)
    check_pattern_exists(pattern_id)
    pattern_service.delete_pattern(pattern_id)
    return {
        "status": "success",
        "message": "Sucessfully deleted",
        "id": pattern_id
    }
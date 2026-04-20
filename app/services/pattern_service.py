from typing import List, Dict, Any, Optional

from app.db.db import fetch, execute


# =========================================
# ⚙️ SYSTEM CONFIG
# =========================================

def get_max_active_rooms() -> int:
    """
    Получить глобальный лимит активных комнат
    """
    query = """
        SELECT max_active_rooms
        FROM system_config
        WHERE id = 1
    """
    result = fetch(query)
    return result[0]["max_active_rooms"] if result else 0


# =========================================
# 📤 GET PATTERNS
# =========================================

def get_all_patterns(game: str) -> List[Dict[str, Any]]:
    """
    Все паттерны (включая неактивные)
    """
    query = """
        SELECT *
        FROM room_pattern
        WHERE game = %s
        ORDER BY id DESC
    """
    return fetch(query, (game,))


def get_pattern_by_id(pattern_id: int) -> Optional[Dict[str, Any]]:
    """
    Один паттерн по id
    """
    query = """
        SELECT *
        FROM room_pattern
        WHERE id = %s
    """
    result = fetch(query, (pattern_id,))
    return result[0] if result else None


def export_patterns(game: str) -> Dict[str, Any]:
    """
    Полный JSON для админки
    """
    return {
        "game": game,
        "max_active_rooms": get_max_active_rooms(),
        "patterns": get_all_patterns(game)
    }


# =========================================
# ➕ CREATE PATTERN
# =========================================

def create_pattern(data: Dict[str, Any]) -> int:
    """
    Создаёт новый паттерн (всегда новая запись)
    """
    query = """
        INSERT INTO room_pattern (
            game,
            join_cost,
            max_members_count,
            rank,
            min_bots_count,
            max_bots_count,
            waiting_lobby_stage,
            waiting_shop_stage,
            max_rooms_count,
            is_active,
            weight
        )
        VALUES (
            %(game)s,
            %(join_cost)s,
            %(max_members_count)s,
            %(rank)s,
            %(min_bots_count)s,
            %(max_bots_count)s,
            %(waiting_lobby_stage)s,
            %(waiting_shop_stage)s,
            %(max_rooms_count)s,
            TRUE,
            %(weight)s
        )
        RETURNING id
    """
    result = fetch(query, data)
    return result[0]["id"]


# =========================================
# 🔁 UPDATE (VERSIONING)
# =========================================

def update_pattern(old_pattern_id: int, new_data: Dict[str, Any]) -> int:
    """
    Обновление через создание новой версии:
    - старый паттерн деактивируется
    - создаётся новый
    """
    execute("""
        UPDATE room_pattern
        SET is_active = FALSE
        WHERE id = %s
    """, (old_pattern_id,))

    return create_pattern(new_data)


# =========================================
# 🟢 ACTIVATE / DEACTIVATE
# =========================================

def set_pattern_active(pattern_id: int, active: bool) -> None:
    """
    Включить / выключить паттерн
    """
    execute("""
        UPDATE room_pattern
        SET is_active = %s
        WHERE id = %s
    """, (active, pattern_id))


def bulk_activate_patterns(pattern_ids: List[int]) -> None:
    if not pattern_ids:
        return

    execute("""
        UPDATE room_pattern
        SET is_active = TRUE
        WHERE id = ANY(%s)
    """, (pattern_ids,))


def bulk_deactivate_patterns(pattern_ids: List[int]) -> None:
    if not pattern_ids:
        return

    execute("""
        UPDATE room_pattern
        SET is_active = FALSE
        WHERE id = ANY(%s)
    """, (pattern_ids,))
from typing import List, Dict, Any, Optional

from app.db.db import fetch_one, fetch_all, execute, execute_with_returning


# =========================================
# ⚙️ SYSTEM CONFIG
# =========================================

def get_max_rooms_count():
    """
    Максимальное кол-во комнат
    """
    data.setdefault("boost_cost_per_point", 10)
    data.setdefault("winner_payout_percent", 80)
    query = """
            SELECT max_active_rooms
            FROM system_config
            """
    q = fetch_one(query)
    return q["max_active_rooms"]


def set_max_rooms_count(new_count):
    execute("""
            UPDATE system_config
            SET max_active_rooms = %s
            """, (new_count,))

# =========================================
# 📤 GET PATTERNS
# =========================================

def get_all_active_patterns() -> List[Dict[str, Any]]:
    """
    Все паттерны (только активные)
    """
    query = """
        SELECT *
        FROM room_pattern
        WHERE is_active = TRUE
        ORDER BY id DESC
    """
    return fetch_all(query)

def get_all_disabled_patterns() -> List[Dict[str, Any]]:
    """
    Все паттерны (включая неактивные)
    """
    query = """
        SELECT *
        FROM room_pattern
        WHERE is_active = FALSE
        ORDER BY deleted_at DESC
    """
    return fetch_all(query)

def get_pattern_by_id(pattern_id: int) -> Optional[Dict[str, Any]]:
    """
    Один паттерн по id
    """
    query = """
        SELECT *
        FROM room_pattern
        WHERE id = %s
    """
    result = fetch_one(query, (pattern_id,))
    return result

def get_pattern_by_game_and_cost(game: str, min_cost: int, max_cost: int) -> Optional[Dict]:
    """
    Возвращает самый дорогой паттерн комнаты для указанной игры и стоимости входа.
    """
    return fetch_one("""
        SELECT *
        FROM room_pattern
        WHERE game = %s 
        AND join_cost BETWEEN %s AND %s
        AND is_active = TRUE
        ORDER BY join_cost DESC
        LIMIT 1
    """, (game, min_cost, max_cost))


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
            weight,
            boost_cost_per_point,
            winner_payout_percent
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
            %(weight)s,
            %(boost_cost_per_point)s,
            %(winner_payout_percent)s
        )
        RETURNING id
    """
    result = execute_with_returning(query, data)
    return result["id"]



def delete_pattern(pattern_id: int) -> bool:
    execute("""
        UPDATE room_pattern
        SET is_active = FALSE, deleted_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (pattern_id,))
    return True


def update_pattern(old_pattern_id: int, new_data: Dict[str, Any]) -> int:
    """
    Обновление через создание новой версии:
    - старый паттерн деактивируется
    - создаётся новый
    """
    delete_pattern(old_pattern_id)

    return create_pattern(new_data)

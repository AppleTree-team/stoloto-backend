from typing import List, Dict, Any, Optional

from app.db.db import fetch_one, fetch_all, execute, execute_with_returning


def _validate_pattern_payload(data: Dict[str, Any]) -> None:
    cfg = fetch_one("""
        SELECT
            COALESCE(min_join_cost, 0)::bigint AS min_join_cost,
            COALESCE(max_join_cost, 1000000000)::bigint AS max_join_cost
        FROM system_config
        WHERE id = 1
    """) or {"min_join_cost": 0, "max_join_cost": 1000000000}

    if "join_cost" in data:
        try:
            join_cost = int(data.get("join_cost"))
        except (TypeError, ValueError):
            raise ValueError("join_cost must be an integer")

        if join_cost <= 0:
            raise ValueError("join_cost must be > 0")

        min_join_cost = int(cfg.get("min_join_cost") or 0)
        max_join_cost = int(cfg.get("max_join_cost") or 1000000000)
        if join_cost < min_join_cost or join_cost > max_join_cost:
            raise ValueError(f"join_cost must be between {min_join_cost} and {max_join_cost}")

    if "rank" in data:
        try:
            rank = float(data.get("rank"))
        except (TypeError, ValueError):
            raise ValueError("rank must be a number")
        if rank < 0 or rank > 100:
            raise ValueError("rank must be between 0 and 100")

    try:
        weight = float(data.get("weight"))
    except (TypeError, ValueError):
        raise ValueError("Pattern weight must be greater than 0")

    if weight <= 0:
        raise ValueError("Pattern weight must be greater than 0")


# =========================================
# ⚙️ SYSTEM CONFIG
# =========================================

def get_max_rooms_count() -> int:
    """
    Максимальное кол-во комнат
    """
    query = """
            SELECT max_active_rooms
            FROM system_config
            """
    q = fetch_one(query)
    if not q or q.get("max_active_rooms") is None:
        return 50
    return int(q["max_active_rooms"])


def set_max_rooms_count(new_count):
    execute("""
            UPDATE system_config
            SET max_active_rooms = %s
            WHERE id = 1
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
    Возвращает случайный паттерн комнаты для указанной игры и стоимости входа.
    Вероятность выбора паттерна пропорциональна его весу.
    """
    return fetch_one("""
        SELECT *
        FROM room_pattern
        WHERE game = %s 
        AND join_cost BETWEEN %s AND %s
        AND is_active = TRUE
        AND weight > 0
        ORDER BY -LN(RANDOM()) / weight
        LIMIT 1
    """, (game, min_cost, max_cost))


def get_top_patterns(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Возвращает топ N паттернов по количеству реальных игроков.
    Поля: id, game, real_players, join_cost, profit.
    """
    query = """
    SELECT 
        rp.id,
        rp.game,
        COUNT(DISTINCT rm.user_id) FILTER (WHERE NOT u.is_bot) AS real_players,
        rp.join_cost,
        COALESCE(SUM(le.amount) FILTER (WHERE le.account = 'casino' AND le.entry_type = 'casino_income'), 0) -
        COALESCE(SUM(le.amount) FILTER (WHERE le.account = 'casino' AND le.entry_type = 'bot_slots'), 0) AS profit
    FROM room_pattern rp
    LEFT JOIN rooms r ON r.room_pattern_id = rp.id
    LEFT JOIN room_members rm ON rm.room_id = r.id
    LEFT JOIN users u ON u.id = rm.user_id
    LEFT JOIN ledger_entries le ON le.room_id = r.id
    WHERE rp.deleted_at IS NULL
    GROUP BY rp.id, rp.game, rp.join_cost
    ORDER BY real_players DESC, profit DESC
    LIMIT %s;
    """
    return fetch_all(query, (limit,))

def get_loss_warning_pattern_id() -> int | None:
    """
    Возвращает ID первого убыточного паттерна (7 дней подряд) или None.
    """
    query = """
    WITH daily_profit AS (
        SELECT 
            r.room_pattern_id,
            DATE(r.created_at) AS day,
            COALESCE(SUM(le.amount), 0) AS daily_profit
        FROM rooms r
        JOIN ledger_entries le ON le.room_id = r.id
        WHERE le.account = 'casino' AND le.entry_type = 'casino_income'
          AND r.created_at > NOW() - INTERVAL '7 days'
        GROUP BY r.room_pattern_id, DATE(r.created_at)
    ),
    loss_days AS (
        SELECT 
            room_pattern_id
        FROM daily_profit
        GROUP BY room_pattern_id
        HAVING COUNT(DISTINCT day) = 7 AND BOOL_AND(daily_profit < 0) = TRUE
    )
    SELECT id
    FROM room_pattern rp
    JOIN loss_days ld ON ld.room_pattern_id = rp.id
    WHERE rp.is_active = TRUE AND rp.deleted_at IS NULL
    LIMIT 1
    """
    row = fetch_one(query)
    return row["id"] if row else None

# =========================================
# ➕ CREATE PATTERN
# =========================================

def create_pattern(data: Dict[str, Any]) -> int:
    """
    Создаёт новый паттерн (всегда новая запись)
    """
    _validate_pattern_payload(data)
    data.setdefault("boost_cost_per_point", 10)
    data.setdefault("winner_payout_percent", 100)
    query = """
        INSERT INTO room_pattern (
            game,
            join_cost,
            max_members_count,
            rank,
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

from app.db.db import fetch
from app.services.room_service import create_room, add_user_to_room


# ========================
# CONFIG
# ========================
MAX_ROOMS_PER_PATTERN = 50


# ========================
# MAIN ENTRY (MATCHMAKING)
# ========================
def join_game(user_id: int, game: str, join_cost: int):
    # 1. получить или создать паттерн
    pattern = get_or_create_pattern(game, join_cost)

    # 2. найти подходящую комнату
    room = find_available_room(pattern["id"])

    # 3. если нет — создать новую (если не превышен лимит)
    if not room:
        if not can_create_room(pattern["id"]):
            raise Exception("Room limit reached for this pattern")

        room = create_room(pattern["id"])

    # 4. добавить пользователя в комнату
    add_user_to_room(room["id"], user_id)

    return room["id"]


# ========================
# PATTERN LOGIC
# ========================
def get_or_create_pattern(game: str, join_cost: int):
    pattern = fetch(
        """
        SELECT *
        FROM room_pattern
        WHERE game = %s AND join_cost = %s
        LIMIT 1
        """,
        (game, join_cost)
    )

    if pattern:
        return pattern

    return fetch(
        """
        INSERT INTO room_pattern (
            game,
            join_cost,
            max_members_count,
            rank,
            min_bots_count,
            max_bots_count,
            waiting_lobby_stage,
            waiting_shop_stage
        )
        VALUES (%s, %s, 10, 1.0, 1, 3, 60, 30)
        RETURNING *
        """,
        (game, join_cost)
    )


# ========================
# ROOM FINDING
# ========================
def find_available_room(pattern_id: int):
    room = fetch(
        """
        SELECT r.id
        FROM rooms r
        JOIN room_pattern rp ON r.room_pattern_id = rp.id
        WHERE r.room_pattern_id = %s
          AND r.status IN ('waiting', 'lobby')
          AND (
              SELECT COUNT(*)
              FROM room_members rm
              WHERE rm.room_id = r.id
          ) < rp.max_members_count
        ORDER BY r.created_at ASC
        LIMIT 1
        """,
        (pattern_id,)
    )

    return room


# ========================
# LIMIT CONTROL
# ========================
def can_create_room(pattern_id: int):
    pattern = fetch(
        """
        SELECT max_rooms_count
        FROM room_pattern
        WHERE id = %s
        """,
        (pattern_id,)
    )

    result = fetch(
        """
        SELECT COUNT(*) as count
        FROM rooms
        WHERE room_pattern_id = %s
          AND status IN ('waiting', 'lobby', 'running')
        """,
        (pattern_id,)
    )

    return result["count"] < pattern["max_rooms_count"]

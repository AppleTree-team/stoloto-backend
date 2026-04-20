from app.db.db import fetch
from app.services.room_service import add_user_to_room_tx, create_room, add_user_to_room


# ========================
# CONFIG
# ========================
MAX_ROOMS_PER_PATTERN = 50


# ========================
# MAIN ENTRY (MATCHMAKING)
# ========================
from app.db.db import get_connection_cursor
from app.services.room_service import add_user_to_room  # переделаем или вызовем внутри

def join_game(user_id: int, game: str, join_cost: int):
    with get_connection_cursor() as (conn, cursor):
        # 1. Получить или создать паттерн с блокировкой
        cursor.execute(
            "SELECT * FROM room_pattern WHERE game = %s AND join_cost = %s",
            (game, join_cost)
        )
        pattern = cursor.fetchone()
        if not pattern:
            cursor.execute(
                """
                INSERT INTO room_pattern (
                    game, join_cost, max_members_count, rank,
                    min_bots_count, max_bots_count,
                    waiting_lobby_stage, waiting_shop_stage,
                    max_rooms_count
                ) VALUES (%s, %s, 10, 1.0, 1, 3, 60, 30, 50)
                RETURNING *
                """,
                (game, join_cost)
            )
            pattern = cursor.fetchone()
        else:
            # Блокируем строку паттерна, чтобы никто другой не мог одновременно создавать комнаты
            cursor.execute(
                "SELECT * FROM room_pattern WHERE id = %s FOR UPDATE",
                (pattern["id"],)
            )

        # 2. Найти доступную комнату (с блокировкой найденной строки)
        cursor.execute(
            """
            SELECT r.id
            FROM rooms r
            LEFT JOIN room_members rm ON rm.room_id = r.id
            JOIN room_pattern rp ON r.room_pattern_id = rp.id
            WHERE r.room_pattern_id = %s
              AND r.status IN ('waiting', 'lobby')
            GROUP BY r.id, rp.max_members_count
            HAVING COUNT(rm.id) < rp.max_members_count
            ORDER BY r.created_at ASC
            LIMIT 1
            FOR UPDATE OF r SKIP LOCKED
            """,
            (pattern["id"],)
        )
        room = cursor.fetchone()

        # 3. Если нет – проверить лимит и создать
        if not room:
            # Проверяем текущее количество активных комнат
            cursor.execute(
                "SELECT max_rooms_count FROM room_pattern WHERE id = %s",
                (pattern["id"],)
            )
            max_rooms = cursor.fetchone()["max_rooms_count"]

            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM rooms
                WHERE room_pattern_id = %s
                  AND status IN ('waiting', 'lobby', 'running')
                """,
                (pattern["id"],)
            )
            active_count = cursor.fetchone()["count"]

            if active_count >= max_rooms:
                raise Exception("Room limit reached for this pattern")

            # Создаём комнату внутри этой же транзакции
            import uuid
            token = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO rooms (room_pattern_id, websocket_access_token) VALUES (%s, %s) RETURNING *",
                (pattern["id"], token)
            )
            room = cursor.fetchone()

        room_id = room["id"]

        # 4. Добавить пользователя в комнату (используем текущий курсор)
        add_user_to_room_tx(cursor, room_id, user_id)

        return room_id


# ========================
# ROOM LISTING
# ========================
def list_available_rooms(game: str, join_cost: int):
    """
    Возвращает список комнат, доступных для входа.
    """
    pattern = fetch(
        "SELECT id, max_members_count FROM room_pattern WHERE game = %s AND join_cost = %s",
        (game, join_cost)
    )
    if not pattern:
        return []

    rooms = fetch(
        """
        SELECT
            r.id,
            r.status,
            r.created_at,
            COUNT(rm.user_id) AS current_players,
            rp.max_members_count AS max_players
        FROM rooms r
        JOIN room_pattern rp ON r.room_pattern_id = rp.id
        LEFT JOIN room_members rm ON rm.room_id = r.id
        WHERE r.room_pattern_id = %s
          AND r.status IN ('waiting', 'lobby')
        GROUP BY r.id, rp.max_members_count
        HAVING COUNT(rm.user_id) < rp.max_members_count
        ORDER BY r.created_at ASC
        """,
        (pattern["id"],),
        many=True
    )
    return rooms


# ========================
# JOIN SPECIFIC ROOM
# ========================
def join_room_by_id(user_id: int, room_id: int):
    """
    Добавляет пользователя в конкретную комнату, проверяя её доступность.
    """
    with get_connection_cursor() as (conn, cursor):
        # Блокируем комнату и проверяем, можно ли войти
        cursor.execute(
            """
            SELECT r.id, rp.max_members_count,
                   (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) AS current
            FROM rooms r
            JOIN room_pattern rp ON r.room_pattern_id = rp.id
            WHERE r.id = %s
              AND r.status IN ('waiting', 'lobby')
            FOR UPDATE OF r
            """,
            (room_id,)
        )
        room_info = cursor.fetchone()
        if not room_info:
            raise Exception("Room not found or not joinable")

        if room_info["current"] >= room_info["max_members_count"]:
            raise Exception("Room is full")

        # Проверяем, не состоит ли пользователь уже в другой активной комнате
        cursor.execute(
            """
            SELECT 1 FROM room_members rm
            JOIN rooms r ON rm.room_id = r.id
            WHERE rm.user_id = %s AND r.status IN ('waiting', 'lobby', 'running')
            """,
            (user_id,)
        )
        if cursor.fetchone():
            raise Exception("User already in an active room")

        # Добавляем пользователя
        add_user_to_room_tx(cursor, room_id, user_id)

        return room_id

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

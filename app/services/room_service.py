from app.db.db import fetch, execute
from datetime import datetime
import uuid
import random


# --------------------
# CREATE ROOM
# --------------------
def create_room(room_pattern_id: int):
    token = str(uuid.uuid4())

    room = fetch(
        """
        INSERT INTO rooms (room_pattern_id, websocket_access_token)
        VALUES (%s, %s)
        RETURNING *
        """,
        (room_pattern_id, token)
    )

    return room


# --------------------
# GET ROOM
# --------------------
def get_room(room_id: int):
    return fetch(
        "SELECT * FROM rooms WHERE id = %s",
        (room_id,)
    )


# --------------------
# GET ROOM MEMBERS
# --------------------
def get_room_members(room_id: int):
    members = fetch(
        """
        SELECT * FROM room_members
        WHERE room_id = %s
        """,
        (room_id,)
    )

    if not members:
        return []

    if isinstance(members, dict):
        return [members]

    return members


# --------------------
# COUNT MEMBERS
# --------------------
def count_members(room_id: int) -> int:
    result = fetch(
        """
        SELECT COUNT(*) as count
        FROM room_members
        WHERE room_id = %s
        """,
        (room_id,)
    )

    return result["count"]


# --------------------
# ADD USER TO ROOM
# --------------------
def add_user_to_room(room_id: int, user_id: int):
    # проверка: уже есть?
    existing = fetch(
        """
        SELECT 1 FROM room_members
        WHERE room_id = %s AND user_id = %s
        """,
        (room_id, user_id)
    )

    if existing:
        return

    # лимит комнаты
    room = fetch(
        """
        SELECT rp.max_members_count
        FROM rooms r
        JOIN room_pattern rp ON r.room_pattern_id = rp.id
        WHERE r.id = %s
        """,
        (room_id,)
    )

    current_count = count_members(room_id)

    if current_count >= room["max_members_count"]:
        raise Exception("Room is full")

    # добавляем
    execute(
        """
        INSERT INTO room_members (room_id, user_id)
        VALUES (%s, %s)
        """,
        (room_id, user_id)
    )

    # если первый игрок → lobby
    if current_count == 0:
        set_room_status(room_id, "lobby")


# --------------------
# SET STATUS
# --------------------
def set_room_status(room_id: int, status: str):
    execute(
        """
        UPDATE rooms
        SET status = %s
        WHERE id = %s
        """,
        (status, room_id)
    )


# --------------------
# START GAME
# --------------------
def start_game(room_id: int):
    execute(
        """
        UPDATE rooms
        SET status = 'running',
            started_at = %s
        WHERE id = %s
        """,
        (datetime.utcnow(), room_id)
    )


# --------------------
# FINISH GAME
# --------------------
def finish_game(room_id: int, winner_id: int):
    execute(
        """
        UPDATE rooms
        SET status = 'finished',
            winner_id = %s,
            ended_at = %s
        WHERE id = %s
        """,
        (winner_id, datetime.utcnow(), room_id)
    )


# --------------------
# CALCULATE WINNER
# --------------------
def calculate_winner(room_id: int):
    members = get_room_members(room_id)

    if not members:
        return None

    # веса (boost влияет)
    weighted = []

    for m in members:
        weight = 1 + m.get("boost", 0)
        weighted.extend([m["user_id"]] * weight)

    winner_id = random.choice(weighted)

    return winner_id


# --------------------
# RUN FULL GAME
# --------------------
def run_game(room_id: int):
    # старт
    start_game(room_id)

    # считаем победителя
    winner_id = calculate_winner(room_id)

    # завершаем
    finish_game(room_id, winner_id)

    return winner_id




#class RoomService:

    # --------------------
    # ROOM MANAGEMENT
    # --------------------
    #def create_room(): ...
    #def join_room(): ...

    # --------------------
    # GAME ENGINE (внутри)
    # --------------------
    #def start_game(): ...
    #def update_state(): ...
    #def finish_game(): ...
from app.db.db import fetch
from datetime import datetime
import random


# =========================================================
# 🧩 CREATE ROOM
# =========================================================
def create_room(pattern_id: int):
    room = fetch("""
        INSERT INTO rooms (room_pattern_id, websocket_access_token)
        VALUES (%s, gen_random_uuid()::text)
        RETURNING *
    """, (pattern_id,))

    return room


# =========================================================
# 👤 ADD USER SLOTS
# =========================================================
def add_user_slots(room_id: int, user_id: int, slots_count: int, boost: int = 0):
    """
    пользователь занимает N слотов в комнате
    """

    room = fetch("""
        SELECT * FROM rooms
        WHERE id = %s
        FOR UPDATE
    """, (room_id,))

    if not room:
        raise Exception("Room not found")

    if room["status"] not in ("waiting", "lobby"):
        raise Exception("Room is not joinable")


    pattern = fetch("""
        SELECT * FROM room_pattern
        WHERE id = %s
    """, (room["room_pattern_id"],))


    # текущие слоты
    current_slots = fetch("""
        SELECT COUNT(*) as count
        FROM room_members
        WHERE room_id = %s
    """, (room_id,))["count"]

    if current_slots + slots_count > pattern["max_members_count"]:
        raise Exception("Not enough free slots")


    # 💰 списание с пользователя
    total_cost = slots_count * pattern["join_cost"]

    updated = fetch("""
        UPDATE users
        SET balance = balance - %s
        WHERE id = %s AND balance >= %s
        RETURNING id
    """, (total_cost, user_id, total_cost))

    if not updated:
        raise Exception("Not enough balance")


    # ➕ добавляем слоты
    for _ in range(slots_count):
        fetch("""
            INSERT INTO room_members (room_id, user_id, boost)
            VALUES (%s, %s, %s)
        """, (room_id, user_id, boost))


    # 🟡 первый игрок → перевод в lobby
    if room["status"] == "waiting":
        fetch("""
            UPDATE rooms
            SET status = 'lobby'
            WHERE id = %s
        """, (room_id,))


        # сигнал scheduler-у
        return {
            "first_player": True,
            "spawn_bots_delay": pattern["waiting_lobby_stage"]
        }

    return {"first_player": False}


# =========================================================
# 🤖 ADD BOT SLOTS
# =========================================================
def add_bot_slots(room_id: int, bot_id: int, slots_count: int):
    """
    бот занимает N слотов (оплата из казино)
    """

    room = fetch("""
        SELECT * FROM rooms
        WHERE id = %s
        FOR UPDATE
    """, (room_id,))

    if room["status"] != "lobby":
        return


    pattern = fetch("""
        SELECT * FROM room_pattern
        WHERE id = %s
    """, (room["room_pattern_id"],))


    total_cost = slots_count * pattern["join_cost"]

    casino = fetch("""
        SELECT * FROM casino_balance
        WHERE id = 1
    """)

    if casino["balance"] < total_cost:
        return


    # 💸 списываем казино
    fetch("""
        UPDATE casino_balance
        SET balance = balance - %s
        WHERE id = 1
    """, (total_cost,))


    # ➕ добавляем слоты
    for _ in range(slots_count):
        fetch("""
            INSERT INTO room_members (room_id, user_id, boost)
            VALUES (%s, %s, 0)
        """, (room_id, bot_id))


# =========================================================
# 🔍 GET MEMBERS
# =========================================================
def get_room_members(room_id: int):
    return fetch("""
        SELECT rm.user_id, rm.boost, u.is_bot
        FROM room_members rm
        JOIN users u ON u.id = rm.user_id
        WHERE rm.room_id = %s
    """, (room_id,))


# =========================================================
# ✅ CAN START
# =========================================================
def can_start(room_id: int) -> bool:
    room = fetch("SELECT * FROM rooms WHERE id = %s", (room_id,))
    pattern = fetch("""
        SELECT * FROM room_pattern
        WHERE id = %s
    """, (room["room_pattern_id"],))

    count = fetch("""
        SELECT COUNT(*) as count
        FROM room_members
        WHERE room_id = %s
    """, (room_id,))["count"]

    return count >= pattern["min_bots_count"]


# =========================================================
# 🎮 RUN GAME
# =========================================================
def run_game(room_id: int):
    """
    основной запуск игры
    """

    room = fetch("""
        SELECT * FROM rooms
        WHERE id = %s
        FOR UPDATE
    """, (room_id,))

    if room["status"] != "lobby":
        return


    # 🚀 перевод в running
    fetch("""
        UPDATE rooms
        SET status = 'running',
            started_at = NOW()
        WHERE id = %s
    """, (room_id,))


    pattern = fetch("""
        SELECT * FROM room_pattern
        WHERE id = %s
    """, (room["room_pattern_id"],))


    members = get_room_members(room_id)


    # 🎯 веса
    weighted = []
    total_pool = 0

    for m in members:
        weight = 1 + m["boost"]
        weighted.append((m["user_id"], weight, m["is_bot"]))
        total_pool += pattern["join_cost"]


    # 🏆 выбор победителя
    winner = weighted_random(weighted)


    payout = int(total_pool * 0.9)
    casino_cut = total_pool - payout


    # 💰 распределение
    if winner["is_bot"]:
        fetch("""
            UPDATE casino_balance
            SET balance = balance + %s
            WHERE id = 1
        """, (payout,))
    else:
        fetch("""
            UPDATE users
            SET balance = balance + %s
            WHERE id = %s
        """, (payout, winner["user_id"]))


    # казино комиссия
    fetch("""
        UPDATE casino_balance
        SET balance = balance + %s
        WHERE id = 1
    """, (casino_cut,))


    # 🏁 финал
    fetch("""
        UPDATE rooms
        SET status = 'finished',
            winner_id = %s,
            ended_at = NOW()
        WHERE id = %s
    """, (winner["user_id"], room_id))


# =========================================================
# 🎲 WEIGHTED RANDOM
# =========================================================
def weighted_random(items):
    """
    items = [(user_id, weight, is_bot), ...]
    """

    pool = []

    for user_id, weight, is_bot in items:
        for _ in range(weight):
            pool.append({
                "user_id": user_id,
                "is_bot": is_bot
            })

    return random.choice(pool)
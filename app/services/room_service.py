# from app.db.db import fetch
# from datetime import datetime
# import random
#
#
# # =========================================================
# # 🧩 CREATE ROOM
# # =========================================================
# def create_room(pattern_id: int):
#     room = fetch("""
#         INSERT INTO rooms (room_pattern_id, websocket_access_token)
#         VALUES (%s, gen_random_uuid()::text)
#         RETURNING *
#     """, (pattern_id,))
#
#     return room
#
#
# # =========================================================
# # 👤 ADD USER SLOTS
# # =========================================================
# def add_user(room_id: int, user_id: int, slots_count: int, boost: int = 0):
#     """
#     пользователь занимает N слотов в комнате
#     """
#
#     room = fetch("""
#         SELECT * FROM rooms
#         WHERE id = %s
#         FOR UPDATE
#     """, (room_id,))
#
#     if not room:
#         raise Exception("Room not found")
#
#     if room["status"] not in ("waiting", "lobby"):
#         raise Exception("Room is not joinable")
#
#
#     pattern = fetch("""
#         SELECT * FROM room_pattern
#         WHERE id = %s
#     """, (room["room_pattern_id"],))
#
#
#     # текущие слоты
#     current_slots = fetch("""
#         SELECT COUNT(*) as count
#         FROM room_members
#         WHERE room_id = %s
#     """, (room_id,))["count"]
#
#     if current_slots + slots_count > pattern["max_members_count"]:
#         raise Exception("Not enough free slots")
#
#
#     # 💰 списание с пользователя
#     total_cost = slots_count * pattern["join_cost"]
#
#     updated = fetch("""
#         UPDATE users
#         SET balance = balance - %s
#         WHERE id = %s AND balance >= %s
#         RETURNING id
#     """, (total_cost, user_id, total_cost))
#
#     if not updated:
#         raise Exception("Not enough balance")
#
#
#     # ➕ добавляем слоты
#     for _ in range(slots_count):
#         fetch("""
#             INSERT INTO room_members (room_id, user_id, boost)
#             VALUES (%s, %s, %s)
#         """, (room_id, user_id, boost))
#
#
#     # 🟡 первый игрок → перевод в lobby
#     if room["status"] == "waiting":
#         fetch("""
#             UPDATE rooms
#             SET status = 'lobby'
#             WHERE id = %s
#         """, (room_id,))
#
#
#         # сигнал scheduler-у
#         return {
#             "first_player": True,
#             "spawn_bots_delay": pattern["waiting_lobby_stage"]
#         }
#
#     return {"first_player": False}
#
#
# # =========================================================
# # 🤖 ADD BOT SLOTS
# # =========================================================
# def add_bot_slots(room_id: int, bot_id: int, slots_count: int):
#     """
#     бот занимает N слотов (оплата из казино)
#     """
#
#     room = fetch("""
#         SELECT * FROM rooms
#         WHERE id = %s
#         FOR UPDATE
#     """, (room_id,))
#
#     if room["status"] != "lobby":
#         return
#
#
#     pattern = fetch("""
#         SELECT * FROM room_pattern
#         WHERE id = %s
#     """, (room["room_pattern_id"],))
#
#
#     total_cost = slots_count * pattern["join_cost"]
#
#     casino = fetch("""
#         SELECT * FROM casino_balance
#         WHERE id = 1
#     """)
#
#     if casino["balance"] < total_cost:
#         return
#
#
#     # 💸 списываем казино
#     fetch("""
#         UPDATE casino_balance
#         SET balance = balance - %s
#         WHERE id = 1
#     """, (total_cost,))
#
#
#     # ➕ добавляем слоты
#     for _ in range(slots_count):
#         fetch("""
#             INSERT INTO room_members (room_id, user_id, boost)
#             VALUES (%s, %s, 0)
#         """, (room_id, bot_id))
#
#
# # =========================================================
# # 🔍 GET MEMBERS
# # =========================================================
# def get_room_members(room_id: int):
#     return fetch("""
#         SELECT rm.user_id, rm.boost, u.is_bot
#         FROM room_members rm
#         JOIN users u ON u.id = rm.user_id
#         WHERE rm.room_id = %s
#     """, (room_id,))
#
#
# # =========================================================
# # ✅ CAN START
# # =========================================================
# def can_start(room_id: int) -> bool:
#     room = fetch("SELECT * FROM rooms WHERE id = %s", (room_id,))
#     pattern = fetch("""
#         SELECT * FROM room_pattern
#         WHERE id = %s
#     """, (room["room_pattern_id"],))
#
#     count = fetch("""
#         SELECT COUNT(*) as count
#         FROM room_members
#         WHERE room_id = %s
#     """, (room_id,))["count"]
#
#     return count >= pattern["min_bots_count"]
#
#
# # =========================================================
# # 🎮 RUN GAME
# # =========================================================
# def run_game(room_id: int):
#     """
#     основной запуск игры
#     """
#
#     room = fetch("""
#         SELECT * FROM rooms
#         WHERE id = %s
#         FOR UPDATE
#     """, (room_id,))
#
#     if room["status"] != "lobby":
#         return
#
#     # 🚀 перевод в running
#     fetch("""
#         UPDATE rooms
#         SET status = 'running',
#             started_at = NOW()
#         WHERE id = %s
#     """, (room_id,))
#
#     pattern = fetch("""
#         SELECT * FROM room_pattern
#         WHERE id = %s
#     """, (room["room_pattern_id"],))
#
#
#     members = get_room_members(room_id)
#
#     # 🎯 веса
#     weighted = []
#     total_pool = 0
#
#     for m in members:
#         weight = 1 + m["boost"]
#         weighted.append((m["user_id"], weight, m["is_bot"]))
#         total_pool += pattern["join_cost"]
#
#     # 🏆 выбор победителя
#     winner = weighted_random(weighted)
#
#
#     payout = int(total_pool * 0.9)
#     casino_cut = total_pool - payout
#
#     # 💰 распределение
#     if winner["is_bot"]:
#         fetch("""
#             UPDATE casino_balance
#             SET balance = balance + %s
#             WHERE id = 1
#         """, (payout,))
#     else:
#         fetch("""
#             UPDATE users
#             SET balance = balance + %s
#             WHERE id = %s
#         """, (payout, winner["user_id"]))
#
#
#     # казино комиссия
#     fetch("""
#         UPDATE casino_balance
#         SET balance = balance + %s
#         WHERE id = 1
#     """, (casino_cut,))
#
#
#     # 🏁 финал
#     fetch("""
#         UPDATE rooms
#         SET status = 'finished',
#             winner_id = %s,
#             ended_at = NOW()
#         WHERE id = %s
#     """, (winner["user_id"], room_id))
#
#
# # =========================================================
# # 🎲 WEIGHTED RANDOM
# # =========================================================
# def weighted_random(items):
#     """
#     items = [(user_id, weight, is_bot), ...]
#     """
#
#     pool = []
#
#     for user_id, weight, is_bot in items:
#         for _ in range(weight):
#             pool.append({
#                 "user_id": user_id,
#                 "is_bot": is_bot
#             })
#
#     return random.choice(pool)
#
#
#
#
# # Оценщик шанса

import secrets
import random
from typing import List, Dict, Any, Optional


from app.db.db import fetch_one, fetch_all, execute_with_returning


# =========================================================
# 🔧 AUXILIARY FUNCTIONS
# =========================================================

def generate_websocket_token() -> str:
    """Генерирует длинную случайную строку для токена комнаты."""
    return secrets.token_urlsafe(48)


def get_room_by_id(room_id: int):
    return fetch_one("""
        SELECT * 
        FROM room
        WHETE id = %s
    """, (room_id,))


def get_room_by_token(token: str) -> Optional[Dict]:
    """Возвращает id, status, game, cost комнаты по токену."""
    return fetch_one("""
        SELECT r.*, rp.game, rp.join_cost, rp.max_members_count, rp.rank
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.access_token = %s
    """, (token,))


def get_all_rooms(limit=100):
    return fetch_all("""
        SELECT r.*, rp.game, rp.join_cost
        (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) as members_count
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.status IN ('waiting', 'lobby', 'shop', 'running')
        ORDER BY r.created_at DESC
        LIMIT %s
    """, (limit,))


def get_room_by_pattern(pattern_id: int) -> Optional[Dict]:
    """
    Возвращает комнату со статусом 'lobby', имеющую хотя бы 1 свободный слот.
    """
    rooms = fetch_all("""
        SELECT r.*, rp.game, rp.join_cost, rp.max_members_count
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.room_pattern_id = %s
        AND r.status = 'lobby'
        ORDER BY r.created_at ASC
    """, (pattern_id,))

    for room in rooms:
        occupied = fetch_one("""
            SELECT COUNT(*) as cnt
            FROM room_members
            WHERE room_id = %s
        """, (room['id'],))['cnt']

        if room['max_members_count'] - occupied >= 1:
            return room
    return None


# =========================================================
# 🔍 GET MEMBERS
# =========================================================

def get_room_members(room_id: int):
     return fetch_all("""
         SELECT rm.user_id, rm.boost, u.is_bot
         FROM room_members rm
         JOIN users u ON u.id = rm.user_id
         WHERE rm.room_id = %s
    """, (room_id,))


def get_user_slots_in_room(room_id: int, user_id: int) -> List[Dict]:
    """Возвращает все слоты пользователя в комнате с их бустами."""
    return fetch_all("""
        SELECT id, boost
        FROM room_members
        WHERE room_id = %s AND user_id = %s
    """, (room_id, user_id))

# =========================================================
# ➕ CREATE ROOM
# =========================================================

def create_room(pattern_id: int) -> Dict:
    """Создаёт новую комнату со статусом 'waiting' и уникальным токеном."""
    token = generate_websocket_token()
    room = execute_with_returning("""
        INSERT INTO rooms (room_pattern_id, websocket_access_token, status)
        VALUES (%s, %s, 'waiting')
        RETURNING *
    """, (pattern_id, token))
    return room


def join_room(room_id: int, user_id: int) -> Dict:
    """
    Добавляет пользователя в комнату, занимает 1 слот, boost = 0.
    Возвращает: success, first_player, delay_seconds (если первый), room_id.
    """
    room = fetch_one("""
        SELECT * 
        FROM rooms 
        WHERE id = %s FOR UPDATE
    """, (room_id,))

    if not room:
        return {"success": False, "message": "Room not found"}

    if room['status'] != 'lobby':
        return {"success": False, "message": "Room is not joinable now"}

    pattern = fetch_one("""
        SELECT * 
        FROM room_pattern 
        WHERE id = %s
    """, (room['room_pattern_id'],))

    if not pattern:
        return {"success": False, "message": "Pattern not found"}

    current_slots = fetch_one("""
        SELECT COUNT(*) as cnt 
        FROM room_members 
        WHERE room_id = %s
    """, (room_id,))['cnt']

    if current_slots + 1 > pattern['max_members_count']:
        return {"success": False, "message": "No free slots"}

    user = fetch_one("""
        SELECT is_bot 
        FROM users 
        WHERE id = %s
    """, (user_id,))

    if not user or user['is_bot']:
        return {"success": False, "message": "Invalid user"}

    total_cost = pattern['join_cost']
    updated = fetch_one("""
        UPDATE users 
        SET balance = balance - %s
        WHERE id = %s AND balance >= %s
        RETURNING id
    """, (total_cost, user_id, total_cost))

    if not updated:
        return {"success": False, "message": "Not enough balance"}

    fetch_one("""
        INSERT INTO room_members (room_id, user_id, boost)
        VALUES (%s, %s, 0)
    """, (room_id, user_id))

    is_first = (current_slots == 0)

    return {
        "success": True,
        "first_player": is_first,
        "delay_seconds": pattern['waiting_lobby_stage'] if is_first else 0,
        "room_id": room_id
    }
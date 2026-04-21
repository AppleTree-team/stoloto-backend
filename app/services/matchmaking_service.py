#
#
# def find_available_room(game, cost, slots_count):
#
#     return None
#
#
# def can_create_room(pattern_id):
#
#     active_rooms = count rooms WHERE status IN (waiting, lobby, running)
#
#     if active_rooms >= system_config.max_active_rooms:
#         return False
#
#     pattern_rooms = count rooms WHERE pattern_id
#
#     if pattern_rooms >= pattern.max_rooms_count:
#         return False
#
#     return True
#
#
#
#
# def join_game(user_id, game, cost, slots_count, boost_per_slot):
#
#     # 1. найти подходящую комнату
#     room = find_available_room(game, cost, slots_count)
#
#     if room:
#         room_service.add_user_slots(
#             room_id=room.id,
#             user_id=user_id,
#             slots_count=slots_count,
#             boost=boost_per_slot
#         )
#         return room
#
#     # 2. не нашли — ищем паттерн
#     pattern = find_pattern(game, cost)
#
#     if not pattern:
#         return suggest_alternative_rooms(game)
#
#     # 3. можно ли создать комнату?
#     if not can_create_room(pattern.id):
#         return suggest_alternative_rooms(game)
#
#     # 4. создаём комнату
#     room = room_service.create_room(pattern.id)
#
#     room_service.add_user_slots(
#         room_id=room.id,
#         user_id=user_id,
#         slots_count=slots_count,
#         boost=boost_per_slot
#     )
#
#     return room
#
#
#
#
#
#
#
#

from app.services.pattern_service import get_pattern_by_game_and_cost
from app.services.room_service import get_room_by_pattern, create_room

def find_room_for_user(game: str, min_cost: int, max_cost: int) -> dict:
    pattern = get_pattern_by_game_and_cost(game, min_cost, max_cost)
    if not pattern:
        return {"success": False, "message": "No active pattern found for this game and cost"}

    room = get_room_by_pattern(pattern["id"])
    if not room:
        room = create_room(pattern["id"])

    return {"success": True, "room": room}
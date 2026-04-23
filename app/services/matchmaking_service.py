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
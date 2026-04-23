from app.services.pattern_service import get_pattern_by_game_and_cost
from app.services.room_service import get_room_by_pattern, create_room

def find_room_for_user(game: str, min_cost: int, max_cost: int) -> dict:
    pattern = get_pattern_by_game_and_cost(game, min_cost, max_cost)
    if not pattern:
        return {"success": False, "message": "No active pattern found for this game and cost"}

    room = get_room_by_pattern(pattern["id"])
    if not room:
        created = create_room(pattern["id"])
        if not created.get("success"):
            return {"success": False, "message": created.get("message", "Room not created")}
        room = created.get("room")
        if not room:
            return {"success": False, "message": "Room not created"}

    return {"success": True, "room": room}

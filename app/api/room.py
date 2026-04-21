from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_profile, require_session_payload
from app.services.matchmaking_service import find_room_for_user
from app.services.room_service import get_room_by_token, get_room_members, get_user_slots_in_room
#from app.services.room_service import find_room_for_user, get_room_by_token

router = APIRouter(prefix="/room", tags=["Room"])

class SearchRequest(BaseModel):
    game: str
    min_cost: int
    max_cost: int

@router.post("/search")
def search_room(
    data: SearchRequest,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Найти (или создать) комнату для пользователя.

    Возвращает:
        - 200: {
            "room_access_token": "<token>"
          }
        - 400: Не удалось найти или создать комнату
        - 401: Неавторизован
    """

    result = find_room_for_user(data.game, data.min_cost, data.max_cost)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    room = result["room"]

    return {
        "room_access_token": room["websocket_access_token"]
    }

@router.get("/{room_access_token}")
def get_room(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Получить информацию о комнате по access_token.

    Возвращает:
        - 200: {
            "id": <room_id>,
            "status": "<status>",
            "players": [...],
            "game": "<game>",
            "cost": <cost>
          }
        - 404: Комната не найдена
    """

    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    players = get_room_members(room["id"])

    return {
        "id": room["id"],
        "status": room["status"],
        "players": players,
        "game": room["game"],
        "join_cost": room["join_cost"]
    }


@router.get("/lobby/{room_access_token}")
def get_lobby(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Lobby is not available now")

    players = get_room_members(room["id"])
    current_players = len(players)
    total_pool = room["join_cost"] * current_players
    casino_cut = int(total_pool * room["rank"])
    prize_pool = total_pool - casino_cut

    return {
        "id": room["id"],
        "game": room["game"],
        "max_members_count": room["max_members_count"],
        "prize_pool": prize_pool
    }


@router.get("/shop/{room_access_token}")
def get_shop(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room["status"] != "shop":
        raise HTTPException(status_code=400, detail="Shop is not available now")

    players = get_room_members(room["id"])
    current_players = len(players)
    total_pool = room["join_cost"] * current_players
    casino_cut = int(total_pool * room["rank"])
    prize_pool = total_pool - casino_cut

    return {
        "id": room["id"],
        "game": room["game"],
        "join_cost": room["join_cost"],
        "max_members_count": room["max_members_count"],
        "prize_pool": prize_pool,
    }

@router.post("/shop/boosts/{room_access_token}")
def buy_boosts(

    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    return {

    }


@router.post("/shop/slots/{room_access_token}")
def buy_slots(
        slots_count: int,
        room_access_token: str,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):

    return {

    }
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_profile, require_session_payload
from app.services.matchmaking_service import find_room_for_user
from app.services.room_service import get_room_by_token, get_room_members

from app.models.room import SearchRequest

from typing import Optional


router = APIRouter(prefix="/room", tags=["Room"])
shop_router = APIRouter(prefix="", tags=["Shop"])





@router.post("/search")
def search_room(
    data: SearchRequest,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Найти (или создать не активированную комнату) комнату для пользователя.

    Возвращает:
        - 200: {
            "room_access_token": "<token>"
          }
        - 400: Не удалось найти или создать комнату
        - 401: Неавторизован
    """

    # здесь нужно праивильную функицю из matchmaking_service
    #room = find_room_for_user(user_id=profile["id"])

    #if not room:
    #    raise HTTPException(status_code=400, detail="Room not available")

    #return {
    #    "room_access_token": room["access_token"]
    #}
    result = find_room_for_user(data.game, data.min_cost, data.max_cost)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return {
        "room": result["room"]
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


@router.get("/{room_access_token}/lobby")
def get_lobby(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
        SSE Стрим ожидания начала стадии закупок
    """
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



@shop_router.get("/")
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




@shop_router.post("/buy/boost")
def shop_buy_boost_on_slot(
    room_access_token: str,
    slot_id: Optional[int] = None,
    _payload: dict = Depends(require_session_payload),
):
    """
        Купить буст для выбранного слота.
        Проверяем в какой стадии находится комната,
            если это стадия shop, и оцениваем там же нас на победу в функции pgsql
    """

    room = get_room_by_token(room_access_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    players = get_room_members(room["id"])

    print(players)



@shop_router.post("/buy/slot")
def shop_buy_slot(
    room_access_token: str,
    slot_id: Optional[int] = None,
    _payload: dict = Depends(require_session_payload),
):
    """
    Купить слот для выбранного слота.
    """

    room = get_room_by_token(room_access_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    players = get_room_members(room["id"])

    print(players)



@router.get("/{room_access_token}/victory_chance")
def room_victory_chance(
    room_access_token: str,
    _payload: dict = Depends(require_session_payload),
):
    """
    Возвращает все слоты и их шансы с параметром буста.
    """
    pass






router.include_router(shop_router, prefix="/{room_access_token}/shop")
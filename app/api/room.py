from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from typing import Optional
from app.api.deps import get_current_user_profile, require_session_payload
from app.services.matchmaking_service import find_room_for_user
from app.services.room_service import get_room_by_token, get_room_members
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






"""
    SHOP
"""



shop_router = APIRouter(prefix="/shop", tags=["Shop"])
router.include_router(shop_router, tags=["Shop"])




@shop_router.post("/{room_access_token}/buy/slot")
def shop_buy_slot(
    room_access_token: str,
    _payload: dict = Depends(require_session_payload),
):
    """
    Купить слот для текущей комнаты.
    Проверяем в какой стадии находится комната,
        если это стадия shop, и оцениваем там же нас на победу в функции pgsql

    """

    room = get_room_by_token(room_access_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    players = get_room_members(room["id"])

    #if players[''] < len(room['players']):

    return {
        "id": room["id"],
        "status": room["status"],
        "players": players,
        "game": room["game"],
        "join_cost": room["join_cost"]
    }



@shop_router.post("/{room_access_token}/buy/bust")
def shop_buy_bust_on_slot(
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



@shop_router.get("/{room_access_token}/victory_chance")
def shop_victory_chance(
    room_access_token: str,
    _payload: dict = Depends(require_session_payload),
):
    """
    Возвращает все слоты и их шансы с параметром буста.
    """
    pass


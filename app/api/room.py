import asyncio
import json
import time

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_profile, require_session_payload
from app.services.matchmaking_service import find_room_for_user
from app.services.room_service import (
    get_room_by_token,
    get_room_members,
    start_lobby_if_waiting,
    ensure_user_added_to_room_once,
    set_lobby_timer_if_missing,
    get_room_members_count,
    get_lobby_seconds_left,
    finish_lobby_to_shop_if_lobby,
)

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
async def get_lobby(
    room_access_token: str,
    request: Request,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
        SSE Стрим ожидания начала стадии закупок
    """
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room["status"] == "waiting":
        start_lobby_if_waiting(room["id"], room.get("waiting_lobby_stage", 0))
        room = get_room_by_token(room_access_token)

    if room["status"] == "lobby" and not room.get("started_at"):
        set_lobby_timer_if_missing(room["id"], room.get("waiting_lobby_stage", 0))
        room = get_room_by_token(room_access_token)

    if room["status"] not in ("lobby", "shop"):
        raise HTTPException(status_code=400, detail="Lobby is not available now")

    if room["status"] == "lobby":
        ensure_user_added_to_room_once(room["id"], profile["id"])

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    async def event_generator():
        last_tick_sent = 0.0
        while True:
            if await request.is_disconnected():
                break

            current_room = get_room_by_token(room_access_token)
            if not current_room:
                yield sse("error", {"detail": "Room not found"})
                break

            if current_room["status"] != "lobby":
                yield sse("lobby_end", {"status": current_room["status"], "room_id": current_room["id"]})
                break

            members_count = get_room_members_count(current_room["id"])
            max_members_count = int(current_room.get("max_members_count") or 0)
            threshold = max(2, (max_members_count + 1) // 2)

            seconds_left = get_lobby_seconds_left(current_room["id"])

            should_end_by_members = members_count >= threshold
            should_end_by_timer = seconds_left == 0

            if should_end_by_members or should_end_by_timer:
                finish_lobby_to_shop_if_lobby(current_room["id"])
                updated_room = get_room_by_token(room_access_token)
                reason = "members" if should_end_by_members else "timer"
                yield sse("lobby_end", {
                    "status": updated_room["status"] if updated_room else "shop",
                    "room_id": current_room["id"],
                    "members_count": members_count,
                    "threshold": threshold,
                    "max_members_count": max_members_count,
                    "seconds_left": seconds_left,
                    "reason": reason,
                })
                break

            now_mono = time.monotonic()
            if now_mono - last_tick_sent >= 10:
                total_pool = current_room["join_cost"] * members_count
                casino_cut = int(total_pool * current_room["rank"])
                prize_pool = total_pool - casino_cut

                yield sse("tick", {
                    "room_id": current_room["id"],
                    "status": current_room["status"],
                    "members_count": members_count,
                    "threshold": threshold,
                    "max_members_count": max_members_count,
                    "seconds_left": seconds_left,
                    "prize_pool": prize_pool,
                })
                last_tick_sent = now_mono

            await asyncio.sleep(1)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)



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

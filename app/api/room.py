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
    get_room_total_weight,
    get_room_victory_chance,
    get_room_escrow_snapshot,
    start_game_if_shop,
    finish_game_and_pick_winner_if_running,
    shop_buy_slot as shop_buy_slot_service,
    shop_buy_boost as shop_buy_boost_service,
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
    chance = get_room_victory_chance(room["id"], profile["id"])

    return {
        "id": room["id"],
        "status": room["status"],
        "players": players,
        "game": room["game"],
        "join_cost": room["join_cost"],
        "max_members_count": room.get("max_members_count"),
        "members_count": chance.get("members_count") if chance.get("success") else None,
        "free_slots": chance.get("free_slots") if chance.get("success") else None,
        # "шанс от общего кол-ва мест" (max_members_count), а не только от текущих участников
        "victory_chance_percent": chance.get("chance_capacity_percent") if chance.get("success") else None,
        "victory_chance_current_percent": chance.get("chance_current_percent") if chance.get("success") else None,
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
        join_result = ensure_user_added_to_room_once(room["id"], profile["id"])
        if not join_result.get("success"):
            raise HTTPException(status_code=400, detail=join_result.get("message", "Join failed"))

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
                finish_lobby_to_shop_if_lobby(current_room["id"], current_room.get("waiting_shop_stage", 0))
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
                # В лобби показываем потенциальный приз при полном заполнении комнаты
                total_pool = current_room["join_cost"] * max_members_count
                casino_cut = int(total_pool * (float(current_room["rank"]) / 100.0))
                prize_pool = total_pool - casino_cut
                chance = get_room_victory_chance(current_room["id"], profile["id"])

                yield sse("tick", {
                    "room_id": current_room["id"],
                    "status": current_room["status"],
                    "members_count": members_count,
                    "threshold": threshold,
                    "max_members_count": max_members_count,
                    "seconds_left": seconds_left,
                    "victory_chance_percent": chance.get("chance_capacity_percent") if chance.get("success") else None,
                    "victory_chance_current_percent": chance.get("chance_current_percent") if chance.get("success") else None,
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
async def get_shop(
    room_access_token: str,
    request: Request,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room["status"] not in ("shop", "running", "finished"):
        raise HTTPException(status_code=400, detail="Shop is not available now")

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    async def event_generator():
        last_tick_sent = 0.0
        last_free_slots = None
        last_members_count = None
        last_total_weight = None

        while True:
            if await request.is_disconnected():
                break

            current_room = get_room_by_token(room_access_token)
            if not current_room:
                yield sse("error", {"detail": "Room not found"})
                break

            if current_room["status"] == "finished":
                yield sse("game_result", {
                    "room_id": current_room["id"],
                    "status": current_room["status"],
                    "winner_id": current_room.get("winner_id"),
                    "ended_at": current_room.get("ended_at"),
                })
                break

            if current_room["status"] == "running":
                result = finish_game_and_pick_winner_if_running(current_room["id"])
                updated = get_room_by_token(room_access_token)
                yield sse("game_result", {
                    "room_id": current_room["id"],
                    "status": updated["status"] if updated else "finished",
                    "winner_id": (result or {}).get("winner_id") or (updated or {}).get("winner_id"),
                    "ended_at": (result or {}).get("ended_at") or (updated or {}).get("ended_at"),
                })
                break

            if current_room["status"] != "shop":
                yield sse("shop_end", {"status": current_room["status"], "room_id": current_room["id"]})
                break

            room_id = current_room["id"]
            seconds_left = get_lobby_seconds_left(room_id)
            members_count = get_room_members_count(room_id)
            total_weight = get_room_total_weight(room_id)

            max_members_count = int(current_room.get("max_members_count") or 0)
            free_slots = max(0, max_members_count - members_count)

            if (
                last_free_slots is None
                or free_slots != last_free_slots
                or members_count != last_members_count
                or total_weight != last_total_weight
            ):
                yield sse("slots_update", {
                    "room_id": room_id,
                    "free_slots": free_slots,
                    "members_count": members_count,
                    "max_members_count": max_members_count,
                    "total_weight": total_weight,
                })
                last_free_slots = free_slots
                last_members_count = members_count
                last_total_weight = total_weight

            if seconds_left == 0:
                start_result = start_game_if_shop(room_id)
                updated_after_start = get_room_by_token(room_access_token)
                started = bool(start_result.get("started")) or bool(updated_after_start and updated_after_start.get("status") == "running")

                if not started:
                    yield sse("error", {
                        "detail": "Failed to start room from shop",
                        "room_id": room_id,
                        "start_result": start_result,
                    })
                    break

                yield sse("game_start", {
                    "room_id": room_id,
                    "status": "running",
                    "bots_added": start_result.get("bots_added", 0),
                    "free_slots_before": start_result.get("free_slots"),
                    "fill_slots": start_result.get("fill_slots"),
                })

                result = finish_game_and_pick_winner_if_running(room_id)
                updated = get_room_by_token(room_access_token)
                yield sse("game_result", {
                    "room_id": room_id,
                    "status": updated["status"] if updated else "finished",
                    "winner_id": (result or {}).get("winner_id") or (updated or {}).get("winner_id"),
                    "ended_at": (result or {}).get("ended_at") or (updated or {}).get("ended_at"),
                })
                break

            now_mono = time.monotonic()
            if now_mono - last_tick_sent >= 10:
                escrow = get_room_escrow_snapshot(room_id)
                stake_fund = int(escrow.get("stake_amount") or 0)
                boost_fund = int(escrow.get("boost_amount") or 0)
                casino_cut = int(stake_fund * (float(current_room["rank"]) / 100.0))
                prize_pool = max(0, stake_fund - casino_cut) + boost_fund
                chance = get_room_victory_chance(room_id, profile["id"])

                yield sse("tick", {
                    "room_id": room_id,
                    "status": current_room["status"],
                    "seconds_left": seconds_left,
                    "free_slots": free_slots,
                    "members_count": members_count,
                    "max_members_count": max_members_count,
                    "total_weight": total_weight,
                    "victory_chance_percent": chance.get("chance_capacity_percent") if chance.get("success") else None,
                    "victory_chance_current_percent": chance.get("chance_current_percent") if chance.get("success") else None,
                    "stake_fund": stake_fund,
                    "boost_fund": boost_fund,
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




@shop_router.post("/buy/boost")
def shop_buy_boost_on_slot(
    room_access_token: str,
    slot_id: Optional[int] = None,
    boost: int = 5,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
        Купить буст для выбранного слота.
        Проверяем в какой стадии находится комната,
            если это стадия shop, и оцениваем там же нас на победу в функции pgsql
    """

    if not slot_id:
        raise HTTPException(status_code=400, detail="slot_id is required")

    if boost <= 0:
        raise HTTPException(status_code=400, detail="boost must be > 0")

    room = get_room_by_token(room_access_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    result = shop_buy_boost_service(room["id"], profile["id"], int(slot_id), int(boost))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Boost purchase failed"))

    return {
        "status": "success",
        "slot_id": slot_id,
        "user_weight_after": result.get("user_weight_after"),
        "total_weight_after": result.get("total_weight_after"),
    }



@shop_router.post("/buy/slot")
def shop_buy_slot(
    room_access_token: str,
    slot_id: Optional[int] = None,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Купить слот для выбранного слота.
    """

    room = get_room_by_token(room_access_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    result = shop_buy_slot_service(room["id"], profile["id"])
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Slot purchase failed"))

    return {
        "status": "success",
        "slot_id": result.get("slot_id"),
        "free_slots": result.get("free_slots_after"),
        "members_count": result.get("members_count_after"),
    }



@router.get("/{room_access_token}/victory_chance")
def room_victory_chance(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    """
    Возвращает все слоты и их шансы с параметром буста.
    """
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    result = get_room_victory_chance(room["id"], profile["id"])
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "Room not found"))

    return {"room_id": room["id"], **result}






router.include_router(shop_router, prefix="/{room_access_token}/shop")

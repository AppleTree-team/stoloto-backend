from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_profile, require_session_payload
from app.services.matchmaking_service import find_room_for_user
from app.services.room_service import get_room_by_token, get_room_members
#from app.services.room_service import find_room_for_user, get_room_by_token

from fastapi import Request
from fastapi.responses import StreamingResponse
import json

import asyncio


rooms_queues = {}  # room_id -> [Queue]
room_timers = {}   # room_id -> seconds
room_tasks = {}    # room_id -> asyncio.Task




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






@router.get("/lobby/{room_access_token}")
def get_lobby(
    room_access_token: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    players = get_room_members(room["id"])

    return {
        "room_id": room["id"],
        "players": players,
        "status": room["status"]
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

    # тут можешь потом заменить на реальную логику
    return {
        "room_id": room["id"],
        "items": [
            {"id": 1, "name": "Sword", "price": 100},
            {"id": 2, "name": "Shield", "price": 150},
        ]
    }





async def room_timer_task(room_id: str, duration: int = 60):
    room_timers[room_id] = duration

    while room_timers[room_id] > 0:
        await asyncio.sleep(10)
        room_timers[room_id] -= 10

        await broadcast(room_id, {
            "type": "timer",
            "seconds_left": room_timers[room_id]
        })

    # финальное событие
    await broadcast(room_id, {
        "type": "start_game"
    })

    # очистка
    del room_timers[room_id]
    del room_tasks[room_id]


async def broadcast(room_id: str, message: dict):
    if room_id not in rooms_queues:
        return

    for q in rooms_queues[room_id]:
        await q.put(message)



@router.get("/events/{room_access_token}")
async def room_events(request: Request, room_access_token: str):
    room = get_room_by_token(room_access_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    #room_id = str(room["id"])
    room_id = room["id"]

    queue = asyncio.Queue()

    if room_id not in rooms_queues:
        rooms_queues[room_id] = []

    rooms_queues[room_id].append(queue)

    lock = asyncio.Lock()
        # 🔥 ВАЖНО: старт таймера только если его ещё нет
    async with lock:
        if room_id not in room_tasks:
            room_tasks[room_id] = asyncio.create_task(
                room_timer_task(room_id, duration=60)
            )

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield f"data: {json.dumps(data)}\n\n"

        finally:
            rooms_queues[room_id].remove(queue)

            if not rooms_queues[room_id]:
                del rooms_queues[room_id]

                # 💥 останавливаем таймер если никого нет
                if room_id in room_tasks:
                    room_tasks[room_id].cancel()
                    del room_tasks[room_id]

                if room_id in room_timers:
                    del room_timers[room_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )



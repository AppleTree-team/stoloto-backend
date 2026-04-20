from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.api.deps import get_current_user_profile
from app.services.room_scheduler import list_available_rooms, join_room_by_id

router = APIRouter(prefix="/rooms", tags=["Rooms"])


class RoomInfo(BaseModel):
    id: int
    status: str
    created_at: str  # или datetime, но проще строкой
    current_players: int
    max_players: int


class RoomsListResponse(BaseModel):
    rooms: List[RoomInfo]



@router.get("", response_model=RoomsListResponse)
def get_rooms(
    game: str,
    join_cost: int,
    profile: dict = Depends(get_current_user_profile)
):
    """
    Возвращает список комнат, доступных для входа, по игре и стоимости входа.
    """
    rooms = list_available_rooms(game, join_cost)
    return {"rooms": rooms}


class JoinRoomResponse(BaseModel):
    room_id: int
    websocket_access_token: Optional[str] = None  # если нужно фронту


@router.post("/{room_id}/join", response_model=JoinRoomResponse)
def join_room(
    room_id: int,
    profile: dict = Depends(get_current_user_profile)
):
    """
    Присоединяет текущего пользователя к указанной комнате.
    """
    user_id = profile["user"]["id"]
    try:
        # join_room_by_id возвращает room_id, но можно и токен добавить
        room_id = join_room_by_id(user_id, room_id)
        # Получаем токен комнаты для вебсокета (если нужно)
        from app.services.room_service import get_room
        room = get_room(room_id)
        return {
            "room_id": room_id,
            "websocket_access_token": room["websocket_access_token"] if room else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
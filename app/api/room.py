from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_profile, require_session_payload
#from app.services.room_service import find_room_for_user, get_room_by_token

router = APIRouter(prefix="/room", tags=["Room"])


@router.post("/search")
def search_room(
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

    #room = find_room_for_user(user_id=profile["id"])

    #if not room:
    #    raise HTTPException(status_code=400, detail="Room not available")

    #return {
    #    "room_access_token": room["access_token"]
    #}


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

    # room = get_room_by_token(room_access_token)
    #
    # if not room:
    #     raise HTTPException(status_code=404, detail="Room not found")
    #
    # return room
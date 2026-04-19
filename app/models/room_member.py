from pydantic import BaseModel
from datetime import datetime


class RoomMember(BaseModel):
    id: int

    room_id: int
    user_id: int

    joined_at: datetime
    boost: int = 0
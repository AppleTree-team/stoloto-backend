
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.room_status import RoomStatus
class Room(BaseModel):
    id: int
    game_pattern_id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: RoomStatus = RoomStatus.waiting
    winner_id: Optional[int] = None
    access_token: str


#room search
class SearchRequest(BaseModel):
    game: str
    min_cost: int
    max_cost: int

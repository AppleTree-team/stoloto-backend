from pydantic import BaseModel
from typing import Optional

class Room(BaseModel):
    id: int
    game_pattern_id: int
    created_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: str = "waiting"
    winner_id: Optional[int] = None
    websocket_access_token: str
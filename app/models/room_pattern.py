from pydantic import BaseModel
from app.models.game_type import GameType

class RoomPattern(BaseModel):
    id: int
    game: GameType
    join_cost: int
    max_members_count: int = 10
    rank: float
    waiting_lobby_stage: int = 60
    waiting_shop_stage: int = 30

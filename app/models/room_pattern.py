from pydantic import BaseModel

class RoomPattern(BaseModel):
    id: int
    game: str
    join_cost: int
    max_members_count: int = 10
    rank: float
    min_bots_count: int = 1
    max_bots_count: int = 9
    waiting_lobby_stage: int = 60
    waiting_shop_stage: int = 30
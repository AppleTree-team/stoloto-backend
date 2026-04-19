from pydantic import BaseModel
from datetime import datetime

class User(BaseModel):
    id: int
    username: str
    balance: int = 0
    created_at: datetime
    is_bot: bool = False

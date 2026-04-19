from pydantic import BaseModel
from typing import Optional


class User(BaseModel):
    id: int
    username: str
    balance: int
    created_at: str
    is_bot: bool
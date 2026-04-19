from pydantic import BaseModel

class User(BaseModel):
    id: int
    username: str
    balance: int
    created_at: str
    is_bot: bool
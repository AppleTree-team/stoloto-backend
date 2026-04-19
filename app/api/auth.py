from fastapi import APIRouter
from pydantic import BaseModel

from app.services.auth_service import check_user, create_fake_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(data: LoginRequest):
    if not check_user(data.username, data.password):
        return {
            "status": "error",
            "message": "invalid credentials"
        }

    token = create_fake_token(data.username)

    return {
        "status": "ok",
        "message": f"welcome {data.username}",
        "token": token
    }
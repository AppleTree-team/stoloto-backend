from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.services.auth_service import login

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login_endpoint(data: LoginRequest, response: Response):
    result = login(data.username, data.password)

    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response.set_cookie(
        key="session_id",
        value=result["token"],
        httponly=True
    )

    return {
        "message": "Login successful",
        "user_id": result["user_id"],
        "username": result["username"]
    }
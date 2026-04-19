from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.auth_service import decode_session_token, get_user_by_id

router = APIRouter()


@router.get("/home")
def home(request: Request):
    token = request.cookies.get("session_id")

    if not token:
        return JSONResponse(status_code=401, content={"detail": "No session"})

    payload = decode_session_token(token)

    if not payload:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    user = get_user_by_id(payload["user_id"])

    if not user:
        return JSONResponse(status_code=401, content={"detail": "User not found"})

    return {
        "message": "Welcome home!",
        "user": user
    }
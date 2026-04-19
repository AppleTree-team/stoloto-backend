from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.auth_service import decode_session_token
from app.services.user_service import get_user_profile

router = APIRouter()


@router.get("/home")
def home(request: Request):
    token = request.cookies.get("session_id")

    if not token:
        return JSONResponse(status_code=401, content={"detail": "No session"})

    payload = decode_session_token(token)

    if not payload:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    profile = get_user_profile(payload["user_id"])

    if not profile:
        return JSONResponse(status_code=404, content={"detail": "User not found"})

    return profile
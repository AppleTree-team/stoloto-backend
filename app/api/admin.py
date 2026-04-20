from typing import List

from fastapi import APIRouter, Depends, HTTPException, Body

from app.services import pattern_service
#from app.services.auth_service import get_current_user_profile, require_session_payload
from app.api.deps import get_current_user_profile, require_session_payload


router = APIRouter(prefix="/admin", tags=["Admin"])


# =========================================
# 🛡️ HELPERS
# =========================================

def ensure_admin(profile: dict):
    if not profile["is_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")


# =========================================
# 🏠 MAIN
# =========================================

@router.get("/")
def admin_main(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    return profile


# =========================================
# 📤 GET PATTERNS
# =========================================

@router.get("/patterns")
def get_patterns(
    game: str,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return pattern_service.export_patterns(game)


@router.get("/patterns/{pattern_id}")
def get_pattern(
    pattern_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern = pattern_service.get_pattern_by_id(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    return pattern


# =========================================
# ➕ CREATE
# =========================================

@router.post("/patterns")
def create_pattern(
    data: dict = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern_id = pattern_service.create_pattern(data)
    return {"id": pattern_id}


# =========================================
# 🔁 UPDATE (VERSIONING)
# =========================================

@router.post("/patterns/{pattern_id}/update")
def update_pattern(
    pattern_id: int,
    data: dict = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    new_id = pattern_service.update_pattern(pattern_id, data)
    return {"id": new_id}


# =========================================
# 🟢 ACTIVATE / DEACTIVATE
# =========================================

@router.post("/patterns/{pattern_id}/activate")
def activate_pattern(
    pattern_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern_service.set_pattern_active(pattern_id, True)
    return {"status": "ok"}


@router.post("/patterns/{pattern_id}/deactivate")
def deactivate_pattern(
    pattern_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern_service.set_pattern_active(pattern_id, False)
    return {"status": "ok"}


# =========================================
# ⚡ BULK
# =========================================

@router.post("/patterns/bulk/activate")
def bulk_activate(
    ids: List[int] = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern_service.bulk_activate_patterns(ids)
    return {"status": "ok"}


@router.post("/patterns/bulk/deactivate")
def bulk_deactivate(
    ids: List[int] = Body(...),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)

    pattern_service.bulk_deactivate_patterns(ids)
    return {"status": "ok"}


# from fastapi import APIRouter, Depends
#
# from app.api.deps import get_current_user_profile, require_session_payload
#
# router = APIRouter(prefix="/admin", tags=["Admin"])
#
#
# @router.get("/")
# def admin_main(
#     profile:  dict = Depends(get_current_user_profile),
#     _payload: dict = Depends(require_session_payload),
# ):
#     """
#     Достаёт данные из JWT ДО вызова эндпоинта (через dependency) и возвращает профиль.
#
#     `_payload` здесь не используется напрямую — он нужен, чтобы гарантировать
#     `request.state.jwt_payload` для кода ниже/внутренних функций при расширении логики.
#     """
#     return profile
#




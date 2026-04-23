from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import ensure_admin, get_current_user_profile, require_session_payload
from app.services import admin_service


router = APIRouter(prefix="/admin", tags=["Admin"])


class ConfigPatch(BaseModel):
    max_active_rooms: Optional[int] = Field(None, ge=0)
    casino_balance: Optional[int] = Field(None, ge=0)
    bots_enabled: Optional[bool] = None
    min_join_cost: Optional[int] = Field(None, ge=0)
    max_join_cost: Optional[int] = Field(None, ge=0)


class BalanceAdjustRequest(BaseModel):
    amount: int
    reason: str
    room_id: Optional[int] = None


class RefundRoomRequest(BaseModel):
    reason: str


@router.get("/config")
def admin_get_config(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return admin_service.get_system_config()


@router.patch("/config")
def admin_patch_config(
    data: ConfigPatch,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    res = admin_service.update_system_config(
        max_active_rooms=data.max_active_rooms,
        casino_balance=data.casino_balance,
        bots_enabled=data.bots_enabled,
        min_join_cost=data.min_join_cost,
        max_join_cost=data.max_join_cost,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Config update failed"))
    return res["config"]


@router.get("/users/search")
def admin_user_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return {"items": admin_service.search_users(q, limit=limit)}


@router.get("/users/{user_id}/history")
def admin_user_history(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return {"user_id": int(user_id), "items": admin_service.get_user_history_admin(int(user_id), limit=int(limit))}


@router.get("/users/{user_id}/current_game")
def admin_user_current_game(
    user_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    item = admin_service.get_user_current_game_admin(int(user_id))
    return {"user_id": int(user_id), "has_active_game": bool(item), "item": item}


@router.post("/users/{user_id}/adjust_balance")
def admin_adjust_user_balance(
    user_id: int,
    data: BalanceAdjustRequest,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    res = admin_service.adjust_user_balance(
        admin_user_id=int(profile["id"]),
        user_id=int(user_id),
        amount=int(data.amount),
        reason=str(data.reason),
        room_id=int(data.room_id) if data.room_id is not None else None,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Adjustment failed"))
    return res


@router.get("/rooms")
def admin_list_rooms(
    status: Optional[str] = Query(None, description="waiting|lobby|shop|running|finished"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return {"items": admin_service.list_rooms(status=status, limit=limit, offset=offset)}


@router.get("/rooms/history")
def admin_rooms_history(
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return {"items": admin_service.list_finished_rooms(days=int(days), limit=int(limit), offset=int(offset))}


@router.get("/rooms/search")
def admin_room_search(
    token: Optional[str] = Query(None),
    room_id: Optional[int] = Query(None, ge=1),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    if token:
        room = admin_service.get_room_by_token_admin(token)
        return {"item": room}
    if room_id:
        room = admin_service.get_room_by_id_admin(int(room_id))
        return {"item": room}
    raise HTTPException(status_code=400, detail="token or room_id is required")


@router.get("/rooms/{room_id}/card")
def admin_room_card(
    room_id: int,
    ledger_limit: int = Query(200, ge=1, le=2000),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    card = admin_service.get_room_card(int(room_id), ledger_limit=int(ledger_limit))
    if not card:
        raise HTTPException(status_code=404, detail="Room not found")
    return card


@router.post("/rooms/{room_id}/force_finish_running")
def admin_force_finish_running(
    room_id: int,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    res = admin_service.force_finish_running_room(int(room_id))
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Finish failed"))
    return res


@router.post("/rooms/{room_id}/force_refund")
def admin_force_refund(
    room_id: int,
    data: RefundRoomRequest,
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    res = admin_service.force_refund_room(
        admin_user_id=int(profile["id"]),
        room_id=int(room_id),
        reason=str(data.reason),
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Refund failed"))
    return res


@router.get("/ledger")
def admin_ledger(
    room_id: Optional[int] = Query(None, ge=1),
    user_id: Optional[int] = Query(None, ge=1),
    account: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    rows = admin_service.list_ledger(
        room_id=room_id,
        user_id=user_id,
        account=account,
        entry_type=entry_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"items": rows}


@router.get("/ledger/export.csv")
def admin_ledger_export_csv(
    room_id: Optional[int] = Query(None, ge=1),
    user_id: Optional[int] = Query(None, ge=1),
    account: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(2000, ge=1, le=50000),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    rows = admin_service.list_ledger(
        room_id=room_id,
        user_id=user_id,
        account=account,
        entry_type=entry_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=0,
    )
    csv_text = admin_service.export_ledger_csv(rows)
    return Response(content=csv_text, media_type="text/csv")


@router.get("/anomalies")
def admin_anomalies(
    days: int = Query(7, ge=1, le=365),
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return admin_service.get_anomalies(days=int(days))


@router.get("/reconcile/casino")
def admin_reconcile_casino(
    profile: dict = Depends(get_current_user_profile),
    _payload: dict = Depends(require_session_payload),
):
    ensure_admin(profile)
    return admin_service.reconcile_casino_balance()

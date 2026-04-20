from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from app.services import pattern_service
from app.api.deps import get_current_user_profile, require_session_payload, ensure_admin

router = APIRouter(prefix="/patterns", tags=["Admin"])


# =========================================
# 📦 PYDANTIC MODELS
# =========================================

class PatternCreateRequest(BaseModel):
    game: str = Field(..., description="Game identifier")
    name: str = Field(..., description="Pattern name")
    description: Optional[str] = Field(None, description="Pattern description")
    data: dict = Field(..., description="Pattern data/content")
    is_active: bool = Field(True, description="Active status")


class PatternEditRequest(BaseModel):
    pattern_id: int = Field(..., description="Pattern ID to edit")
    game: Optional[str] = Field(None, description="Game identifier")
    name: Optional[str] = Field(None, description="Pattern name")
    description: Optional[str] = Field(None, description="Pattern description")
    data: Optional[dict] = Field(None, description="Pattern data/content")
    is_active: Optional[bool] = Field(None, description="Active status")


class PatternDeleteRequest(BaseModel):
    pattern_id: int = Field(..., description="Pattern ID to delete")
    hard_delete: bool = Field(False, description="Permanently delete instead of soft delete")


class BulkActivateRequest(BaseModel):
    ids: List[int] = Field(..., description="List of pattern IDs")


# =========================================
# 📤 GET PATTERNS (LIST/EXPORT)
# =========================================

@router.get("/")
def get_patterns(
        game: str,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Get all patterns for a specific game (admin only)"""
    ensure_admin(profile)
    return pattern_service.export_patterns(game)


@router.get("/{pattern_id}")
def get_pattern(
        pattern_id: int,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Get single pattern by ID (admin only)"""
    ensure_admin(profile)

    pattern = pattern_service.get_pattern_by_id(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    return pattern


# =========================================
# ➕ CREATE PATTERN (from modal window)
# =========================================

# create
@router.post("/")
def create_pattern(
        request: PatternCreateRequest,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """
    Create a new pattern from modal window

    - **game**: Game identifier
    - **name**: Pattern name
    - **description**: Optional description
    - **data**: Pattern content/data
    - **is_active**: Whether pattern is active by default
    """
    ensure_admin(profile)

    # Convert request to dict for service
    pattern_data = request.dict(exclude_unset=True)

    pattern_id = pattern_service.create_pattern(pattern_data)
    return {
        "status": "success",
        "message": "Pattern created successfully",
        "id": pattern_id
    }


# =========================================
# ✏️ EDIT PATTERN (Save button → confirmation)
# =========================================

@router.update("/edit")
def edit_pattern(
        request: PatternEditRequest,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """
    Edit existing pattern (Save button with confirmation)

    - **pattern_id**: ID of pattern to edit
    - Only provided fields will be updated
    - Creates a new version of the pattern
    """
    ensure_admin(profile)

    # Check if pattern exists
    existing_pattern = pattern_service.get_pattern_by_id(request.pattern_id)
    if not existing_pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # Convert request to dict, removing None values and pattern_id
    update_data = request.dict(exclude_unset=True, exclude={"pattern_id"})

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields to update provided"
        )

    # Update pattern (creates new version)
    new_id = pattern_service.update_pattern(request.pattern_id, update_data)

    return {
        "status": "success",
        "message": "Pattern updated successfully",
        "old_id": request.pattern_id,
        "new_id": new_id
    }


# =========================================
# 🗑️ DELETE PATTERN (Delete pattern button)
# =========================================

@router.delete("/")
def delete_pattern(
        request: PatternDeleteRequest,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """
    Delete pattern (Delete pattern button)

    - **pattern_id**: ID of pattern to delete
    - **hard_delete**: If True, permanently delete; if False, soft delete
    """
    ensure_admin(profile)

    # Check if pattern exists
    existing_pattern = pattern_service.get_pattern_by_id(request.pattern_id)
    if not existing_pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # Perform deletion
    if request.hard_delete:
        pattern_service.hard_delete_pattern(request.pattern_id)
        message = "Pattern permanently deleted"
    else:
        pattern_service.soft_delete_pattern(request.pattern_id)
        message = "Pattern deactivated (soft deleted)"

    return {
        "status": "success",
        "message": message,
        "pattern_id": request.pattern_id,
        "hard_delete": request.hard_delete
    }









# =========================================
# 🔁 LEGACY UPDATE ENDPOINT (keep for compatibility)
# =========================================

@router.post("/{pattern_id}/update")
def update_pattern_legacy(
        pattern_id: int,
        data: dict = Body(...),
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Legacy endpoint for pattern update (kept for backward compatibility)"""
    ensure_admin(profile)

    new_id = pattern_service.update_pattern(pattern_id, data)
    return {"id": new_id}


# =========================================
# 🟢 ACTIVATE / DEACTIVATE (individual)
# =========================================

@router.post("/{pattern_id}/activate")
def activate_pattern(
        pattern_id: int,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Activate a single pattern"""
    ensure_admin(profile)

    pattern_service.set_pattern_active(pattern_id, True)
    return {"status": "ok", "message": "Pattern activated"}


@router.post("/{pattern_id}/deactivate")
def deactivate_pattern(
        pattern_id: int,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Deactivate a single pattern"""
    ensure_admin(profile)

    pattern_service.set_pattern_active(pattern_id, False)
    return {"status": "ok", "message": "Pattern deactivated"}


# =========================================
# ⚡ BULK OPERATIONS
# =========================================

@router.post("/bulk/activate")
def bulk_activate(
        request: BulkActivateRequest,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Activate multiple patterns at once"""
    ensure_admin(profile)

    pattern_service.bulk_activate_patterns(request.ids)
    return {
        "status": "ok",
        "message": f"Activated {len(request.ids)} patterns",
        "ids": request.ids
    }


@router.post("/bulk/deactivate")
def bulk_deactivate(
        request: BulkActivateRequest,
        profile: dict = Depends(get_current_user_profile),
        _payload: dict = Depends(require_session_payload),
):
    """Deactivate multiple patterns at once"""
    ensure_admin(profile)

    pattern_service.bulk_deactivate_patterns(request.ids)
    return {
        "status": "ok",
        "message": f"Deactivated {len(request.ids)} patterns",
        "ids": request.ids
    }
"""
RFQ Stage routes — FastAPI router for RFQ_Stage endpoints.

Endpoints:
- GET    /rfqs/{rfqId}/stages                          — #11 List stages for RFQ
- GET    /rfqs/{rfqId}/stages/{stageId}                — #12 Get stage detail
- PATCH  /rfqs/{rfqId}/stages/{stageId}                — #13 Update stage
- POST   /rfqs/{rfqId}/stages/{stageId}/notes          — #14 Add note
- POST   /rfqs/{rfqId}/stages/{stageId}/files          — #15 Upload file
- POST   /rfqs/{rfqId}/stages/{stageId}/advance        — #16 Advance to next stage

File endpoints (#28–#30) are in file_route.py.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, Body

from src.translators.rfq_stage_translator import (
    RfqStageAdvanceRequest, RfqStageUpdateRequest, NoteCreateRequest,
    RfqStageDetailResponse, StageNoteResponse, StageFileResponse,
    RfqStageListResponse
)
from src.app_context import get_rfq_stage_controller
from src.controllers.rfq_stage_controller import RfqStageController
from src.utils.auth import AuthContext, Permissions, require_permission

router = APIRouter(prefix="/rfqs/{rfq_id}/stages", tags=["RFQ_Stage"])


@router.get("", response_model=RfqStageListResponse)
def list_stages(
    rfq_id: UUID,
    _auth=Depends(require_permission(Permissions.RFQ_STAGE_READ)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#11 — List stages for RFQ, ordered by stage order."""
    return ctrl.list(rfq_id)


@router.get("/{stage_id}", response_model=RfqStageDetailResponse)
def get_stage(
    rfq_id: UUID,
    stage_id: UUID,
    _auth=Depends(require_permission(Permissions.RFQ_STAGE_READ)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#12 — Get stage detail with embedded subtasks, notes, files."""
    return ctrl.get(rfq_id, stage_id)


@router.patch("/{stage_id}", response_model=RfqStageDetailResponse)
def update_stage(
    rfq_id: UUID,
    stage_id: UUID,
    body: RfqStageUpdateRequest,
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_STAGE_UPDATE)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#13 — Update progress, captured_data, blocker_status."""
    return ctrl.update(rfq_id, stage_id, body, actor_name=auth.user_name)


@router.post("/{stage_id}/notes", status_code=201, response_model=StageNoteResponse)
def add_note(
    rfq_id: UUID,
    stage_id: UUID,
    body: NoteCreateRequest,
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_STAGE_ADD_NOTE)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#14 — Add note to stage (append-only)."""
    return ctrl.add_note(rfq_id, stage_id, body, user_name=auth.user_name)


@router.post("/{stage_id}/files", status_code=201, response_model=StageFileResponse)
async def upload_file(
    rfq_id: UUID,
    stage_id: UUID,
    file: UploadFile = File(...),
    type: str = Form(...),
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_STAGE_ADD_FILE)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#15 — Upload file to stage (multipart/form-data)."""
    content = await file.read()
    return ctrl.upload_file(
        rfq_id,
        stage_id,
        file.filename,
        type,
        content,
        uploaded_by=auth.user_name,
    )


@router.post("/{stage_id}/advance", response_model=RfqStageDetailResponse)
def advance_stage(
    rfq_id: UUID,
    stage_id: UUID,
    body: RfqStageAdvanceRequest = Body(default_factory=RfqStageAdvanceRequest),
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_STAGE_ADVANCE)),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#16 — Advance to next stage. Validates blockers and mandatory fields."""
    return ctrl.advance(
        rfq_id,
        stage_id,
        request=body,
        actor_team=auth.team,
        actor_user_id=auth.user_id,
        actor_name=auth.user_name,
        actor_permissions=auth.permissions,
    )

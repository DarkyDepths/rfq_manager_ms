"""
RFQ Stage routes — FastAPI router for RFQ_Stage endpoints.

Endpoints:
- GET    /rfqs/{rfqId}/stages                          — #10 List stages for RFQ
- GET    /rfqs/{rfqId}/stages/{stageId}                — #11 Get stage detail
- PATCH  /rfqs/{rfqId}/stages/{stageId}                — #12 Update stage
- POST   /rfqs/{rfqId}/stages/{stageId}/notes          — #13 Add note
- POST   /rfqs/{rfqId}/stages/{stageId}/files          — #14 Upload file
- POST   /rfqs/{rfqId}/stages/{stageId}/advance        — #15 Advance to next stage

File endpoints (#26–#28) are in file_route.py.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form

from src.translators.rfq_stage_translator import (
    RfqStageUpdateRequest, NoteCreateRequest,
    RfqStageResponse, RfqStageDetailResponse, StageNoteResponse, StageFileResponse,
    RfqStageListResponse
)
from src.app_context import get_rfq_stage_controller
from src.controllers.rfq_stage_controller import RfqStageController

router = APIRouter(prefix="/rfqs/{rfq_id}/stages", tags=["RFQ_Stage"])


@router.get("", response_model=RfqStageListResponse)
def list_stages(rfq_id: UUID, ctrl: RfqStageController = Depends(get_rfq_stage_controller)):
    """#10 — List stages for RFQ, ordered by stage order."""
    return ctrl.list(rfq_id)


@router.get("/{stage_id}", response_model=RfqStageDetailResponse)
def get_stage(rfq_id: UUID, stage_id: UUID, ctrl: RfqStageController = Depends(get_rfq_stage_controller)):
    """#11 — Get stage detail with embedded subtasks, notes, files."""
    return ctrl.get(rfq_id, stage_id)


@router.patch("/{stage_id}", response_model=RfqStageDetailResponse)
def update_stage(rfq_id: UUID, stage_id: UUID, body: RfqStageUpdateRequest, ctrl: RfqStageController = Depends(get_rfq_stage_controller)):
    """#12 — Update progress, captured_data, blocker_status."""
    return ctrl.update(rfq_id, stage_id, body)


@router.post("/{stage_id}/notes", status_code=201, response_model=StageNoteResponse)
def add_note(rfq_id: UUID, stage_id: UUID, body: NoteCreateRequest, ctrl: RfqStageController = Depends(get_rfq_stage_controller)):
    """#13 — Add note to stage (append-only)."""
    return ctrl.add_note(rfq_id, stage_id, body)


@router.post("/{stage_id}/files", status_code=201, response_model=StageFileResponse)
async def upload_file(
    rfq_id: UUID,
    stage_id: UUID,
    file: UploadFile = File(...),
    type: str = Form(...),
    ctrl: RfqStageController = Depends(get_rfq_stage_controller),
):
    """#14 — Upload file to stage (multipart/form-data)."""
    content = await file.read()
    return ctrl.upload_file(rfq_id, stage_id, file.filename, type, content)


@router.post("/{stage_id}/advance", response_model=RfqStageDetailResponse)
def advance_stage(rfq_id: UUID, stage_id: UUID, ctrl: RfqStageController = Depends(get_rfq_stage_controller)):
    """#15 — Advance to next stage. Validates blockers and mandatory fields."""
    return ctrl.advance(rfq_id, stage_id)

"""
Subtask routes — FastAPI router for Subtask endpoints.

Endpoints:
- POST   /rfqs/{rfqId}/stages/{stageId}/subtasks               — #16 Create subtask
- GET    /rfqs/{rfqId}/stages/{stageId}/subtasks               — #17 List subtasks
- PATCH  /rfqs/{rfqId}/stages/{stageId}/subtasks/{subtaskId}   — #18 Update subtask
- DELETE /rfqs/{rfqId}/stages/{stageId}/subtasks/{subtaskId}   — #19 Delete subtask (soft)
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Response

from src.translators.subtask_translator import SubtaskCreateRequest, SubtaskUpdateRequest, SubtaskResponse, SubtaskListResponse
from src.app_context import get_subtask_controller
from src.controllers.subtask_controller import SubtaskController

router = APIRouter(prefix="/rfqs/{rfq_id}/stages/{stage_id}/subtasks", tags=["Subtask"])


@router.post("", status_code=201, response_model=SubtaskResponse)
def create_subtask(rfq_id: UUID, stage_id: UUID, body: SubtaskCreateRequest, ctrl: SubtaskController = Depends(get_subtask_controller)):
    """#16 — Create subtask."""
    return ctrl.create(rfq_id, stage_id, body)


@router.get("", response_model=SubtaskListResponse)
def list_subtasks(rfq_id: UUID, stage_id: UUID, ctrl: SubtaskController = Depends(get_subtask_controller)):
    """#17 — List subtasks (active only, soft-deleted excluded)."""
    return ctrl.list(rfq_id, stage_id)


@router.patch("/{subtask_id}", response_model=SubtaskResponse)
def update_subtask(rfq_id: UUID, stage_id: UUID, subtask_id: UUID, body: SubtaskUpdateRequest, ctrl: SubtaskController = Depends(get_subtask_controller)):
    """#18 — Update subtask. Auto-updates parent stage progress."""
    return ctrl.update(rfq_id, stage_id, subtask_id, body)


@router.delete("/{subtask_id}", status_code=204)
def delete_subtask(rfq_id: UUID, stage_id: UUID, subtask_id: UUID, ctrl: SubtaskController = Depends(get_subtask_controller)):
    """#19 — Soft delete subtask."""
    ctrl.delete(rfq_id, stage_id, subtask_id)
    return Response(status_code=204)
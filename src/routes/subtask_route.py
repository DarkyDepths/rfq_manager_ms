"""
Subtask routes — FastAPI router for Subtask endpoints.

Endpoints:
- POST   /rfqs/{rfqId}/stages/{stageId}/subtasks               — #17 Create subtask
- GET    /rfqs/{rfqId}/stages/{stageId}/subtasks               — #18 List subtasks
- PATCH  /rfqs/{rfqId}/stages/{stageId}/subtasks/{subtaskId}   — #19 Update subtask
- DELETE /rfqs/{rfqId}/stages/{stageId}/subtasks/{subtaskId}   — #20 Delete subtask (soft)
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Response

from src.translators.subtask_translator import SubtaskCreateRequest, SubtaskUpdateRequest, SubtaskResponse, SubtaskListResponse
from src.app_context import get_subtask_controller
from src.controllers.subtask_controller import SubtaskController
from src.utils.auth import Permissions, require_permission

router = APIRouter(prefix="/rfqs/{rfq_id}/stages/{stage_id}/subtasks", tags=["Subtask"])


@router.post("", status_code=201, response_model=SubtaskResponse)
def create_subtask(
    rfq_id: UUID,
    stage_id: UUID,
    body: SubtaskCreateRequest,
    _auth=Depends(require_permission(Permissions.SUBTASK_CREATE)),
    ctrl: SubtaskController = Depends(get_subtask_controller),
):
    """#17 — Create subtask."""
    return ctrl.create(rfq_id, stage_id, body)


@router.get("", response_model=SubtaskListResponse)
def list_subtasks(
    rfq_id: UUID,
    stage_id: UUID,
    _auth=Depends(require_permission(Permissions.SUBTASK_READ)),
    ctrl: SubtaskController = Depends(get_subtask_controller),
):
    """#18 — List subtasks (active only, soft-deleted excluded)."""
    return ctrl.list(rfq_id, stage_id)


@router.patch("/{subtask_id}", response_model=SubtaskResponse)
def update_subtask(
    rfq_id: UUID,
    stage_id: UUID,
    subtask_id: UUID,
    body: SubtaskUpdateRequest,
    _auth=Depends(require_permission(Permissions.SUBTASK_UPDATE)),
    ctrl: SubtaskController = Depends(get_subtask_controller),
):
    """#19 — Update subtask. Auto-updates parent stage progress."""
    return ctrl.update(rfq_id, stage_id, subtask_id, body)


@router.delete("/{subtask_id}", status_code=204)
def delete_subtask(
    rfq_id: UUID,
    stage_id: UUID,
    subtask_id: UUID,
    _auth=Depends(require_permission(Permissions.SUBTASK_DELETE)),
    ctrl: SubtaskController = Depends(get_subtask_controller),
):
    """#20 — Soft delete subtask."""
    ctrl.delete(rfq_id, stage_id, subtask_id)
    return Response(status_code=204)

"""
Workflow routes — FastAPI router for Workflow endpoints.

Endpoints:
- GET    /workflows              — #8 List all workflows
- GET    /workflows/{workflowId} — #9 Get workflow detail with stages
- PATCH  /workflows/{workflowId} — #10 Update workflow (name, description, is_active, is_default)
"""

from uuid import UUID
from fastapi import APIRouter, Depends

from src.translators.workflow_translator import WorkflowUpdateRequest, WorkflowDetail, WorkflowListResponse
from src.app_context import get_workflow_controller
from src.controllers.workflow_controller import WorkflowController

router = APIRouter(prefix="/workflows", tags=["Workflow"])


@router.get("", response_model=WorkflowListResponse)
def list_workflows(ctrl: WorkflowController = Depends(get_workflow_controller)):
    """#8 — List all workflows (active and inactive)."""
    return ctrl.list()


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: UUID, ctrl: WorkflowController = Depends(get_workflow_controller)):
    """#9 — Get workflow detail with stage templates."""
    return ctrl.get(workflow_id)


@router.patch("/{workflow_id}", response_model=WorkflowDetail)
def update_workflow(workflow_id: UUID, body: WorkflowUpdateRequest, ctrl: WorkflowController = Depends(get_workflow_controller)):
    """#10 — Update workflow (name, description, is_active, is_default)."""
    return ctrl.update(workflow_id, body)

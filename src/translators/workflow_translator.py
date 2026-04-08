"""
Workflow translator — converts between Pydantic schemas and the Workflow SQLAlchemy model.

Functions:
- to_model(schema)     — WorkflowUpdateRequest → Workflow model instance
- to_summary(model)    — Workflow model → WorkflowSummary response schema
- to_detail(model)     — Workflow model → WorkflowDetail response schema (with stages[])
"""

from uuid import UUID
from typing import Optional, List

from pydantic import BaseModel


# ═══════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════

class WorkflowUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


# ═══════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════

class StageTemplateResponse(BaseModel):
    id: UUID
    name: str
    order: int
    default_team: Optional[str] = None
    planned_duration_days: int
    is_required: bool = False

    class Config:
        from_attributes = True


class WorkflowSummary(BaseModel):
    id: UUID
    name: str
    code: str
    stage_count: int = 0
    is_active: bool
    is_default: bool
    selection_mode: str = "fixed"
    base_workflow_id: Optional[UUID] = None

    class Config:
        from_attributes = True

class WorkflowListResponse(BaseModel):
    data: List[WorkflowSummary]


class WorkflowDetail(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str] = None
    stage_count: int = 0
    is_active: bool
    is_default: bool
    selection_mode: str = "fixed"
    base_workflow_id: Optional[UUID] = None
    stages: List[StageTemplateResponse] = []

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════
# CONVERSION FUNCTIONS
# ═══════════════════════════════════════════════════

def to_summary(workflow, stages=None) -> WorkflowSummary:
    effective_stages = stages if stages is not None else workflow.stages
    return WorkflowSummary(
        id=workflow.id,
        name=workflow.name,
        code=workflow.code,
        stage_count=len(effective_stages) if effective_stages else 0,
        is_active=workflow.is_active,
        is_default=workflow.is_default,
        selection_mode=getattr(workflow, "selection_mode", "fixed") or "fixed",
        base_workflow_id=getattr(workflow, "base_workflow_id", None),
    )


def to_detail(workflow, stages=None) -> WorkflowDetail:
    effective_stages = stages if stages is not None else workflow.stages
    return WorkflowDetail(
        id=workflow.id,
        name=workflow.name,
        code=workflow.code,
        description=workflow.description,
        stage_count=len(effective_stages) if effective_stages else 0,
        is_active=workflow.is_active,
        is_default=workflow.is_default,
        selection_mode=getattr(workflow, "selection_mode", "fixed") or "fixed",
        base_workflow_id=getattr(workflow, "base_workflow_id", None),
        stages=[StageTemplateResponse.model_validate(s) for s in effective_stages],
    )

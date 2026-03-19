"""
RFQ Stage translator — converts between Pydantic schemas and the RfqStage SQLAlchemy model.

Functions:
- to_model(schema)     — RfqStageUpdateRequest → RfqStage model instance
- to_schema(model)     — RfqStage model → RfqStage response schema
- to_detail(model)     — RfqStage model → RfqStageDetail response (with subtasks, notes, files)
- note_to_schema(model) — RfqNote model → StageNote response schema
- file_to_schema(model) — RfqFile model → StageFile response schema
"""

from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Literal

from pydantic import BaseModel


# ═══════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════

class RfqStageUpdateRequest(BaseModel):
    progress: Optional[int] = None
    assigned_team: Optional[str] = None
    captured_data: Optional[dict] = None
    blocker_status: Optional[Literal["Blocked", "Resolved"]] = None
    blocker_reason_code: Optional[str] = None

class NoteCreateRequest(BaseModel):
    text: str


# ═══════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════

class StageNoteResponse(BaseModel):
    id: UUID
    user_name: str
    text: str
    created_at: datetime
    class Config:
        from_attributes = True

class StageFileResponse(BaseModel):
    id: UUID
    filename: str
    download_url: str
    type: str
    uploaded_by: str
    size_bytes: Optional[int] = None
    uploaded_at: datetime
    class Config:
        from_attributes = True

class SubtaskBrief(BaseModel):
    id: UUID
    name: str
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    progress: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class RfqStageResponse(BaseModel):
    id: UUID
    name: str
    order: int
    assigned_team: Optional[str] = None
    status: str
    progress: int
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    blocker_status: Optional[str] = None
    blocker_reason_code: Optional[str] = None
    class Config:
        from_attributes = True

class RfqStageListResponse(BaseModel):
    data: List[RfqStageResponse]
    class Config:
        from_attributes = True

class RfqStageDetailResponse(RfqStageResponse):
    captured_data: Optional[dict] = None
    mandatory_fields: Optional[str] = None
    notes: List[StageNoteResponse] = []
    files: List[StageFileResponse] = []
    subtasks: List[SubtaskBrief] = []


# ═══════════════════════════════════════════════════
# CONVERSION FUNCTIONS
# ═══════════════════════════════════════════════════

def to_response(stage) -> RfqStageResponse:
    return RfqStageResponse.model_validate(stage)

def to_detail(stage, notes=None, files=None, subtasks=None) -> RfqStageDetailResponse:
    return RfqStageDetailResponse(
        id=stage.id,
        name=stage.name,
        order=stage.order,
        assigned_team=stage.assigned_team,
        status=stage.status,
        progress=stage.progress,
        planned_start=stage.planned_start,
        planned_end=stage.planned_end,
        actual_start=stage.actual_start,
        actual_end=stage.actual_end,
        blocker_status=stage.blocker_status,
        blocker_reason_code=stage.blocker_reason_code,
        captured_data=stage.captured_data,
        mandatory_fields=stage.mandatory_fields,
        notes=[StageNoteResponse.model_validate(n) for n in (notes or [])],
        files=[file_to_schema(f) for f in (files or [])],
        subtasks=[SubtaskBrief.model_validate(s) for s in (subtasks or [])],
    )


def file_to_schema(file) -> StageFileResponse:
    return StageFileResponse(
        id=file.id,
        filename=file.filename,
        download_url=f"/rfq-manager/v1/files/{file.id}/download",
        type=file.type,
        uploaded_by=file.uploaded_by,
        size_bytes=file.size_bytes,
        uploaded_at=file.uploaded_at,
    )

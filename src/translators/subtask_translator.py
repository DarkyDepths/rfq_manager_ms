"""
Subtask translator — converts between Pydantic schemas and the Subtask SQLAlchemy model.

Functions:
- to_model(schema)    — SubtaskCreateRequest / SubtaskUpdateRequest → Subtask model instance
- to_schema(model)    — Subtask model → Subtask response schema
"""

from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel


class SubtaskCreateRequest(BaseModel):
    name: str
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None

class SubtaskUpdateRequest(BaseModel):
    name: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    progress: Optional[int] = None
    status: Optional[Literal["Open", "In progress", "Done"]] = None

class SubtaskResponse(BaseModel):
    id: UUID
    rfq_stage_id: UUID
    name: str
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    progress: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class SubtaskListResponse(BaseModel):
    data: List[SubtaskResponse]

def to_response(subtask) -> SubtaskResponse:
    return SubtaskResponse.model_validate(subtask)

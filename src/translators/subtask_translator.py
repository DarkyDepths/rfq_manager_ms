"""
Subtask translator — converts between Pydantic schemas and the Subtask SQLAlchemy model.

Functions:
- to_model(schema)    — SubtaskCreateRequest / SubtaskUpdateRequest → Subtask model instance
- to_schema(model)    — Subtask model → Subtask response schema
"""

from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


SUBTASK_NAME_REQUIRED_MESSAGE = "Subtask name is required."
SUBTASK_ASSIGNEE_REQUIRED_MESSAGE = "Please assign the subtask before creating it."
SUBTASK_DUE_DATE_REQUIRED_MESSAGE = (
    "Please choose a subtask due date before creating it."
)


class SubtaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_required_fields(self):
        normalized_name = self.name.strip() if isinstance(self.name, str) else None
        normalized_assigned_to = self.assigned_to.strip() if isinstance(self.assigned_to, str) else None

        self.name = normalized_name or None
        self.assigned_to = normalized_assigned_to or None

        if not self.name:
            raise ValueError(SUBTASK_NAME_REQUIRED_MESSAGE)
        if not self.assigned_to:
            raise ValueError(SUBTASK_ASSIGNEE_REQUIRED_MESSAGE)
        if self.due_date is None:
            raise ValueError(SUBTASK_DUE_DATE_REQUIRED_MESSAGE)

        return self

class SubtaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
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

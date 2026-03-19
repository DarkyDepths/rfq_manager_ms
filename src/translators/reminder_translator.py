"""
Reminder translator — converts between Pydantic schemas and the Reminder SQLAlchemy model.

Functions:
- to_model(schema)    — ReminderCreateRequest → Reminder model instance
- to_schema(model)    — Reminder model → Reminder response schema (with computed delay_days)
- rule_to_schema(model) — ReminderRule model → ReminderRule response schema
"""

from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel


class ReminderCreateRequest(BaseModel):
    rfq_id: UUID
    rfq_stage_id: Optional[UUID] = None
    type: Literal["internal", "external"]
    message: str
    due_date: date
    assigned_to: Optional[str] = None

class ReminderRuleUpdateRequest(BaseModel):
    is_active: bool

class ReminderResponse(BaseModel):
    id: UUID
    rfq_id: UUID
    rfq_stage_id: Optional[UUID] = None
    type: str
    message: str
    due_date: date
    assigned_to: Optional[str] = None
    status: str
    delay_days: int = 0          # computed, not from DB
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_sent_at: Optional[datetime] = None
    send_count: int
    class Config:
        from_attributes = True

class ReminderRuleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    scope: str
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ReminderStatsResponse(BaseModel):
    open_tasks: int
    overdue_tasks: int
    due_this_week: int
    with_active_reminders: int

class ReminderListResponse(BaseModel):
    data: List[ReminderResponse]

class ReminderRuleListResponse(BaseModel):
    data: List[ReminderRuleResponse]


def to_response(reminder) -> ReminderResponse:
    today = date.today()
    delay = max(0, (today - reminder.due_date).days) if reminder.due_date else 0

    return ReminderResponse(
        id=reminder.id,
        rfq_id=reminder.rfq_id,
        rfq_stage_id=reminder.rfq_stage_id,
        type=reminder.type,
        message=reminder.message,
        due_date=reminder.due_date,
        assigned_to=reminder.assigned_to,
        status=reminder.status,
        delay_days=delay,                # computed here
        created_by=reminder.created_by,
        created_at=reminder.created_at,
        updated_at=reminder.updated_at,
        last_sent_at=reminder.last_sent_at,
        send_count=reminder.send_count,
    )

def rule_to_response(rule) -> ReminderRuleResponse:
    return ReminderRuleResponse.model_validate(rule)

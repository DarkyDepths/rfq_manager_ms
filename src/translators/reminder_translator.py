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
from pydantic import BaseModel, model_validator


ACTIVE_REMINDER_STATUSES = frozenset({"open", "overdue"})
REMINDER_STATUS_OPEN = "open"
REMINDER_STATUS_OVERDUE = "overdue"
REMINDER_STATUS_RESOLVED = "resolved"
REMINDER_SOURCE_MANUAL = "manual"
REMINDER_SOURCE_AUTOMATIC = "automatic"


class ReminderCreateRequest(BaseModel):
    rfq_id: UUID
    rfq_stage_id: Optional[UUID] = None
    type: Literal["internal", "external"]
    message: str
    due_date: date
    assigned_to: Optional[str] = None

    @model_validator(mode="after")
    def normalize(self):
        normalized_message = self.message.strip() if isinstance(self.message, str) else ""
        if not normalized_message:
            raise ValueError("Reminder message is required.")
        self.message = normalized_message
        if isinstance(self.assigned_to, str):
            normalized_assigned_to = self.assigned_to.strip()
            self.assigned_to = normalized_assigned_to or None
        return self

class ReminderRuleUpdateRequest(BaseModel):
    is_active: bool

class ReminderResponse(BaseModel):
    id: UUID
    rfq_id: UUID
    rfq_stage_id: Optional[UUID] = None
    type: str
    message: str
    due_date: date
    rfq_code: Optional[str] = None
    rfq_name: Optional[str] = None
    rfq_deadline: Optional[date] = None
    rfq_stage_name: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Literal["open", "overdue", "resolved"]
    source: Literal["manual", "automatic"] = REMINDER_SOURCE_MANUAL
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


def normalize_reminder_status(status: str | None, due_date: date | None) -> Literal["open", "overdue", "resolved"]:
    today = date.today()
    normalized_status = (status or "").strip().lower()

    if normalized_status == REMINDER_STATUS_RESOLVED:
        return REMINDER_STATUS_RESOLVED

    if due_date and due_date < today:
        return REMINDER_STATUS_OVERDUE

    return REMINDER_STATUS_OPEN


def to_response(reminder) -> ReminderResponse:
    today = date.today()
    delay = max(0, (today - reminder.due_date).days) if reminder.due_date else 0
    normalized_status = normalize_reminder_status(reminder.status, reminder.due_date)

    return ReminderResponse(
        id=reminder.id,
        rfq_id=reminder.rfq_id,
        rfq_stage_id=reminder.rfq_stage_id,
        type=reminder.type,
        message=reminder.message,
        due_date=reminder.due_date,
        rfq_code=getattr(reminder, "rfq_code", None),
        rfq_name=getattr(reminder, "rfq_name", None),
        rfq_deadline=getattr(reminder, "rfq_deadline", None),
        rfq_stage_name=getattr(reminder, "rfq_stage_name", None),
        assigned_to=reminder.assigned_to,
        status=normalized_status,
        source=getattr(reminder, "source", REMINDER_SOURCE_MANUAL),
        delay_days=delay,                # computed here
        created_by=reminder.created_by,
        created_at=reminder.created_at,
        updated_at=reminder.updated_at,
        last_sent_at=reminder.last_sent_at,
        send_count=reminder.send_count,
    )

def rule_to_response(rule) -> ReminderRuleResponse:
    return ReminderRuleResponse.model_validate(rule)

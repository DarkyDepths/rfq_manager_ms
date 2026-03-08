"""
Reminder routes — FastAPI router for Reminder endpoints.

Endpoints:
- POST   /reminders              — #20 Create reminder
- GET    /reminders              — #21 List reminders (filter by user, status, rfq_id)
- GET    /reminders/stats        — #22 Reminder KPIs
- GET    /reminders/rules        — #23 List reminder rules
- PATCH  /reminders/rules/{ruleId} — #24 Toggle reminder rule
- POST   /reminders/test         — #25 Test reminder email
"""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Query

from src.translators.reminder_translator import (
    ReminderCreateRequest, ReminderRuleUpdateRequest, ReminderListResponse,
    ReminderResponse, ReminderRuleResponse, ReminderStatsResponse, ReminderRuleListResponse
)
from src.app_context import get_reminder_controller
from src.controllers.reminder_controller import ReminderController

router = APIRouter(prefix="/reminders", tags=["Reminder"])


@router.post("", status_code=201, response_model=ReminderResponse)
def create_reminder(body: ReminderCreateRequest, ctrl: ReminderController = Depends(get_reminder_controller)):
    """#20 — Create reminder."""
    return ctrl.create(body)


@router.get("", response_model=ReminderListResponse)
def list_reminders(
    user: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    rfq_id: Optional[UUID] = Query(None),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#21 — List reminders with filters."""
    return ctrl.list(user=user, status=status, rfq_id=rfq_id)


@router.get("/stats", response_model=ReminderStatsResponse)
def reminder_stats(ctrl: ReminderController = Depends(get_reminder_controller)):
    """#22 — Reminder KPIs."""
    return ctrl.get_stats()


@router.get("/rules", response_model=ReminderRuleListResponse)
def list_rules(ctrl: ReminderController = Depends(get_reminder_controller)):
    """#23 — List reminder rules."""
    return ctrl.list_rules()


@router.patch("/rules/{rule_id}", response_model=ReminderRuleResponse)
def update_rule(rule_id: UUID, body: ReminderRuleUpdateRequest, ctrl: ReminderController = Depends(get_reminder_controller)):
    """#24 — Toggle reminder rule active/inactive."""
    return ctrl.update_rule(rule_id, body)


@router.post("/test")
def test_reminder(ctrl: ReminderController = Depends(get_reminder_controller)):
    """#25 — Test reminder email (log-only in V1)."""
    return ctrl.test_email()

@router.post("/process")
def process_reminders(ctrl: ReminderController = Depends(get_reminder_controller)):
    """#26 — Trigger batch processing of due reminders."""
    return ctrl.process_reminders()

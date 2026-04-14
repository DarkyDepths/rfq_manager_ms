"""
Reminder routes — FastAPI router for Reminder endpoints.

Endpoints:
- POST   /reminders              — #21 Create reminder
- GET    /reminders              — #22 List reminders (filter by user, status, rfq_id)
- GET    /reminders/stats        — #23 Reminder KPIs
- GET    /reminders/rules        — #24 List reminder rules
- PATCH  /reminders/rules/{ruleId} — #25 Toggle reminder rule
- POST   /reminders/test         — #26 Test reminder email
- POST   /reminders/process      — #27 Trigger batch processing of due reminders
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
from src.utils.auth import AuthContext, Permissions, require_permission

router = APIRouter(prefix="/reminders", tags=["Reminder"])


@router.post("", status_code=201, response_model=ReminderResponse)
def create_reminder(
    body: ReminderCreateRequest,
    auth: AuthContext = Depends(require_permission(Permissions.REMINDER_CREATE)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#21 — Create reminder."""
    return ctrl.create(body, created_by=auth.user_name)


@router.get("", response_model=ReminderListResponse)
def list_reminders(
    user: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    rfq_id: Optional[UUID] = Query(None),
    _auth=Depends(require_permission(Permissions.REMINDER_READ)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#22 — List reminders with filters."""
    return ctrl.list(user=user, status=status, rfq_id=rfq_id)


@router.get("/stats", response_model=ReminderStatsResponse)
def reminder_stats(
    _auth=Depends(require_permission(Permissions.REMINDER_READ)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#23 — Reminder KPIs."""
    return ctrl.get_stats()


@router.get("/rules", response_model=ReminderRuleListResponse)
def list_rules(
    _auth=Depends(require_permission(Permissions.REMINDER_READ)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#24 — List reminder rules."""
    return ctrl.list_rules()


@router.patch("/rules/{rule_id}", response_model=ReminderRuleResponse)
def update_rule(
    rule_id: UUID,
    body: ReminderRuleUpdateRequest,
    _auth=Depends(require_permission(Permissions.REMINDER_UPDATE_RULES)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#25 — Toggle reminder rule active/inactive."""
    return ctrl.update_rule(rule_id, body)


@router.post("/test")
def test_reminder(
    auth: AuthContext = Depends(require_permission(Permissions.REMINDER_TEST)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#26 — Test reminder email (log-only in V1)."""
    return ctrl.test_email(actor_name=auth.user_name)

@router.post("/process")
def process_reminders(
    _auth=Depends(require_permission(Permissions.REMINDER_PROCESS)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """#27 — Trigger batch processing of due reminders."""
    return ctrl.process_reminders()


@router.post("/{reminder_id}/resolve", response_model=ReminderResponse)
def resolve_reminder(
    reminder_id: UUID,
    _auth=Depends(require_permission(Permissions.REMINDER_UPDATE)),
    ctrl: ReminderController = Depends(get_reminder_controller),
):
    """Resolve a reminder explicitly without deleting its history."""
    return ctrl.resolve(reminder_id)

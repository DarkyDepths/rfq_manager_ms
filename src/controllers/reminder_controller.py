"""
Reminder controller — business logic for the Reminder resource.

Orchestrates:
- Create reminder (auto-set created_by, status=open, send_count=0)
- List reminders with filters (user, status, rfq_id)
- Stats aggregation for tasks.html KPI cards
- Reminder rules: list and toggle is_active
- Test reminder email (send to current user)
- Batch processing support (rate-limit via last_sent_at, increment send_count)
"""

import logging
from datetime import date
from sqlalchemy.orm import Session

from src.datasources.reminder_datasource import ReminderDatasource
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.translators import reminder_translator
from src.utils.errors import ConflictError, NotFoundError, UnprocessableEntityError

logger = logging.getLogger(__name__)


REMINDER_PAST_DUE_DATE_MESSAGE = "Reminder due date cannot be in the past."
REMINDER_RFQ_DUE_DATE_WINDOW_MESSAGE = (
    "RFQ-level reminder due date must fall between today and the RFQ deadline."
)
REMINDER_STAGE_DUE_DATE_WINDOW_MESSAGE = (
    "Stage-linked reminder due date must fall within the current stage window."
)
REMINDER_STAGE_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE = (
    "Stage-linked reminder due date cannot be set because the current stage schedule is incomplete."
)


class ReminderController:

    def __init__(self, datasource: ReminderDatasource, session: Session):
        self.ds = datasource
        self.session = session

    def create(self, request: reminder_translator.ReminderCreateRequest, created_by: str):
        rfq = self.session.get(RFQ, request.rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{request.rfq_id}' not found")

        stage = None
        if request.rfq_stage_id is not None:
            stage = self.session.get(RFQStage, request.rfq_stage_id)
            if not stage:
                raise NotFoundError(f"RFQ stage '{request.rfq_stage_id}' not found")
            if stage.rfq_id != rfq.id:
                raise UnprocessableEntityError(
                    "Stage reminders must reference a stage belonging to the same RFQ."
                )

        self._validate_due_date(rfq, stage, request.due_date)

        data = request.model_dump()
        data["created_by"] = created_by
        data["status"] = reminder_translator.REMINDER_STATUS_OPEN
        data["source"] = reminder_translator.REMINDER_SOURCE_MANUAL
        data["reminder_rule_id"] = None
        if not data.get("assigned_to"):
            data["assigned_to"] = (
                stage.assigned_team
                if stage and stage.assigned_team
                else rfq.owner
            )
        reminder = self.ds.create(data)
        self._attach_context([reminder])
        self.session.commit()
        return reminder_translator.to_response(reminder)

    def list(self, user: str = None, status: str = None, rfq_id=None) -> dict:
        reminders = self.ds.list(user=user, status=status, rfq_id=rfq_id)
        self._attach_context(reminders)
        return {"data": [reminder_translator.to_response(r) for r in reminders]}

    def get_stats(self):
        return self.ds.get_stats()

    def list_rules(self) -> dict:
        rules = self.ds.list_rules()
        return {"data": [reminder_translator.rule_to_response(r) for r in rules]}

    def update_rule(self, rule_id, request: reminder_translator.ReminderRuleUpdateRequest):
        rule = self.ds.get_rule_by_id(rule_id)
        if not rule:
            raise NotFoundError(f"Reminder rule '{rule_id}' not found")

        update_data = request.model_dump(exclude_unset=True)
        rule = self.ds.update_rule(rule, update_data)
        self.session.commit()
        return reminder_translator.rule_to_response(rule)

    def test_email(self, *, actor_name: str | None = None):
        """V1: outbound delivery is stubbed to logger. Reminder ownership remains inside rfq_manager_ms."""
        recipient = actor_name or "current user"
        logger.info("TEST EMAIL: Would send test reminder email to %s", recipient)
        return {
            "message": (
                f"Test reminder delivery is log-only in V1; no email was sent to {recipient}."
            )
        }

    def process_reminders(self):
        """Invoke the pure batch processing logic."""
        from src.services.notification_service import NotificationService
        svc = NotificationService(self.session)
        result = svc.process_due_reminders()
        return {"message": result["message"], "data": result}

    def resolve(self, reminder_id):
        reminder = self.ds.get_by_id(reminder_id)
        if not reminder:
            raise NotFoundError(f"Reminder '{reminder_id}' not found")

        if getattr(reminder, "source", reminder_translator.REMINDER_SOURCE_MANUAL) == reminder_translator.REMINDER_SOURCE_AUTOMATIC:
            raise ConflictError(
                "Automatic reminders are resolved by batch when their generating condition is no longer true."
            )

        if reminder.status != reminder_translator.REMINDER_STATUS_RESOLVED:
            reminder = self.ds.update(
                reminder,
                {"status": reminder_translator.REMINDER_STATUS_RESOLVED},
            )
            self._attach_context([reminder])
            self.session.commit()

        self._attach_context([reminder])
        return reminder_translator.to_response(reminder)

    def _attach_context(self, reminders):
        if not reminders:
            return

        rfq_ids = {reminder.rfq_id for reminder in reminders if getattr(reminder, "rfq_id", None)}
        stage_ids = {
            reminder.rfq_stage_id
            for reminder in reminders
            if getattr(reminder, "rfq_stage_id", None)
        }

        rfq_map = {}
        if rfq_ids:
            rfqs = self.session.query(RFQ).filter(RFQ.id.in_(tuple(rfq_ids))).all()
            rfq_map = {rfq.id: rfq for rfq in rfqs}

        stage_map = {}
        if stage_ids:
            stages = self.session.query(RFQStage).filter(RFQStage.id.in_(tuple(stage_ids))).all()
            stage_map = {stage.id: stage for stage in stages}

        for reminder in reminders:
            rfq = rfq_map.get(reminder.rfq_id)
            stage = stage_map.get(getattr(reminder, "rfq_stage_id", None))
            setattr(reminder, "rfq_code", getattr(rfq, "rfq_code", None))
            setattr(reminder, "rfq_name", getattr(rfq, "name", None))
            setattr(reminder, "rfq_deadline", getattr(rfq, "deadline", None))
            setattr(reminder, "rfq_stage_name", getattr(stage, "name", None))

    def _validate_due_date(self, rfq: RFQ, stage: RFQStage | None, due_date: date):
        today = date.today()
        if due_date < today:
            raise UnprocessableEntityError(REMINDER_PAST_DUE_DATE_MESSAGE)

        if stage is None:
            if due_date > rfq.deadline:
                raise UnprocessableEntityError(REMINDER_RFQ_DUE_DATE_WINDOW_MESSAGE)
            return

        window_start, window_end = self._resolve_stage_window(stage)
        if window_start is None or window_end is None:
            raise UnprocessableEntityError(REMINDER_STAGE_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE)

        effective_window_start = today if today > window_start else window_start
        if due_date < effective_window_start or due_date > window_end:
            raise UnprocessableEntityError(REMINDER_STAGE_DUE_DATE_WINDOW_MESSAGE)

    @staticmethod
    def _resolve_stage_window(stage: RFQStage | None):
        if stage is None:
            return None, None

        planned_start = getattr(stage, "planned_start", None)
        planned_end = getattr(stage, "planned_end", None)
        actual_start = getattr(stage, "actual_start", None)
        actual_end = getattr(stage, "actual_end", None)

        if actual_start and actual_end:
            return actual_start, actual_end

        if actual_start:
            if planned_start is None or planned_end is None:
                return None, None

            planned_duration_days = max((planned_end - planned_start).days, 0)
            shifted_end = date.fromordinal(actual_start.toordinal() + planned_duration_days)
            return actual_start, shifted_end if shifted_end > planned_end else planned_end

        if planned_start is None or planned_end is None:
            return None, None

        return planned_start, planned_end

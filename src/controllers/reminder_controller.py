"""
Reminder controller — business logic for the Reminder resource.

Orchestrates:
- Create reminder (auto-set created_by, status=open, send_count=0)
- List reminders with filters (user, status, rfq_id)
- Stats aggregation for tasks.html KPI cards
- Reminder rules: list and toggle is_active
- Test reminder email (send to current user)
- Batch processing support (rate-limit via last_sent_at, increment send_count)

Dependencies: ReminderDatasource, EventBusConnector, IamServiceConnector
"""

import logging
from sqlalchemy.orm import Session

from src.datasources.reminder_datasource import ReminderDatasource
from src.translators import reminder_translator
from src.utils.errors import NotFoundError

logger = logging.getLogger(__name__)


class ReminderController:

    def __init__(self, datasource: ReminderDatasource, session: Session):
        self.ds = datasource
        self.session = session

    def create(self, request: reminder_translator.ReminderCreateRequest):
        data = request.model_dump()
        reminder = self.ds.create(data)
        self.session.commit()
        return reminder_translator.to_response(reminder)

    def list(self, user: str = None, status: str = None, rfq_id=None) -> dict:
        reminders = self.ds.list(user=user, status=status, rfq_id=rfq_id)
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

    def test_email(self):
        """V1: log-only. Real email integration comes with rfq_communication_ms."""
        logger.info("TEST EMAIL: Would send test reminder email to current user")
        return {"message": "Test email logged (V1 — no actual send)"}

    def process_reminders(self):
        """Invoke the pure batch processing logic."""
        from src.services.notification_service import NotificationService
        svc = NotificationService(self.session)
        result = svc.process_due_reminders()
        return {"message": "Batch processing complete", "data": result}

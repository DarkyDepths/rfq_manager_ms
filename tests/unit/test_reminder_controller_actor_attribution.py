from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.controllers.reminder_controller import ReminderController
from src.translators.reminder_translator import ReminderCreateRequest


class _MockReminderDatasource:
    def __init__(self):
        self.last_create_data = None

    def create(self, data: dict):
        self.last_create_data = dict(data)
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=uuid4(),
            rfq_id=data["rfq_id"],
            rfq_stage_id=data.get("rfq_stage_id"),
            type=data["type"],
            message=data["message"],
            due_date=data["due_date"],
            assigned_to=data.get("assigned_to"),
            status="open",
            created_by=data.get("created_by"),
            created_at=now,
            updated_at=now,
            last_sent_at=None,
            send_count=0,
        )


class _MockSession:
    def commit(self):
        return None


def test_reminder_create_enriches_created_by_from_actor():
    datasource = _MockReminderDatasource()
    controller = ReminderController(datasource=datasource, session=_MockSession())

    request = ReminderCreateRequest(
        rfq_id=uuid4(),
        type="internal",
        message="Actor-attributed reminder",
        due_date=date.today(),
        assigned_to="Engineering",
    )

    response = controller.create(request, created_by="Auth User")

    assert datasource.last_create_data is not None
    assert datasource.last_create_data["created_by"] == "Auth User"
    assert response.created_by == "Auth User"

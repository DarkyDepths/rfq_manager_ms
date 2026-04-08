from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.translators.reminder_translator import (
    REMINDER_SOURCE_AUTOMATIC,
    REMINDER_STATUS_OVERDUE,
    to_response,
)


def test_to_response_includes_updated_at_field():
    now = datetime.now(timezone.utc)
    reminder = SimpleNamespace(
        id=uuid4(),
        rfq_id=uuid4(),
        rfq_stage_id=None,
        type="internal",
        message="Follow up",
        due_date=date.today(),
        assigned_to="Engineering",
        status="open",
        created_by="System",
        created_at=now,
        updated_at=now,
        last_sent_at=None,
        send_count=0,
    )

    response = to_response(reminder)

    assert response.updated_at == now
    assert "updated_at" in response.model_dump()


def test_to_response_normalizes_legacy_sent_status_and_preserves_source():
    now = datetime.now(timezone.utc)
    reminder = SimpleNamespace(
        id=uuid4(),
        rfq_id=uuid4(),
        rfq_stage_id=None,
        type="internal",
        message="Follow up",
        due_date=date.today() - timedelta(days=2),
        assigned_to="Engineering",
        status="sent",
        source=REMINDER_SOURCE_AUTOMATIC,
        created_by="System",
        created_at=now,
        updated_at=now,
        last_sent_at=now,
        send_count=1,
    )

    response = to_response(reminder)

    assert response.status == REMINDER_STATUS_OVERDUE
    assert response.source == REMINDER_SOURCE_AUTOMATIC

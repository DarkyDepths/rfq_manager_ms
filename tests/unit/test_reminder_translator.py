from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.translators.reminder_translator import to_response


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

import pytest
import time
import uuid
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.models.workflow  # noqa: F401
import src.models.rfq  # noqa: F401
import src.models.rfq_stage  # noqa: F401
from src.services.notification_service import NotificationService
from src.models.reminder import Reminder
from src.models.workflow import Workflow
from src.models.rfq import RFQ
from src.database import Base

class MockSession:
    def __init__(self, items):
        self.items = items
        self.committed = False

    def query(self, model): return self
    def filter(self, condition): return self
    def all(self): return self.items
    def commit(self): self.committed = True

def test_process_due_reminders():
    # Due today, 0 sends -> Should stay open, get sent
    r1 = Reminder(status="open", due_date=date.today(), message="Test 1", assigned_to="User 1", send_count=0, type="internal")
    
    # Past due, 2 sends -> Should be overdue, get sent
    r2 = Reminder(status="open", due_date=date.today() - timedelta(days=5), message="Test 2", assigned_to="User 2", send_count=2, type="external")
    
    session = MockSession([r1, r2])
    svc = NotificationService(session)
    
    res = svc.process_due_reminders(max_sends=3)
    
    assert res["processed_count"] == 2
    
    # Check r1
    assert r1.send_count == 1
    assert r1.status == "open"
    assert isinstance(r1.last_sent_at, datetime)
    
    # Check r2
    assert r2.send_count == 3
    assert r2.status == "overdue"
    assert isinstance(r2.last_sent_at, datetime)
    
    assert session.committed is True

def test_process_due_reminders_rate_limiting_and_exhaustion():
    # Past due, but sent today -> Rate limited, no new send, but status updates to overdue
    r1 = Reminder(status="open", due_date=date.today() - timedelta(days=2), message="Test 1", assigned_to="U1", send_count=1, type="internal", last_sent_at=datetime.now())
    
    # Due today, but max_sends reached -> Exhausted, no new send, status stays open
    r2 = Reminder(status="open", due_date=date.today(), message="Test 2", assigned_to="U2", send_count=3, type="internal")
    
    session = MockSession([r1, r2])
    svc = NotificationService(session)
    res = svc.process_due_reminders(max_sends=3)
    
    assert res["processed_count"] == 0
    assert r1.send_count == 1
    assert r1.status == "overdue"
    
    assert r2.send_count == 3
    assert r2.status == "open"


def test_reminder_updated_at_populated_and_changes_on_update():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        workflow = Workflow(
            id=uuid.uuid4(),
            name="Test Workflow",
            code="TEST-WF-1",
            is_active=True,
            is_default=False,
        )
        session.add(workflow)
        session.flush()

        rfq = RFQ(
            id=uuid.uuid4(),
            name="RFQ A",
            client="Client A",
            priority="normal",
            deadline=date.today(),
            owner="Team A",
            workflow_id=workflow.id,
            status="In preparation",
            progress=0,
        )
        session.add(rfq)
        session.flush()

        reminder = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Follow up",
            due_date=date.today(),
            status="open",
            send_count=0,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        first_updated_at = reminder.updated_at
        assert first_updated_at is not None

        time.sleep(1.05)
        reminder.status = "overdue"
        session.commit()
        session.refresh(reminder)

        assert reminder.updated_at is not None
        assert reminder.updated_at > first_updated_at
    finally:
        session.close()

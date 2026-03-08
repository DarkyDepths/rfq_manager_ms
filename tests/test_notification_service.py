import pytest
from datetime import date, datetime, timedelta
from src.services.notification_service import NotificationService
from src.models.reminder import Reminder

class MockSession:
    def __init__(self, items):
        self.items = items
        self.committed = False

    def query(self, model): return self
    def filter(self, condition): return self
    def all(self): return self.items
    def commit(self): self.committed = True

def test_process_due_reminders():
    # Make a reminder that is due today
    r1 = Reminder(status="open", due_date=date.today(), message="Test 1", assigned_to="User 1", send_count=0, type="internal")
    # Make a reminder that is overdue and will max out
    r2 = Reminder(status="overdue", due_date=date.today() - timedelta(days=5), message="Test 2", assigned_to="User 2", send_count=2, type="external")
    
    session = MockSession([r1, r2])
    svc = NotificationService(session)
    
    res = svc.process_due_reminders(max_sends=3)
    
    assert res["processed_count"] == 2
    assert res["completed_count"] == 1 # r2 reached 3 sends
    
    # Check r1
    assert r1.send_count == 1
    assert r1.status == "overdue" # properly transitioned
    assert isinstance(r1.last_sent_at, datetime)
    
    # Check r2
    assert r2.send_count == 3
    assert r2.status == "sent" # reached terminal state
    assert isinstance(r2.last_sent_at, datetime)
    
    assert session.committed is True

"""
Notification service — handles batch processing of reminders.
"""
from datetime import date, datetime
import logging
from sqlalchemy.orm import Session
from src.models.reminder import Reminder

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, session: Session):
        self.session = session

    def process_due_reminders(self, max_sends: int = 3) -> dict:
        """
        Pure, testable function to process due reminders.
        Finds open/overdue reminders due on or before today.
        """
        today = date.today()
        now = datetime.now()

        due_reminders = (
            self.session.query(Reminder)
            .filter(Reminder.status.in_(["open", "overdue"]))
            .filter(Reminder.due_date <= today)
            .all()
        )

        processed = 0

        for reminder in due_reminders:
            # 1. Update lifecycle state based purely on date, regardless of sending
            if reminder.due_date < today:
                reminder.status = "overdue"
            else:
                reminder.status = "open"

            # 2. Execution gates: max exhaustion and daily rate limit
            if reminder.send_count >= max_sends:
                continue

            if reminder.last_sent_at and reminder.last_sent_at.date() == today:
                continue

            # 3. Mock sending logic
            recipient = reminder.assigned_to or "Unassigned"
            logger.info(f"Sending reminder [{reminder.type}]: '{reminder.message}' to {recipient}")

            # 4. Update execution state
            reminder.last_sent_at = now
            reminder.send_count += 1
            processed += 1

        self.session.commit()
        return {"processed_count": processed}

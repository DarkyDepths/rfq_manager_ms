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
        completed = 0

        for reminder in due_reminders:
            # 1. Mock sending logic
            recipient = reminder.assigned_to or "Unassigned"
            logger.info(f"Sending reminder [{reminder.type}]: '{reminder.message}' to {recipient}")

            # 2. Update execution state
            reminder.last_sent_at = now
            reminder.send_count += 1
            processed += 1

            # 3. Exhaustion check
            if reminder.send_count >= max_sends:
                reminder.status = "sent"  # terminal state
                completed += 1
            else:
                reminder.status = "overdue"

        self.session.commit()
        return {"processed_count": processed, "completed_count": completed}

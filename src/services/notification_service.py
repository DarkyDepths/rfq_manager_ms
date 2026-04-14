"""
Notification service — handles batch processing of reminders.
"""
from datetime import date, datetime, timedelta
import logging
from sqlalchemy.orm import Session
from src.models.reminder import Reminder, ReminderRule
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.translators.reminder_translator import (
    ACTIVE_REMINDER_STATUSES,
    REMINDER_SOURCE_AUTOMATIC,
    REMINDER_STATUS_OPEN,
    REMINDER_STATUS_RESOLVED,
    normalize_reminder_status,
)
from src.utils.rfq_status import RFQ_ACTIVE_STATUSES

logger = logging.getLogger(__name__)


AUTO_REMINDER_WINDOW_DAYS = 1
SUPPORTED_RULE_SCOPES = frozenset({"all_rfqs", "critical_only", "stage_overdue"})


class NotificationService:
    def __init__(self, session: Session):
        self.session = session

    def process_due_reminders(self, max_sends: int = 3) -> dict:
        """
        Pure, testable function to process due reminders.
        Finds open/overdue reminders due on or before today.

        Note: Execution relies on a daily rate-limit gate. To change the
        cadence (e.g., hourly), adjust the `last_sent_at` check.
        Note: Exhausted reminders (send_count >= max_sends) are deliberately
        left active (open/overdue) until the user officially Resolves them.
        'sent' is not forced as a terminal business state, avoiding confusion
        with actual task resolution.
        """
        today = date.today()
        now = datetime.now()
        reconciliation = self._reconcile_automatic_reminders(today)

        due_reminders = (
            self.session.query(Reminder)
            .filter(Reminder.status.in_(tuple(ACTIVE_REMINDER_STATUSES)))
            .filter(Reminder.due_date <= today)
            .all()
        )

        processed = 0
        skipped_max_attempts = 0
        skipped_rate_limited = 0

        for reminder in due_reminders:
            # 1. Update lifecycle state based purely on date, regardless of sending
            reminder.status = normalize_reminder_status(reminder.status, reminder.due_date)

            # 2. Execution gates: max exhaustion and daily rate limit
            #    If attempts are exhausted, we simply skip sending. We do NOT mark
            #    as 'sent' or 'resolved' since true resolution is a business action.
            if reminder.send_count >= max_sends:
                skipped_max_attempts += 1
                continue

            #    Daily cadence block: prevents spamming if processed multiple times a day
            if reminder.last_sent_at and reminder.last_sent_at.date() == today:
                skipped_rate_limited += 1
                continue

            # 3. Mock sending logic
            recipient = reminder.assigned_to or "Unassigned"
            logger.info(f"Sending reminder [{reminder.type}]: '{reminder.message}' to {recipient}")

            # 4. Update execution state
            reminder.last_sent_at = now
            reminder.send_count += 1
            processed += 1

        self.session.commit()
        if processed == 0:
            message = (
                "0 reminders sent "
                f"(due={len(due_reminders)}, max-attempt-skips={skipped_max_attempts}, "
                f"rate-limit-skips={skipped_rate_limited})"
            )
        else:
            message = (
                f"Processed {processed} reminder(s) "
                f"(due={len(due_reminders)}, max-attempt-skips={skipped_max_attempts}, "
                f"rate-limit-skips={skipped_rate_limited})"
            )
            
        return {
            "generated_count": reconciliation["generated_count"],
            "due_count": len(due_reminders),
            "processed_count": processed,
            "resolved_count": reconciliation["resolved_count"],
            "skipped_max_attempts_count": skipped_max_attempts,
            "skipped_rate_limited_count": skipped_rate_limited,
            "message": message,
            "skipped_rule_count": reconciliation["skipped_rule_count"],
        }

    def _reconcile_automatic_reminders(self, today: date) -> dict:
        generated = 0
        resolved = 0
        skipped_rule_count = 0

        rules = self.session.query(ReminderRule).all()
        for rule in rules:
            active_reminders = (
                self.session.query(Reminder)
                .filter(
                    Reminder.source == REMINDER_SOURCE_AUTOMATIC,
                    Reminder.reminder_rule_id == rule.id,
                    Reminder.status != REMINDER_STATUS_RESOLVED,
                )
                .all()
            )

            if not rule.is_active:
                for reminder in active_reminders:
                    reminder.status = REMINDER_STATUS_RESOLVED
                    resolved += 1
                continue

            contexts = self._build_contexts_for_rule(rule, today)
            if contexts is None:
                skipped_rule_count += 1
                continue

            existing_by_context = {
                (str(reminder.rfq_id), str(reminder.rfq_stage_id) if reminder.rfq_stage_id else None): reminder
                for reminder in active_reminders
            }
            desired_context_keys: set[tuple[str, str | None]] = set()

            for context in contexts:
                context_key = (
                    str(context["rfq_id"]),
                    str(context["rfq_stage_id"]) if context["rfq_stage_id"] else None,
                )
                desired_context_keys.add(context_key)
                reminder = existing_by_context.get(context_key)
                expected_status = normalize_reminder_status(REMINDER_STATUS_OPEN, context["due_date"])

                if reminder is None:
                    self.session.add(
                        Reminder(
                            rfq_id=context["rfq_id"],
                            rfq_stage_id=context["rfq_stage_id"],
                            reminder_rule_id=rule.id,
                            type=context["type"],
                            message=context["message"],
                            due_date=context["due_date"],
                            assigned_to=context["assigned_to"],
                            status=expected_status,
                            source=REMINDER_SOURCE_AUTOMATIC,
                            created_by=f"Auto rule: {rule.name}",
                            send_count=0,
                        )
                    )
                    generated += 1
                    continue

                reminder.type = context["type"]
                reminder.message = context["message"]
                reminder.due_date = context["due_date"]
                reminder.assigned_to = context["assigned_to"]
                reminder.status = expected_status

            for context_key, reminder in existing_by_context.items():
                if context_key not in desired_context_keys:
                    reminder.status = REMINDER_STATUS_RESOLVED
                    resolved += 1

        return {
            "generated_count": generated,
            "resolved_count": resolved,
            "skipped_rule_count": skipped_rule_count,
        }

    def _build_contexts_for_rule(self, rule: ReminderRule, today: date):
        if rule.scope not in SUPPORTED_RULE_SCOPES:
            return None

        if rule.scope == "all_rfqs":
            return self._build_due_soon_rfq_contexts(today)
        if rule.scope == "critical_only":
            return self._build_due_soon_rfq_contexts(today, critical_only=True)
        if rule.scope == "stage_overdue":
            return self._build_stage_overdue_contexts(today)

        return None

    def _build_due_soon_rfq_contexts(self, today: date, critical_only: bool = False) -> list[dict]:
        threshold = today + timedelta(days=AUTO_REMINDER_WINDOW_DAYS)
        query = self.session.query(RFQ).filter(
            RFQ.status.in_(RFQ_ACTIVE_STATUSES),
            RFQ.deadline <= threshold,
        )
        if critical_only:
            query = query.filter(RFQ.priority == "critical")

        contexts = []
        for rfq in query.all():
            contexts.append(
                {
                    "rfq_id": rfq.id,
                    "rfq_stage_id": None,
                    "type": "internal",
                    "message": (
                        "Critical RFQ requires follow-up before deadline."
                        if critical_only
                        else "RFQ deadline is approaching and needs follow-up."
                    ),
                    "due_date": rfq.deadline,
                    "assigned_to": rfq.owner,
                }
            )
        return contexts

    def _build_stage_overdue_contexts(self, today: date) -> list[dict]:
        stages = (
            self.session.query(RFQStage, RFQ)
            .join(RFQ, RFQ.id == RFQStage.rfq_id)
            .filter(
                RFQ.status.in_(RFQ_ACTIVE_STATUSES),
                RFQ.current_stage_id == RFQStage.id,
                RFQStage.status == "In Progress",
                RFQStage.planned_end.isnot(None),
                RFQStage.planned_end < today,
            )
            .all()
        )

        contexts = []
        for stage, rfq in stages:
            contexts.append(
                {
                    "rfq_id": rfq.id,
                    "rfq_stage_id": stage.id,
                    "type": "internal",
                    "message": f"Stage '{stage.name}' is overdue and needs follow-up.",
                    "due_date": stage.planned_end,
                    "assigned_to": stage.assigned_team or rfq.owner,
                }
            )
        return contexts

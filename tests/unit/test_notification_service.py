import time
import uuid
from datetime import date, datetime, timedelta

import src.models.reminder  # noqa: F401
import src.models.rfq  # noqa: F401
import src.models.rfq_stage  # noqa: F401
import src.models.workflow  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.reminder import Reminder, ReminderRule
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow
from src.services.notification_service import NotificationService
from src.translators.reminder_translator import (
    REMINDER_SOURCE_AUTOMATIC,
    REMINDER_SOURCE_MANUAL,
    REMINDER_STATUS_OPEN,
    REMINDER_STATUS_OVERDUE,
    REMINDER_STATUS_RESOLVED,
)
from src.utils.rfq_status import RFQ_STATUS_CANCELLED, RFQ_STATUS_IN_PREPARATION


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _seed_workflow(session):
    workflow = Workflow(
        id=uuid.uuid4(),
        name="Reminder Workflow",
        code=f"REM-WF-{uuid.uuid4().hex[:6]}",
        is_active=True,
        is_default=False,
    )
    session.add(workflow)
    session.flush()
    return workflow


def _seed_rfq(
    session,
    workflow_id,
    *,
    deadline,
    owner="Estimation Manager",
    priority="normal",
    status=RFQ_STATUS_IN_PREPARATION,
):
    rfq = RFQ(
        id=uuid.uuid4(),
        name="Reminder RFQ",
        client="Client A",
        priority=priority,
        deadline=deadline,
        owner=owner,
        workflow_id=workflow_id,
        status=status,
        progress=20,
    )
    session.add(rfq)
    session.flush()
    return rfq


def _seed_stage(
    session,
    rfq_id,
    *,
    name="Preliminary design",
    order=1,
    assigned_team="Engineering",
    status="In Progress",
    planned_start=None,
    planned_end=None,
):
    stage = RFQStage(
        id=uuid.uuid4(),
        rfq_id=rfq_id,
        name=name,
        order=order,
        assigned_team=assigned_team,
        status=status,
        progress=40,
        planned_start=planned_start,
        planned_end=planned_end,
    )
    session.add(stage)
    session.flush()
    return stage


def _seed_rule(session, *, scope, is_active=True, name=None):
    rule = ReminderRule(
        id=uuid.uuid4(),
        name=name or scope,
        description=f"Rule for {scope}",
        scope=scope,
        is_active=is_active,
    )
    session.add(rule)
    session.flush()
    return rule


def test_process_due_reminders_updates_business_status_and_send_trace():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, deadline=date.today() + timedelta(days=5))

        due_today = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Due today",
            due_date=date.today(),
            assigned_to="User 1",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=0,
        )
        overdue = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="external",
            message="Past due",
            due_date=date.today() - timedelta(days=5),
            assigned_to="User 2",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=2,
        )
        session.add_all([due_today, overdue])
        session.commit()

        result = NotificationService(session).process_due_reminders(max_sends=3)

        session.refresh(due_today)
        session.refresh(overdue)

        assert result["generated_count"] == 0
        assert result["due_count"] == 2
        assert result["resolved_count"] == 0
        assert result["processed_count"] == 2
        assert result["skipped_max_attempts_count"] == 0
        assert result["skipped_rate_limited_count"] == 0
        assert due_today.status == REMINDER_STATUS_OPEN
        assert due_today.send_count == 1
        assert isinstance(due_today.last_sent_at, datetime)
        assert overdue.status == REMINDER_STATUS_OVERDUE
        assert overdue.send_count == 3
        assert isinstance(overdue.last_sent_at, datetime)
    finally:
        session.close()


def test_process_due_reminders_respects_daily_rate_limit_and_max_attempts():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, deadline=date.today() + timedelta(days=5))

        already_sent_today = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Already sent today",
            due_date=date.today() - timedelta(days=2),
            assigned_to="User 1",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=1,
            last_sent_at=datetime.now(),
        )
        exhausted = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Exhausted attempts",
            due_date=date.today(),
            assigned_to="User 2",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=3,
        )
        session.add_all([already_sent_today, exhausted])
        session.commit()

        result = NotificationService(session).process_due_reminders(max_sends=3)

        session.refresh(already_sent_today)
        session.refresh(exhausted)

        assert result["due_count"] == 2
        assert result["processed_count"] == 0
        assert result["skipped_max_attempts_count"] == 1
        assert result["skipped_rate_limited_count"] == 1
        assert already_sent_today.status == REMINDER_STATUS_OVERDUE
        assert already_sent_today.send_count == 1
        assert exhausted.status == REMINDER_STATUS_OPEN
        assert exhausted.send_count == 3
    finally:
        session.close()


def test_process_due_reminders_exposes_truthful_skip_breakdown_in_message():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, deadline=date.today() + timedelta(days=2))

        already_sent_today = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Already sent today",
            due_date=date.today(),
            assigned_to="User 1",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=1,
            last_sent_at=datetime.now(),
        )
        exhausted = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Exhausted attempts",
            due_date=date.today() - timedelta(days=1),
            assigned_to="User 2",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=3,
        )
        session.add_all([already_sent_today, exhausted])
        session.commit()

        result = NotificationService(session).process_due_reminders(max_sends=3)

        assert "due=2" in result["message"]
        assert "max-attempt-skips=1" in result["message"]
        assert "rate-limit-skips=1" in result["message"]
    finally:
        session.close()


def test_batch_auto_generates_and_deduplicates_due_soon_rfq_reminders():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(
            session,
            workflow.id,
            deadline=date.today() + timedelta(days=1),
            owner="Owner A",
        )
        rule = _seed_rule(session, scope="all_rfqs", name="Upcoming deadline")
        session.commit()

        first_result = NotificationService(session).process_due_reminders()
        reminders = (
            session.query(Reminder)
            .filter(Reminder.reminder_rule_id == rule.id)
            .all()
        )

        assert first_result["generated_count"] == 1
        assert len(reminders) == 1
        assert reminders[0].rfq_id == rfq.id
        assert reminders[0].rfq_stage_id is None
        assert reminders[0].assigned_to == "Owner A"
        assert reminders[0].source == REMINDER_SOURCE_AUTOMATIC
        assert reminders[0].status == REMINDER_STATUS_OPEN

        second_result = NotificationService(session).process_due_reminders()
        active_reminders = (
            session.query(Reminder)
            .filter(
                Reminder.reminder_rule_id == rule.id,
                Reminder.status != REMINDER_STATUS_RESOLVED,
            )
            .all()
        )

        assert second_result["generated_count"] == 0
        assert len(active_reminders) == 1
    finally:
        session.close()


def test_batch_auto_resolves_automatic_reminder_when_condition_disappears():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(
            session,
            workflow.id,
            deadline=date.today() + timedelta(days=1),
            owner="Owner A",
        )
        rule = _seed_rule(session, scope="all_rfqs", name="Upcoming deadline")
        session.commit()

        NotificationService(session).process_due_reminders()
        reminder = (
            session.query(Reminder)
            .filter(Reminder.reminder_rule_id == rule.id)
            .one()
        )
        assert reminder.status == REMINDER_STATUS_OPEN

        rfq.status = RFQ_STATUS_CANCELLED
        session.commit()

        result = NotificationService(session).process_due_reminders()
        session.refresh(reminder)

        assert result["resolved_count"] == 1
        assert reminder.status == REMINDER_STATUS_RESOLVED
    finally:
        session.close()


def test_batch_generates_stage_overdue_reminder_for_current_stage():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(
            session,
            workflow.id,
            deadline=date.today() + timedelta(days=10),
            owner="Owner A",
        )
        stage = _seed_stage(
            session,
            rfq.id,
            assigned_team="Engineering",
            planned_start=date.today() - timedelta(days=4),
            planned_end=date.today() - timedelta(days=1),
        )
        rfq.current_stage_id = stage.id
        _seed_rule(session, scope="stage_overdue", name="Stage overdue")
        session.commit()

        result = NotificationService(session).process_due_reminders()
        reminder = session.query(Reminder).filter(Reminder.rfq_stage_id == stage.id).one()

        assert result["generated_count"] == 1
        assert reminder.rfq_id == rfq.id
        assert reminder.rfq_stage_id == stage.id
        assert reminder.assigned_to == "Engineering"
        assert reminder.source == REMINDER_SOURCE_AUTOMATIC
        assert reminder.status == REMINDER_STATUS_OVERDUE
    finally:
        session.close()


def test_reminder_updated_at_populated_and_changes_on_update():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, deadline=date.today())

        reminder = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Follow up",
            due_date=date.today(),
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            send_count=0,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        first_updated_at = reminder.updated_at
        assert first_updated_at is not None

        time.sleep(1.05)
        reminder.status = REMINDER_STATUS_OVERDUE
        session.commit()
        session.refresh(reminder)

        assert reminder.updated_at is not None
        assert reminder.updated_at > first_updated_at
    finally:
        session.close()

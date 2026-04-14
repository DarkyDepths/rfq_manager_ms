import uuid
from datetime import date, timedelta

import src.models.reminder  # noqa: F401
import src.models.rfq  # noqa: F401
import src.models.rfq_stage  # noqa: F401
import src.models.workflow  # noqa: F401
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.controllers.reminder_controller import ReminderController
from src.database import Base
from src.datasources.reminder_datasource import ReminderDatasource
from src.models.reminder import Reminder
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow
from src.translators.reminder_translator import (
    REMINDER_SOURCE_AUTOMATIC,
    REMINDER_SOURCE_MANUAL,
    REMINDER_STATUS_OPEN,
    REMINDER_STATUS_RESOLVED,
    ReminderCreateRequest,
)
from src.utils.errors import ConflictError, UnprocessableEntityError
from src.utils.rfq_status import RFQ_STATUS_IN_PREPARATION


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


def _seed_rfq(session, workflow_id, *, owner="Estimation Manager"):
    rfq = RFQ(
        id=uuid.uuid4(),
        name="Reminder RFQ",
        client="Client A",
        priority="normal",
        deadline=date.today() + timedelta(days=7),
        owner=owner,
        workflow_id=workflow_id,
        status=RFQ_STATUS_IN_PREPARATION,
        progress=10,
    )
    session.add(rfq)
    session.flush()
    return rfq


def _seed_stage(session, rfq_id, *, assigned_team="Engineering"):
    stage = RFQStage(
        id=uuid.uuid4(),
        rfq_id=rfq_id,
        name="Preliminary design",
        order=1,
        assigned_team=assigned_team,
        status="In Progress",
        progress=40,
        planned_start=date.today(),
        planned_end=date.today() + timedelta(days=2),
    )
    session.add(stage)
    session.flush()
    return stage


def test_reminder_create_enriches_created_by_from_actor():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            type="internal",
            message="Actor-attributed reminder",
            due_date=date.today(),
            assigned_to="Engineering",
        )

        response = controller.create(request, created_by="Auth User")

        stored = session.query(Reminder).filter(Reminder.id == response.id).one()
        assert response.created_by == "Auth User"
        assert stored.created_by == "Auth User"
        assert stored.source == REMINDER_SOURCE_MANUAL
        assert stored.status == REMINDER_STATUS_OPEN
    finally:
        session.close()


def test_reminder_create_defaults_rfq_level_owner_when_assignee_missing():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, owner="Owner A")
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            type="internal",
            message="Owner follow-up",
            due_date=date.today(),
        )

        response = controller.create(request, created_by="Auth User")

        assert response.assigned_to == "Owner A"
        stored = session.query(Reminder).filter(Reminder.id == response.id).one()
        assert stored.rfq_stage_id is None
    finally:
        session.close()


def test_reminder_create_defaults_stage_team_when_stage_linked():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id, owner="Owner A")
        stage = _seed_stage(session, rfq.id, assigned_team="Engineering")
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            rfq_stage_id=stage.id,
            type="internal",
            message="Stage follow-up",
            due_date=date.today(),
        )

        response = controller.create(request, created_by="Auth User")

        assert response.rfq_stage_id == stage.id
        assert response.assigned_to == "Engineering"
    finally:
        session.close()


def test_reminder_create_rejects_stage_rfq_mismatch():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq_one = _seed_rfq(session, workflow.id, owner="Owner A")
        rfq_two = _seed_rfq(session, workflow.id, owner="Owner B")
        stage_two = _seed_stage(session, rfq_two.id, assigned_team="Engineering")
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq_one.id,
            rfq_stage_id=stage_two.id,
            type="internal",
            message="Invalid cross-link",
            due_date=date.today(),
        )

        with pytest.raises(UnprocessableEntityError) as excinfo:
            controller.create(request, created_by="Auth User")

        assert "same RFQ" in excinfo.value.message
    finally:
        session.close()


def test_reminder_create_rejects_due_date_in_the_past():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            type="internal",
            message="Past reminder",
            due_date=date.today() - timedelta(days=1),
        )

        with pytest.raises(UnprocessableEntityError) as excinfo:
            controller.create(request, created_by="Auth User")

        assert "cannot be in the past" in excinfo.value.message
    finally:
        session.close()


def test_reminder_create_rejects_rfq_due_date_after_deadline():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        controller = ReminderController(ReminderDatasource(session), session)

        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            type="internal",
            message="Too late for RFQ",
            due_date=rfq.deadline + timedelta(days=1),
        )

        with pytest.raises(UnprocessableEntityError) as excinfo:
            controller.create(request, created_by="Auth User")

        assert "RFQ-level reminder due date must fall between today and the RFQ deadline." == excinfo.value.message
    finally:
        session.close()


def test_stage_linked_reminder_rejects_due_date_outside_dynamic_stage_window():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        stage = _seed_stage(
            session,
            rfq.id,
            assigned_team="Engineering",
        )
        stage.actual_start = date.today() + timedelta(days=3)
        stage.planned_start = date.today()
        stage.planned_end = date.today() + timedelta(days=2)
        session.commit()

        controller = ReminderController(ReminderDatasource(session), session)
        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            rfq_stage_id=stage.id,
            type="internal",
            message="Outside shifted window",
            due_date=date.today() + timedelta(days=1),
        )

        with pytest.raises(UnprocessableEntityError) as excinfo:
            controller.create(request, created_by="Auth User")

        assert "Stage-linked reminder due date must fall within the current stage window." == excinfo.value.message
    finally:
        session.close()


def test_stage_linked_reminder_rejects_due_date_when_stage_schedule_incomplete():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        stage = _seed_stage(session, rfq.id, assigned_team="Engineering")
        stage.planned_start = None
        stage.planned_end = None
        session.commit()

        controller = ReminderController(ReminderDatasource(session), session)
        request = ReminderCreateRequest(
            rfq_id=rfq.id,
            rfq_stage_id=stage.id,
            type="internal",
            message="Incomplete schedule",
            due_date=date.today() + timedelta(days=1),
        )

        with pytest.raises(UnprocessableEntityError) as excinfo:
            controller.create(request, created_by="Auth User")

        assert (
            "Stage-linked reminder due date cannot be set because the current stage schedule is incomplete."
            == excinfo.value.message
        )
    finally:
        session.close()


def test_reminder_resolve_marks_business_state_resolved():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        reminder = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Resolve me",
            due_date=date.today(),
            assigned_to="Engineering",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_MANUAL,
            created_by="Auth User",
            send_count=0,
        )
        session.add(reminder)
        session.commit()

        controller = ReminderController(ReminderDatasource(session), session)
        response = controller.resolve(reminder.id)

        session.refresh(reminder)
        assert response.status == REMINDER_STATUS_RESOLVED
        assert reminder.status == REMINDER_STATUS_RESOLVED
    finally:
        session.close()


def test_automatic_reminder_cannot_be_resolved_manually():
    session = _make_session()
    try:
        workflow = _seed_workflow(session)
        rfq = _seed_rfq(session, workflow.id)
        reminder = Reminder(
            id=uuid.uuid4(),
            rfq_id=rfq.id,
            type="internal",
            message="Auto reminder",
            due_date=date.today(),
            assigned_to="Engineering",
            status=REMINDER_STATUS_OPEN,
            source=REMINDER_SOURCE_AUTOMATIC,
            created_by="Auto rule: all_rfqs",
            send_count=0,
        )
        session.add(reminder)
        session.commit()

        controller = ReminderController(ReminderDatasource(session), session)

        with pytest.raises(ConflictError) as excinfo:
            controller.resolve(reminder.id)

        assert "resolved by batch" in excinfo.value.message
        session.refresh(reminder)
        assert reminder.status == REMINDER_STATUS_OPEN
    finally:
        session.close()


def test_test_email_response_is_explicitly_log_only_and_actor_scoped():
    session = _make_session()
    try:
        controller = ReminderController(ReminderDatasource(session), session)

        response = controller.test_email(actor_name="Ops Reviewer")

        assert response["message"] == (
            "Test reminder delivery is log-only in V1; no email was sent to Ops Reviewer."
        )
    finally:
        session.close()

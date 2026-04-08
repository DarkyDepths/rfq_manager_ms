import uuid
from datetime import date, datetime

import pytest

from src.controllers.subtask_controller import (
    SUBTASK_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE,
    SUBTASK_DUE_DATE_WINDOW_MESSAGE,
    SUBTASK_PROGRESS_DECREASE_MESSAGE,
    SubtaskController,
)
from src.models.rfq_stage import RFQStage
from src.models.subtask import Subtask
from src.translators.subtask_translator import (
    SUBTASK_ASSIGNEE_REQUIRED_MESSAGE,
    SUBTASK_DUE_DATE_REQUIRED_MESSAGE,
    SUBTASK_NAME_REQUIRED_MESSAGE,
    SubtaskCreateRequest,
    SubtaskUpdateRequest,
)
from src.utils.errors import ConflictError, NotFoundError, UnprocessableEntityError


RFQ1 = str(uuid.uuid4())
ST1 = str(uuid.uuid4())
S1_ID = str(uuid.uuid4())
S2_ID = str(uuid.uuid4())
PLANNED_START = date(2026, 4, 10)
PLANNED_END = date(2026, 4, 20)


class MockSubtaskDatasource:
    def __init__(self, subtasks=None):
        self.subtasks = subtasks or []
        self.deleted = []

    def create(self, data):
        subtask = Subtask(
            **data,
            id=str(uuid.uuid4()),
            progress=0,
            status="Open",
            created_at=datetime.now(),
        )
        self.subtasks.append(subtask)
        return subtask

    def list_by_stage(self, stage_id):
        return [subtask for subtask in self.subtasks if subtask.rfq_stage_id == stage_id]

    def get_by_id(self, subtask_id):
        for subtask in self.subtasks:
            if subtask.id == subtask_id:
                return subtask
        for subtask in self.deleted:
            if subtask.id == subtask_id:
                return subtask
        return None

    def update(self, subtask, update_data):
        for key, value in update_data.items():
            setattr(subtask, key, value)
        return subtask

    def soft_delete(self, subtask):
        self.subtasks = [current for current in self.subtasks if current.id != subtask.id]
        self.deleted.append(subtask)


class MockStageDatasource:
    def __init__(self, stages=None):
        self.stages = stages or []

    def get_by_id(self, stage_id):
        return next((stage for stage in self.stages if stage.id == stage_id), None)


class MockSession:
    def __init__(self):
        self.commit_count = 0
        self.flush_count = 0

    def commit(self):
        self.commit_count += 1

    def flush(self):
        self.flush_count += 1


def build_stage(**overrides):
    return RFQStage(
        id=overrides.pop("id", ST1),
        rfq_id=overrides.pop("rfq_id", RFQ1),
        planned_start=overrides.pop("planned_start", PLANNED_START),
        planned_end=overrides.pop("planned_end", PLANNED_END),
        progress=overrides.pop("progress", 0),
        status=overrides.pop("status", "In Progress"),
        **overrides,
    )


def build_subtask(**overrides):
    return Subtask(
        id=overrides.pop("id", S1_ID),
        rfq_stage_id=overrides.pop("rfq_stage_id", ST1),
        name=overrides.pop("name", "Task 1"),
        assigned_to=overrides.pop("assigned_to", None),
        due_date=overrides.pop("due_date", None),
        progress=overrides.pop("progress", 0),
        status=overrides.pop("status", "Open"),
        created_at=overrides.pop("created_at", datetime.now()),
        **overrides,
    )


def build_controller(stage=None, subtasks=None):
    session = MockSession()
    controller = SubtaskController(
        datasource=MockSubtaskDatasource(subtasks),
        stage_datasource=MockStageDatasource([stage or build_stage()]),
        session=session,
    )
    return controller, session


def test_subtask_create_succeeds_with_valid_due_date_inside_stage_window():
    controller, session = build_controller()

    result = controller.create(
        RFQ1,
        ST1,
        SubtaskCreateRequest(
            name="Task 1",
            assigned_to="User 1",
            due_date=date(2026, 4, 15),
        ),
    )

    assert result.name == "Task 1"
    assert result.rfq_stage_id == uuid.UUID(ST1)
    assert result.due_date == date(2026, 4, 15)
    assert result.progress == 0
    assert result.status == "Open"
    assert session.commit_count == 1


def test_subtask_create_rejects_due_date_before_stage_window():
    controller, session = build_controller()

    with pytest.raises(UnprocessableEntityError, match=SUBTASK_DUE_DATE_WINDOW_MESSAGE):
        controller.create(
            RFQ1,
            ST1,
            SubtaskCreateRequest(
                name="Task 1",
                assigned_to="User 1",
                due_date=date(2026, 4, 9),
            ),
        )

    assert controller.ds.subtasks == []
    assert session.commit_count == 0


def test_subtask_create_rejects_due_date_when_stage_schedule_is_incomplete():
    controller, session = build_controller(stage=build_stage(planned_start=None, planned_end=PLANNED_END))

    with pytest.raises(
        UnprocessableEntityError,
        match=SUBTASK_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE,
    ):
        controller.create(
            RFQ1,
            ST1,
            SubtaskCreateRequest(
                name="Task 1",
                assigned_to="User 1",
                due_date=date(2026, 4, 15),
            ),
        )

    assert controller.ds.subtasks == []
    assert session.commit_count == 0


def test_subtask_create_uses_shifted_actual_window_after_stage_starts_late():
    controller, session = build_controller(
        stage=build_stage(
            planned_start=PLANNED_START,
            planned_end=PLANNED_END,
            actual_start=date(2026, 4, 15),
        )
    )

    result = controller.create(
        RFQ1,
        ST1,
        SubtaskCreateRequest(
            name="Task 1",
            assigned_to="User 1",
            due_date=date(2026, 4, 24),
        ),
    )

    assert result.due_date == date(2026, 4, 24)
    assert session.commit_count == 1


def test_subtask_create_rejects_due_date_outside_shifted_actual_window():
    controller, session = build_controller(
        stage=build_stage(
            planned_start=PLANNED_START,
            planned_end=PLANNED_END,
            actual_start=date(2026, 4, 15),
        )
    )

    with pytest.raises(UnprocessableEntityError, match=SUBTASK_DUE_DATE_WINDOW_MESSAGE):
        controller.create(
            RFQ1,
            ST1,
            SubtaskCreateRequest(
                name="Task 1",
                assigned_to="User 1",
                due_date=date(2026, 4, 26),
            ),
        )

    assert controller.ds.subtasks == []
    assert session.commit_count == 0


def test_subtask_update_uses_actual_window_once_stage_has_actual_end():
    stage = build_stage(
        planned_start=PLANNED_START,
        planned_end=PLANNED_END,
        actual_start=date(2026, 4, 15),
        actual_end=date(2026, 4, 22),
    )
    controller, session = build_controller(
        stage=stage,
        subtasks=[build_subtask(id=S1_ID, due_date=date(2026, 4, 18), progress=20, status="In progress")],
    )

    result = controller.update(
        RFQ1,
        ST1,
        S1_ID,
        SubtaskUpdateRequest(due_date=date(2026, 4, 22), progress=20),
    )

    assert result.due_date == date(2026, 4, 22)
    assert session.commit_count == 1


def test_subtask_create_stage_not_found():
    session = MockSession()
    controller = SubtaskController(
        datasource=MockSubtaskDatasource(),
        stage_datasource=MockStageDatasource([]),
        session=session,
    )

    with pytest.raises(NotFoundError):
        controller.create(
            RFQ1,
            str(uuid.uuid4()),
            SubtaskCreateRequest(
                name="Task 1",
                assigned_to="User 1",
                due_date=date(2026, 4, 15),
            ),
        )


def test_subtask_create_request_rejects_blank_name():
    with pytest.raises(ValueError, match=SUBTASK_NAME_REQUIRED_MESSAGE):
        SubtaskCreateRequest(
            name="   ",
            assigned_to="User 1",
            due_date=date(2026, 4, 15),
        )


def test_subtask_create_request_rejects_missing_assignee():
    with pytest.raises(ValueError, match=SUBTASK_ASSIGNEE_REQUIRED_MESSAGE):
        SubtaskCreateRequest(
            name="Task 1",
            assigned_to="   ",
            due_date=date(2026, 4, 15),
        )


def test_subtask_create_request_rejects_missing_due_date():
    with pytest.raises(ValueError, match=SUBTASK_DUE_DATE_REQUIRED_MESSAGE):
        SubtaskCreateRequest(
            name="Task 1",
            assigned_to="User 1",
        )


def test_subtask_list():
    controller, _ = build_controller(
        subtasks=[
            build_subtask(id=S1_ID, progress=0, status="Open"),
            build_subtask(id=S2_ID, name="Task 2", progress=50, status="Open"),
        ],
    )

    response = controller.list(RFQ1, ST1)

    assert len(response["data"]) == 2


def test_subtask_update_normalizes_progress_100_to_done_and_stage_rolls_to_true_100():
    stage = build_stage(progress=0, status="In Progress")
    controller, session = build_controller(
        stage=stage,
        subtasks=[
            build_subtask(id=S1_ID, progress=100, status="Done"),
            build_subtask(id=S2_ID, name="Task 2", progress=0, status="Open"),
        ],
    )

    result = controller.update(RFQ1, ST1, S2_ID, SubtaskUpdateRequest(progress=100))

    assert result.progress == 100
    assert result.status == "Done"
    assert stage.progress == 100
    assert stage.status == "In Progress"
    assert session.commit_count == 1


def test_subtask_update_normalizes_conflicting_done_status_to_progress_semantics():
    stage = build_stage(progress=25, status="In Progress")
    controller, _ = build_controller(
        stage=stage,
        subtasks=[build_subtask(id=S1_ID, progress=60, status="In progress")],
    )

    result = controller.update(
        RFQ1,
        ST1,
        S1_ID,
        SubtaskUpdateRequest(status="Done", progress=60),
    )

    assert result.status == "In progress"
    assert result.progress == 60
    assert stage.progress == 60


def test_subtask_update_normalizes_partial_progress_to_in_progress():
    stage = build_stage(progress=0, status="In Progress")
    controller, _ = build_controller(
        stage=stage,
        subtasks=[build_subtask(id=S1_ID, progress=0, status="Open")],
    )

    result = controller.update(
        RFQ1,
        ST1,
        S1_ID,
        SubtaskUpdateRequest(progress=30, status="Open"),
    )

    assert result.progress == 30
    assert result.status == "In progress"
    assert stage.progress == 30


def test_subtask_update_normalizes_zero_progress_to_open():
    stage = build_stage(progress=50, status="In Progress")
    controller, _ = build_controller(
        stage=stage,
        subtasks=[build_subtask(id=S1_ID, progress=0, status="In progress")],
    )

    result = controller.update(
        RFQ1,
        ST1,
        S1_ID,
        SubtaskUpdateRequest(status="Done"),
    )

    assert result.progress == 0
    assert result.status == "Open"
    assert stage.progress == 0


def test_subtask_update_rejects_due_date_outside_stage_window_and_persists_nothing():
    original_due_date = date(2026, 4, 15)
    original_name = "Task 1"
    controller, session = build_controller(
        subtasks=[
            build_subtask(
                id=S1_ID,
                name=original_name,
                due_date=original_due_date,
                progress=20,
                status="In progress",
            )
        ],
    )

    with pytest.raises(UnprocessableEntityError, match=SUBTASK_DUE_DATE_WINDOW_MESSAGE):
        controller.update(
            RFQ1,
            ST1,
            S1_ID,
            SubtaskUpdateRequest(name="Changed", due_date=date(2026, 4, 25)),
        )

    subtask = controller.ds.get_by_id(S1_ID)
    assert subtask.name == original_name
    assert subtask.due_date == original_due_date
    assert session.commit_count == 0


def test_subtask_update_rejects_due_date_when_stage_schedule_is_incomplete():
    controller, session = build_controller(
        stage=build_stage(planned_start=PLANNED_START, planned_end=None),
        subtasks=[build_subtask(id=S1_ID, progress=20, status="In progress")],
    )

    with pytest.raises(
        UnprocessableEntityError,
        match=SUBTASK_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE,
    ):
        controller.update(
            RFQ1,
            ST1,
            S1_ID,
            SubtaskUpdateRequest(due_date=date(2026, 4, 18)),
        )

    assert controller.ds.get_by_id(S1_ID).due_date is None
    assert session.commit_count == 0


def test_subtask_update_rejects_backward_progress_and_persists_nothing():
    controller, session = build_controller(
        subtasks=[build_subtask(id=S1_ID, progress=60, status="In progress")],
    )

    with pytest.raises(ConflictError, match=SUBTASK_PROGRESS_DECREASE_MESSAGE):
        controller.update(
            RFQ1,
            ST1,
            S1_ID,
            SubtaskUpdateRequest(progress=40, status="In progress"),
        )

    subtask = controller.ds.get_by_id(S1_ID)
    assert subtask.progress == 60
    assert subtask.status == "In progress"
    assert session.commit_count == 0


def test_subtask_delete_and_rollup_keeps_true_100():
    stage = build_stage(progress=50, status="In Progress")
    controller, session = build_controller(
        stage=stage,
        subtasks=[
            build_subtask(id=S1_ID, progress=100, status="Done"),
            build_subtask(id=S2_ID, name="Task 2", progress=0, status="Open"),
        ],
    )

    controller.delete(RFQ1, ST1, S2_ID)

    assert len(controller.ds.subtasks) == 1
    assert len(controller.ds.deleted) == 1
    assert stage.progress == 100
    assert stage.status == "In Progress"
    assert session.commit_count == 1

import pytest
import uuid
from datetime import date
from datetime import datetime
from datetime import timedelta

from pydantic import ValidationError
from src.controllers.rfq_controller import RfqController
from src.translators.rfq_translator import RfqCancelRequest, RfqCreateRequest, RfqUpdateRequest
from src.utils.errors import BadRequestError, ConflictError
from src.utils.observability import request_id_context

class MockRFQ:
    def __init__(self, rfq_code, name, client, priority, status, progress, deadline, owner, created_at):
        self.rfq_code = rfq_code
        self.name = name
        self.client = client
        self.priority = priority
        self.status = status
        self.progress = progress
        self.deadline = deadline
        self.owner = owner
        self.created_at = created_at

class MockQuery:
    def __init__(self, results):
        self.results = results
    def all(self):
        return self.results

class MockRfqDatasource:
    def __init__(self):
        self.last_kwargs = {}
        
    def list(self, **kwargs):
        self.last_kwargs = kwargs
        # Return a mock query yielding two sample RFQs
        r1 = MockRFQ("IF-001", "Pump Package", "Aramco", "critical", "In preparation", 15, date(2023, 12, 1), "Team A", date(2023, 10, 1))
        r2 = MockRFQ("IF-002", "Valves", "SABIC", "normal", "Awarded", 100, date(2023, 11, 15), "Team B", date(2023, 9, 1))
        return MockQuery([r1, r2])


class MockWorkflow:
    def __init__(self, workflow_id):
        self.id = workflow_id
        self.name = "Workflow A"
        self.stages = []
        self.selection_mode = "fixed"
        self.base_workflow_id = None
        self.base_workflow = None


class MockWorkflowDatasource:
    def get_by_id(self, workflow_id):
        return MockWorkflow(workflow_id)


class MockSession:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        return None

    def flush(self):
        return None

    def query(self, _model):
        class _Query:
            def filter_by(self, **_kwargs):
                return self

            def order_by(self, *_args, **_kwargs):
                return self

            def all(self):
                return []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return None

        return _Query()


class MockRfqForUpdate:
    def __init__(self, status):
        self.id = uuid.uuid4()
        self.rfq_code = "IF-1001"
        self.name = "RFQ A"
        self.client = "Client A"
        self.status = status
        self.progress = 20
        self.deadline = date(2030, 1, 1)
        self.current_stage_id = None
        self.workflow_id = uuid.uuid4()
        self.industry = None
        self.country = None
        self.priority = "normal"
        self.owner = "Team A"
        self.description = None
        self.outcome_reason = None
        self.created_at = date(2026, 1, 1)
        self.updated_at = date(2026, 1, 1)


class MockRfqDatasourceForUpdate:
    def __init__(self, rfq):
        self.rfq = rfq
        self.last_update_data = None

    def get_by_id(self, rfq_id):
        if rfq_id == self.rfq.id:
            return self.rfq
        return None

    def update(self, rfq, data):
        self.last_update_data = dict(data)
        for key, value in data.items():
            setattr(rfq, key, value)
        return rfq


class MockTemplate:
    def __init__(self, template_id, order=1, name="Stage", default_team="Team", mandatory_fields=None, planned_duration_days=5, is_required=False):
        self.id = template_id
        self.order = order
        self.name = name
        self.default_team = default_team
        self.mandatory_fields = mandatory_fields
        self.planned_duration_days = planned_duration_days
        self.is_required = is_required


class MockWorkflowForCreate:
    def __init__(self, workflow_id, stages=None, selection_mode="fixed", base_workflow_id=None, base_workflow=None):
        self.id = workflow_id
        self.name = "Workflow Create"
        self.stages = stages or [MockTemplate(uuid.uuid4(), order=1, name="Stage 1")]
        self.selection_mode = selection_mode
        self.base_workflow_id = base_workflow_id
        self.base_workflow = base_workflow


class MockWorkflowDatasourceForCreate:
    def __init__(self, workflow, extra_workflows=None):
        self.workflows = {workflow.id: workflow}
        for extra_workflow in extra_workflows or []:
            self.workflows[extra_workflow.id] = extra_workflow

    def get_by_id(self, workflow_id):
        return self.workflows.get(workflow_id)


class MockRfqDatasourceForCreate:
    def __init__(self):
        self.last_create_data = None

    def get_next_code(self, _prefix):
        return "IF-1002"

    def create(self, data):
        self.last_create_data = dict(data)

        class _RFQ:
            id = uuid.uuid4()
            rfq_code = "IF-1002"
            name = data["name"]
            client = data["client"]
            status = data["status"]
            progress = 0
            deadline = data["deadline"]
            current_stage_id = None
            workflow_id = data["workflow_id"]
            industry = data.get("industry")
            country = data.get("country")
            priority = data.get("priority", "normal")
            owner = data["owner"]
            description = data.get("description")
            outcome_reason = None
            created_at = datetime(2026, 1, 1)
            updated_at = datetime(2026, 1, 1)

        return _RFQ()


class MockRfqStageDatasourceForCreate:
    def __init__(self):
        self.created_stages = []

    def create(self, stage_data):
        self.created_stages.append(dict(stage_data))

        class _Stage:
            id = uuid.uuid4()
            name = stage_data["name"]

        return _Stage()

def test_export_csv_formatting_and_filtering():
    """Verify that export_csv delegates filters to datasource and streams properly formatted CSV."""
    ds = MockRfqDatasource()
    
    # The other datasources/session are not needed for export calculation
    ctrl = RfqController(rfq_datasource=ds, workflow_datasource=None, rfq_stage_datasource=None, session=None)
    
    # Test exporting with filters
    csv_str = ctrl.export_csv(
        status=["In preparation", "Awarded"], 
        priority="critical", 
        owner="Team A",
        created_after=date(2023, 1, 1)
    )
    
    # 1. Assert filters were correctly passed down to the datasource layer
    assert ds.last_kwargs["status"] == ["In preparation", "Awarded"]
    assert ds.last_kwargs["priority"] == "critical"
    assert ds.last_kwargs["owner"] == "Team A"
    assert ds.last_kwargs["created_after"] == date(2023, 1, 1)
    
    # 2. Assert CSV structure is correct (Headers + Rows)
    lines = csv_str.strip().split("\r\n")
    if len(lines) == 1 and "\n" in csv_str:
        # Fallback for standard newline depending on CSV writer implementation
        lines = csv_str.strip().split("\n")
        
    assert len(lines) == 3
    assert lines[0] == "RFQ Code,Name,Client,Priority,Status,Progress (%),Deadline,Owner,Created At"
    assert lines[1] == "IF-001,Pump Package,Aramco,critical,In preparation,15,2023-12-01,Team A,2023-10-01"
    assert lines[2] == "IF-002,Valves,SABIC,normal,Awarded,100,2023-11-15,Team B,2023-09-01"


def test_update_allows_metadata_only_changes():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.update(
        rfq.id,
        RfqUpdateRequest(name="RFQ B", client="Client B"),
    )

    assert result.name == "RFQ B"
    assert result.client == "Client B"
    assert result.status == "In preparation"
    assert ds.last_update_data == {"name": "RFQ B", "client": "Client B"}
    assert session.committed is True


def test_update_request_rejects_unknown_status_field():
    with pytest.raises(ValidationError) as exc:
        RfqUpdateRequest.model_validate({"name": "Should Not Persist", "status": "Awarded"})

    assert "status" in str(exc.value)
    assert "Extra inputs are not permitted" in str(exc.value)


def test_cancel_allows_transition_to_cancelled():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.cancel(
        rfq.id, RfqCancelRequest(outcome_reason="Client withdrew scope.")
    )

    assert result.status == "Cancelled"
    assert session.committed is True


def test_cancel_preserves_terminal_freeze_semantics():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.cancel(
        rfq.id, RfqCancelRequest(outcome_reason="Client withdrew scope.")
    )

    assert result.status == "Cancelled"
    assert result.current_stage_id is None
    assert session.committed is True


def test_cancel_ignores_skipped_stages_when_freezing_progress():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()

    stage_completed = type(
        "Stage",
        (),
        {
            "id": uuid.uuid4(),
            "order": 1,
            "status": "Completed",
            "progress": 100,
            "actual_end": None,
        },
    )()
    stage_skipped = type(
        "Stage",
        (),
        {
            "id": uuid.uuid4(),
            "order": 2,
            "status": "Not Started",
            "progress": 0,
            "actual_end": None,
        },
    )()
    rfq.current_stage_id = stage_skipped.id

    class _Query:
        def filter_by(self, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return [stage_completed, stage_skipped]

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    session.query = lambda _model: _Query()

    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.cancel(
        rfq.id, RfqCancelRequest(outcome_reason="Client withdrew scope.")
    )

    assert result.progress == 100
    assert stage_skipped.status == "Skipped"


def test_create_sets_explicit_initial_status_in_preparation():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(workflow_id)
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()

    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=stage_ds,
        session=session,
    )

    req = RfqCreateRequest(
        name="RFQ Create",
        client="Client",
        deadline=date(2030, 1, 1),
        industry="Industrial Systems",
        owner="Owner",
        country="Saudi Arabia",
        priority="critical",
        workflow_id=workflow_id,
        code_prefix="IF",
    )

    ctrl.create(req)

    assert rfq_ds.last_create_data is not None
    assert rfq_ds.last_create_data["rfq_code"] == "IF-1002"
    assert rfq_ds.last_create_data["status"] == "In preparation"


def test_create_persists_stage_template_id_on_generated_stages():
    workflow_id = uuid.uuid4()
    template_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(workflow_id)
    workflow.stages = [MockTemplate(template_id=template_id, order=1, name="Stage 1")]

    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()

    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=stage_ds,
        session=session,
    )

    req = RfqCreateRequest(
        name="RFQ Create",
        client="Client",
        deadline=date(2030, 1, 1),
        industry="Industrial Systems",
        owner="Owner",
        country="Saudi Arabia",
        priority="critical",
        workflow_id=workflow_id,
        code_prefix="IF",
    )

    ctrl.create(req)

    assert len(stage_ds.created_stages) == 1
    assert stage_ds.created_stages[0]["stage_template_id"] == template_id


def test_create_rejects_deadline_that_is_too_narrow_for_selected_workflow():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[
            MockTemplate(uuid.uuid4(), order=1, name="Stage 1", planned_duration_days=2),
            MockTemplate(uuid.uuid4(), order=2, name="Stage 2", planned_duration_days=3),
        ],
    )
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()
    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=stage_ds,
        session=session,
    )

    with pytest.raises(BadRequestError) as exc:
        ctrl.create(
            RfqCreateRequest(
                name="Too Narrow",
                client="Client",
                deadline=date.today() + timedelta(days=4),
                industry="Industrial Systems",
                owner="Owner",
                country="Saudi Arabia",
                priority="critical",
                workflow_id=workflow_id,
                code_prefix="IF",
            )
        )

    assert "too narrow for the selected workflow" in str(exc.value)
    assert rfq_ds.last_create_data is None
    assert stage_ds.created_stages == []


def test_create_allows_exact_minimum_feasible_deadline():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[
            MockTemplate(uuid.uuid4(), order=1, name="Stage 1", planned_duration_days=2),
            MockTemplate(uuid.uuid4(), order=2, name="Stage 2", planned_duration_days=3),
        ],
    )
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()
    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=stage_ds,
        session=session,
    )

    result = ctrl.create(
        RfqCreateRequest(
            name="Feasible",
            client="Client",
            deadline=date.today() + timedelta(days=5),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="critical",
            workflow_id=workflow_id,
            code_prefix="IF",
        )
    )

    assert result.deadline == date.today() + timedelta(days=5)
    assert rfq_ds.last_create_data is not None
    assert len(stage_ds.created_stages) == 2


def test_create_validates_deadline_against_filtered_stage_set_after_skip_stages():
    workflow_id = uuid.uuid4()
    base_workflow_id = uuid.uuid4()
    template_stage_1 = MockTemplate(
        uuid.uuid4(),
        order=1,
        name="Stage 1",
        planned_duration_days=2,
        is_required=True,
    )
    template_stage_2 = MockTemplate(
        uuid.uuid4(),
        order=2,
        name="Stage 2",
        planned_duration_days=3,
    )
    template_stage_3 = MockTemplate(
        uuid.uuid4(),
        order=3,
        name="Stage 3",
        planned_duration_days=4,
    )
    base_workflow = MockWorkflowForCreate(
        base_workflow_id,
        stages=[template_stage_1, template_stage_2, template_stage_3],
    )
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[],
        selection_mode="customizable",
        base_workflow_id=base_workflow_id,
        base_workflow=base_workflow,
    )
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()
    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow, [base_workflow]),
        rfq_stage_datasource=stage_ds,
        session=session,
    )

    result = ctrl.create(
        RfqCreateRequest(
            name="Filtered Workflow",
            client="Client",
            deadline=date.today() + timedelta(days=5),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="critical",
            workflow_id=workflow_id,
            code_prefix="IF",
            skip_stages=[template_stage_3.id],
        )
    )

    assert result.deadline == date.today() + timedelta(days=5)
    assert len(stage_ds.created_stages) == 2


def test_create_rejects_skip_stage_ids_outside_customizable_catalog():
    workflow_id = uuid.uuid4()
    base_workflow_id = uuid.uuid4()
    required_template = MockTemplate(
        uuid.uuid4(),
        order=1,
        name="RFQ received",
        is_required=True,
    )
    base_workflow = MockWorkflowForCreate(
        base_workflow_id,
        stages=[required_template],
    )
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[],
        selection_mode="customizable",
        base_workflow_id=base_workflow_id,
        base_workflow=base_workflow,
    )
    ctrl = RfqController(
        rfq_datasource=MockRfqDatasourceForCreate(),
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow, [base_workflow]),
        rfq_stage_datasource=MockRfqStageDatasourceForCreate(),
        session=MockSession(),
    )

    with pytest.raises(BadRequestError) as exc:
        ctrl.create(
            RfqCreateRequest(
                name="Custom Workflow",
                client="Client",
                deadline=date.today() + timedelta(days=5),
                industry="Industrial Systems",
                owner="Owner",
                country="Saudi Arabia",
                priority="critical",
                workflow_id=workflow_id,
                code_prefix="IF",
                skip_stages=[uuid.uuid4()],
            )
        )

    assert "do not belong to this customizable workflow" in str(exc.value)


def test_create_rejects_skip_stages_for_fixed_workflow():
    workflow_id = uuid.uuid4()
    template_stage_1 = MockTemplate(uuid.uuid4(), order=1, name="Stage 1")
    template_stage_2 = MockTemplate(uuid.uuid4(), order=2, name="Stage 2")
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[template_stage_1, template_stage_2],
        selection_mode="fixed",
    )
    ctrl = RfqController(
        rfq_datasource=MockRfqDatasourceForCreate(),
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=MockRfqStageDatasourceForCreate(),
        session=MockSession(),
    )

    with pytest.raises(BadRequestError) as exc:
        ctrl.create(
            RfqCreateRequest(
                name="Fixed Workflow",
                client="Client",
                deadline=date.today() + timedelta(days=10),
                industry="Industrial Systems",
                owner="Owner",
                country="Saudi Arabia",
                priority="critical",
                workflow_id=workflow_id,
                code_prefix="IF",
                skip_stages=[template_stage_2.id],
            )
        )

    assert "only allowed for customizable workflows" in str(exc.value)


def test_create_rejects_skipping_required_stage_for_customizable_workflow():
    workflow_id = uuid.uuid4()
    base_workflow_id = uuid.uuid4()
    required_template = MockTemplate(
        uuid.uuid4(),
        order=1,
        name="RFQ received",
        is_required=True,
    )
    optional_template = MockTemplate(
        uuid.uuid4(),
        order=2,
        name="Preliminary design",
        is_required=False,
    )
    base_workflow = MockWorkflowForCreate(
        base_workflow_id,
        stages=[required_template, optional_template],
    )
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[],
        selection_mode="customizable",
        base_workflow_id=base_workflow_id,
        base_workflow=base_workflow,
    )
    ctrl = RfqController(
        rfq_datasource=MockRfqDatasourceForCreate(),
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow, [base_workflow]),
        rfq_stage_datasource=MockRfqStageDatasourceForCreate(),
        session=MockSession(),
    )

    with pytest.raises(BadRequestError) as exc:
        ctrl.create(
            RfqCreateRequest(
                name="Custom Workflow",
                client="Client",
                deadline=date.today() + timedelta(days=10),
                industry="Industrial Systems",
                owner="Owner",
                country="Saudi Arabia",
                priority="critical",
                workflow_id=workflow_id,
                code_prefix="IF",
                skip_stages=[required_template.id],
            )
        )

    assert "Required workflow stages cannot be removed." in str(exc.value)


def test_create_customizable_workflow_reuses_base_stage_catalog_and_renumbers_selected_stages():
    workflow_id = uuid.uuid4()
    base_workflow_id = uuid.uuid4()
    required_template = MockTemplate(
        uuid.uuid4(),
        order=1,
        name="RFQ received",
        planned_duration_days=2,
        is_required=True,
    )
    optional_template = MockTemplate(
        uuid.uuid4(),
        order=4,
        name="Preliminary design",
        planned_duration_days=5,
        is_required=False,
    )
    terminal_template = MockTemplate(
        uuid.uuid4(),
        order=11,
        name="Award / Lost",
        planned_duration_days=1,
        is_required=True,
    )
    base_workflow = MockWorkflowForCreate(
        base_workflow_id,
        stages=[required_template, optional_template, terminal_template],
    )
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[],
        selection_mode="customizable",
        base_workflow_id=base_workflow_id,
        base_workflow=base_workflow,
    )
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow, [base_workflow]),
        rfq_stage_datasource=stage_ds,
        session=MockSession(),
    )

    ctrl.create(
        RfqCreateRequest(
            name="Custom Workflow",
            client="Client",
            deadline=date.today() + timedelta(days=8),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="critical",
            workflow_id=workflow_id,
            code_prefix="IF",
            skip_stages=[optional_template.id],
        )
    )

    assert [stage["name"] for stage in stage_ds.created_stages] == [
        "RFQ received",
        "Award / Lost",
    ]
    assert [stage["order"] for stage in stage_ds.created_stages] == [1, 2]
    assert [stage["stage_template_id"] for stage in stage_ds.created_stages] == [
        required_template.id,
        terminal_template.id,
    ]


def test_recalculate_stage_dates_uses_template_id_when_names_overlap():
    workflow_id = uuid.uuid4()
    template_short = MockTemplate(
        template_id=uuid.uuid4(),
        order=1,
        name="Review",
        planned_duration_days=3,
    )
    template_long = MockTemplate(
        template_id=uuid.uuid4(),
        order=2,
        name="Review",
        planned_duration_days=10,
    )

    class _Workflow:
        def __init__(self):
            self.id = workflow_id
            self.name = "Workflow Overlap"
            self.stages = [template_short, template_long]

    stage_1 = type(
        "Stage",
        (),
        {
            "id": uuid.uuid4(),
            "rfq_id": uuid.uuid4(),
            "stage_template_id": template_short.id,
            "name": "Review",
            "order": 1,
            "status": "In Progress",
            "planned_start": None,
            "planned_end": None,
        },
    )()
    stage_2 = type(
        "Stage",
        (),
        {
            "id": uuid.uuid4(),
            "rfq_id": stage_1.rfq_id,
            "stage_template_id": template_long.id,
            "name": "Review",
            "order": 2,
            "status": "Not Started",
            "planned_start": None,
            "planned_end": None,
        },
    )()

    class _Query:
        def __init__(self, items):
            self.items = items

        def filter_by(self, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.items

    class _Session(MockSession):
        def __init__(self, items):
            super().__init__()
            self.items = items
            self.flushed = False

        def query(self, _model):
            return _Query(self.items)

        def flush(self):
            self.flushed = True

    class _WorkflowDatasource:
        def get_by_id(self, _workflow_id):
            return _Workflow()

    rfq = type("RFQ", (), {"id": stage_1.rfq_id, "workflow_id": workflow_id})()
    session = _Session([stage_1, stage_2])

    ctrl = RfqController(
        rfq_datasource=None,
        workflow_datasource=_WorkflowDatasource(),
        rfq_stage_datasource=None,
        session=session,
    )

    new_deadline = date(2030, 1, 31)
    ctrl._recalculate_stage_dates(rfq, new_deadline)

    assert stage_2.planned_end == date(2030, 1, 31)
    assert stage_2.planned_start == date(2030, 1, 21)
    assert stage_1.planned_end == date(2030, 1, 21)
    assert stage_1.planned_start == date(2030, 1, 18)
    assert session.flushed is True


class MockEventBusConnector:
    def __init__(self, on_publish=None):
        self.calls = []
        self.on_publish = on_publish

    def publish(self, event_type, payload, metadata):
        if self.on_publish:
            self.on_publish(event_type, payload, metadata)
        self.calls.append({"event_type": event_type, "payload": payload, "metadata": metadata})


def test_create_publishes_rfq_created_once_after_commit():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(workflow_id)
    rfq_ds = MockRfqDatasourceForCreate()
    stage_ds = MockRfqStageDatasourceForCreate()
    session = MockSession()

    def _assert_commit_happened(_event_type, _payload, _metadata):
        assert session.committed is True

    bus = MockEventBusConnector(on_publish=_assert_commit_happened)
    ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=MockWorkflowDatasourceForCreate(workflow),
        rfq_stage_datasource=stage_ds,
        session=session,
        event_bus_connector=bus,
    )

    req = RfqCreateRequest(
        name="RFQ Create",
        client="Client",
        deadline=date(2030, 1, 1),
        industry="Industrial Systems",
        owner="Owner",
        country="Saudi Arabia",
        priority="critical",
        workflow_id=workflow_id,
        code_prefix="IF",
    )

    token = request_id_context.set("req-h4-12345678")
    try:
        ctrl.create(req, actor_user_id="u-1", actor_name="Alice", actor_team="Engineering")
    finally:
        request_id_context.reset(token)

    assert len(bus.calls) == 1
    call = bus.calls[0]
    assert call["event_type"] == "rfq.created"
    assert call["payload"]["rfq_code"] == "IF-1002"
    assert call["metadata"]["request_id"] == "req-h4-12345678"
    assert call["metadata"]["actor_user_id"] == "u-1"


def test_create_request_rejects_past_deadline():
    with pytest.raises(ValidationError) as exc:
        RfqCreateRequest(
            name="RFQ Create",
            client="Client",
            deadline=date.today() - timedelta(days=1),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="critical",
            workflow_id=uuid.uuid4(),
            code_prefix="IF",
        )

    assert "deadline cannot be in the past" in str(exc.value)


def test_update_request_rejects_past_deadline():
    with pytest.raises(ValidationError) as exc:
        RfqUpdateRequest(deadline=date.today() - timedelta(days=1))

    assert "deadline cannot be in the past" in str(exc.value)


def test_update_rejects_deadline_that_is_too_narrow_for_workflow():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[
            MockTemplate(uuid.uuid4(), order=1, name="Stage 1", planned_duration_days=2),
            MockTemplate(uuid.uuid4(), order=2, name="Stage 2", planned_duration_days=3),
        ],
    )
    rfq = MockRfqForUpdate(status="In preparation")
    rfq.workflow_id = workflow_id
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(
        ds,
        MockWorkflowDatasourceForCreate(workflow),
        None,
        MockSession(),
    )

    with pytest.raises(BadRequestError) as exc:
        ctrl.update(
            rfq.id,
            RfqUpdateRequest(deadline=date.today() + timedelta(days=4)),
        )

    assert "too narrow for the selected workflow" in str(exc.value)


def test_update_allows_exact_minimum_feasible_deadline_for_workflow():
    workflow_id = uuid.uuid4()
    workflow = MockWorkflowForCreate(
        workflow_id,
        stages=[
            MockTemplate(uuid.uuid4(), order=1, name="Stage 1", planned_duration_days=2),
            MockTemplate(uuid.uuid4(), order=2, name="Stage 2", planned_duration_days=3),
        ],
    )
    rfq = MockRfqForUpdate(status="In preparation")
    rfq.workflow_id = workflow_id
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(
        ds,
        MockWorkflowDatasourceForCreate(workflow),
        None,
        session,
    )

    result = ctrl.update(
        rfq.id,
        RfqUpdateRequest(deadline=date.today() + timedelta(days=5)),
    )

    assert result.deadline == date.today() + timedelta(days=5)
    assert session.committed is True


def test_create_request_rejects_blank_required_text_fields():
    with pytest.raises(ValidationError) as exc:
        RfqCreateRequest(
            name="   ",
            client="Client",
            deadline=date.today(),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="critical",
            workflow_id=uuid.uuid4(),
            code_prefix="IF",
        )

    assert "name is required" in str(exc.value)


def test_create_request_rejects_blank_industry_and_country():
    with pytest.raises(ValidationError) as exc:
        RfqCreateRequest(
            name="RFQ Create",
            client="Client",
            deadline=date.today(),
            industry="   ",
            owner="Owner",
            country="   ",
            priority="critical",
            workflow_id=uuid.uuid4(),
            code_prefix="IF",
        )

    message = str(exc.value)
    assert "industry is required" in message
    assert "country is required" in message


def test_update_rejects_outcome_reason_for_non_terminal_rfq():
    rfq = MockRfqForUpdate(status="In preparation")
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, MockSession())

    with pytest.raises(BadRequestError) as exc:
        ctrl.update(rfq.id, RfqUpdateRequest(outcome_reason="Still negotiating"))

    assert "outcome_reason can only be set" in str(exc.value)


def test_update_rejects_standard_lifecycle_control_updates_for_terminal_rfq():
    rfq = MockRfqForUpdate(status="Cancelled")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    with pytest.raises(ConflictError) as exc:
        ctrl.update(
            rfq.id,
            RfqUpdateRequest(
                name="Do Not Persist",
                outcome_reason="Cancelled after client withdrew scope.",
            ),
        )

    assert "Terminal RFQs are read-only through standard lifecycle controls." in str(
        exc.value
    )
    assert ds.last_update_data is None
    assert session.committed is False


def test_cancel_publishes_status_changed_only_when_value_actually_changes():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    bus = MockEventBusConnector()
    ctrl = RfqController(
        MockRfqDatasourceForUpdate(rfq),
        MockWorkflowDatasource(),
        None,
        session,
        event_bus_connector=bus,
    )

    ctrl.cancel(rfq.id, RfqCancelRequest(outcome_reason="Client withdrew scope."))
    assert any(call["event_type"] == "rfq.status_changed" for call in bus.calls)

    bus.calls.clear()
    rfq.status = "Cancelled"
    ctrl.cancel(rfq.id, RfqCancelRequest(outcome_reason="Client withdrew scope."))
    assert all(call["event_type"] != "rfq.status_changed" for call in bus.calls)


def test_update_publishes_deadline_changed_only_when_value_actually_changes():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    bus = MockEventBusConnector()
    ctrl = RfqController(
        MockRfqDatasourceForUpdate(rfq),
        MockWorkflowDatasource(),
        None,
        session,
        event_bus_connector=bus,
    )

    ctrl.update(rfq.id, RfqUpdateRequest(deadline=date(2031, 1, 1)))
    assert any(call["event_type"] == "rfq.deadline_changed" for call in bus.calls)

    bus.calls.clear()
    rfq.deadline = date(2031, 1, 1)
    ctrl.update(rfq.id, RfqUpdateRequest(deadline=date(2031, 1, 1)))
    assert all(call["event_type"] != "rfq.deadline_changed" for call in bus.calls)


def test_enrich_summaries_includes_current_stage_blocker_signal():
    rfq = MockRfqForUpdate(status="In preparation")
    rfq.workflow_id = uuid.uuid4()
    current_stage_id = uuid.uuid4()
    rfq.current_stage_id = current_stage_id

    workflow = type("Workflow", (), {"id": rfq.workflow_id, "name": "Workflow A"})()
    stage = type(
        "Stage",
        (),
        {
            "id": current_stage_id,
            "name": "Client Clarifications",
            "order": 4,
            "status": "In Progress",
            "blocker_status": "Blocked",
            "blocker_reason_code": "waiting_client_input",
        },
    )()

    class _Query:
        def __init__(self, items):
            self.items = items

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.items

    class _Session(MockSession):
        def __init__(self):
            super().__init__()
            self.query_calls = 0

        def query(self, _model):
            self.query_calls += 1
            return _Query([workflow] if self.query_calls == 1 else [stage])

    ctrl = RfqController(
        rfq_datasource=None,
        workflow_datasource=None,
        rfq_stage_datasource=None,
        session=_Session(),
    )

    result = ctrl._enrich_summaries([rfq])

    assert len(result) == 1
    assert result[0].current_stage_name == "Client Clarifications"
    assert result[0].current_stage_id == current_stage_id
    assert result[0].current_stage_order == 4
    assert result[0].current_stage_status == "In Progress"
    assert result[0].current_stage_blocker_status == "Blocked"
    assert result[0].current_stage_blocker_reason_code == "waiting_client_input"


def test_event_publish_failure_does_not_fail_successful_update_and_is_logged(caplog):
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()

    class _FailingBus:
        def publish(self, _event_type, _payload, _metadata):
            raise RuntimeError("event bus down")

    ctrl = RfqController(
        MockRfqDatasourceForUpdate(rfq),
        MockWorkflowDatasource(),
        None,
        session,
        event_bus_connector=_FailingBus(),
    )

    result = ctrl.update(rfq.id, RfqUpdateRequest(deadline=date(2031, 1, 1)))

    assert result.deadline == date(2031, 1, 1)
    assert session.committed is True
    assert any("event_publish_failed" in record.message for record in caplog.records)

import pytest
import uuid
from datetime import date

from src.controllers.rfq_controller import RfqController
from src.translators.rfq_translator import RfqUpdateRequest
from src.utils.errors import ConflictError

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
        r2 = MockRFQ("IF-002", "Valves", "SABIC", "normal", "Submitted", 100, date(2023, 11, 15), "Team B", date(2023, 9, 1))
        return MockQuery([r1, r2])


class MockWorkflow:
    def __init__(self, workflow_id):
        self.id = workflow_id
        self.name = "Workflow A"


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

    def get_by_id(self, rfq_id):
        if rfq_id == self.rfq.id:
            return self.rfq
        return None

    def update(self, rfq, data):
        for key, value in data.items():
            setattr(rfq, key, value)
        return rfq


class MockTemplate:
    def __init__(self, template_id, order=1, name="Stage", default_team="Team", mandatory_fields=None, planned_duration_days=5):
        self.id = template_id
        self.order = order
        self.name = name
        self.default_team = default_team
        self.mandatory_fields = mandatory_fields
        self.planned_duration_days = planned_duration_days


class MockWorkflowForCreate:
    def __init__(self, workflow_id):
        self.id = workflow_id
        self.name = "Workflow Create"
        self.stages = [MockTemplate(uuid.uuid4(), order=1, name="Stage 1")]


class MockWorkflowDatasourceForCreate:
    def __init__(self, workflow):
        self.workflow = workflow

    def get_by_id(self, workflow_id):
        if workflow_id == self.workflow.id:
            return self.workflow
        return None


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
            created_at = date(2026, 1, 1)
            updated_at = date(2026, 1, 1)

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
        status=["In preparation", "Submitted"], 
        priority="critical", 
        owner="Team A",
        created_after=date(2023, 1, 1)
    )
    
    # 1. Assert filters were correctly passed down to the datasource layer
    assert ds.last_kwargs["status"] == ["In preparation", "Submitted"]
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
    assert lines[2] == "IF-002,Valves,SABIC,normal,Submitted,100,2023-11-15,Team B,2023-09-01"


def test_update_rejects_invalid_status_transition_submitted_to_draft():
    rfq = MockRfqForUpdate(status="Submitted")
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, MockSession())

    with pytest.raises(ConflictError) as exc:
        ctrl.update(rfq.id, RfqUpdateRequest(status="Draft"))

    assert "Invalid RFQ status transition" in str(exc.value)


def test_update_allows_valid_status_transition_in_preparation_to_submitted():
    rfq = MockRfqForUpdate(status="In preparation")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.update(rfq.id, RfqUpdateRequest(status="Submitted"))

    assert result.status == "Submitted"
    assert session.committed is True


def test_update_rejects_invalid_status_transition_in_preparation_to_awarded():
    rfq = MockRfqForUpdate(status="In preparation")
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, MockSession())

    with pytest.raises(ConflictError) as exc:
        ctrl.update(rfq.id, RfqUpdateRequest(status="Awarded"))

    assert "Invalid RFQ status transition" in str(exc.value)


def test_update_allows_valid_status_transition_submitted_to_awarded():
    rfq = MockRfqForUpdate(status="Submitted")
    session = MockSession()
    ds = MockRfqDatasourceForUpdate(rfq)
    ctrl = RfqController(ds, MockWorkflowDatasource(), None, session)

    result = ctrl.update(rfq.id, RfqUpdateRequest(status="Awarded"))

    assert result.status == "Awarded"
    assert result.current_stage_id is None
    assert session.committed is True


def test_update_terminal_progress_ignores_skipped_stages():
    rfq = MockRfqForUpdate(status="Submitted")
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

    result = ctrl.update(rfq.id, RfqUpdateRequest(status="Awarded"))

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

    from src.translators.rfq_translator import RfqCreateRequest

    req = RfqCreateRequest(
        name="RFQ Create",
        client="Client",
        deadline=date(2030, 1, 1),
        owner="Owner",
        workflow_id=workflow_id,
        code_prefix="IF",
    )

    ctrl.create(req)

    assert rfq_ds.last_create_data is not None
    assert rfq_ds.last_create_data["status"] == "In preparation"

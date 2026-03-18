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
        raise AssertionError("query() should not be called in these transition tests")


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

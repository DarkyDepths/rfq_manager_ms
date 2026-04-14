import pytest
from src.app_context import get_reminder_controller, get_rfq_controller, get_rfq_stage_controller
from src.utils.errors import BadRequestError

class MockRfqController:
    def __init__(self):
        self.last_kwargs = {}
        self.update_calls = []
        self.cancel_calls = []

    @staticmethod
    def _detail_payload():
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "rfq_code": "IF-1001",
            "name": "API Test RFQ",
            "client": "Client A",
            "status": "In preparation",
            "progress": 20,
            "deadline": "2030-01-01",
            "current_stage_name": "RFQ received",
            "workflow_name": "Workflow A",
            "industry": "Industrial Systems",
            "country": "Saudi Arabia",
            "priority": "normal",
            "owner": "Team A",
            "description": "API test payload",
            "workflow_id": "00000000-0000-0000-0000-000000000002",
            "current_stage_id": "00000000-0000-0000-0000-000000000003",
            "source_package_available": False,
            "source_package_updated_at": None,
            "workbook_available": False,
            "workbook_updated_at": None,
            "outcome_reason": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def list(self, **kwargs):
        self.last_kwargs = {
            k: str(v) if v is not None and not isinstance(v, (int, list, dict, str)) else v 
            for k, v in kwargs.items()
        }
        return {
            "data": [],
            "total": 0,
            "page": kwargs.get("page", 1),
            "size": kwargs.get("size", 20)
        }

    def get(self, rfq_id):
        payload = self._detail_payload()
        payload["id"] = str(rfq_id)
        return payload

    def export_csv(self, **kwargs):
        self.last_kwargs = kwargs
        return "RFQ Code,Name\r\nIF-001,Pump Package"

    def update(self, rfq_id, body, **kwargs):
        self.update_calls.append({"rfq_id": str(rfq_id), "body": body, "kwargs": kwargs})
        payload = self._detail_payload()
        payload["id"] = str(rfq_id)
        payload["name"] = body.name or payload["name"]
        payload["client"] = body.client or payload["client"]
        return payload

    def cancel(self, rfq_id, body, **kwargs):
        self.cancel_calls.append({"rfq_id": str(rfq_id), "body": body, "kwargs": kwargs})
        payload = self._detail_payload()
        payload["id"] = str(rfq_id)
        payload["status"] = "Cancelled"
        payload["progress"] = 100
        payload["current_stage_id"] = None
        payload["current_stage_name"] = None
        payload["outcome_reason"] = body.outcome_reason
        return payload

mock_ctrl = MockRfqController()

def override_get_rfq_controller():
    return mock_ctrl


class MockRfqStageController:
    def __init__(self):
        self.advance_calls = []
        self.update_calls = []

    def update(self, rfq_id, stage_id, body, **kwargs):
        self.update_calls.append(
            {
                "rfq_id": str(rfq_id),
                "stage_id": str(stage_id),
                "body": body,
                "kwargs": kwargs,
            }
        )
        return {
            "id": str(stage_id),
            "name": "Preliminary design",
            "order": 4,
            "assigned_team": "Engineering",
            "status": "In preparation",
            "progress": 40,
            "planned_start": None,
            "planned_end": None,
            "actual_start": None,
            "actual_end": None,
            "blocker_status": body.blocker_status,
            "blocker_reason_code": body.blocker_reason_code,
            "captured_data": body.captured_data or {},
            "mandatory_fields": "design_approved",
            "notes": [],
            "files": [],
            "subtasks": [],
        }

    def advance(self, rfq_id, stage_id, request=None, **kwargs):
        self.advance_calls.append(
            {
                "rfq_id": str(rfq_id),
                "stage_id": str(stage_id),
                "request": request,
                "kwargs": kwargs,
            }
        )
        return {
            "id": str(stage_id),
            "name": "Go / No-Go",
            "order": 2,
            "assigned_team": kwargs.get("actor_team"),
            "status": "Skipped",
            "progress": 40,
            "planned_start": None,
            "planned_end": None,
            "actual_start": "2026-04-06",
            "actual_end": "2026-04-06",
            "blocker_status": None,
            "blocker_reason_code": None,
            "captured_data": {"go_nogo_decision": "no_go"},
            "mandatory_fields": "go_nogo_decision",
            "notes": [],
            "files": [],
            "subtasks": [],
        }


mock_stage_ctrl = MockRfqStageController()


def override_get_rfq_stage_controller():
    return mock_stage_ctrl


class MockReminderController:
    def __init__(self):
        self.created = []
        self.resolved = []

    def create(self, body, created_by: str):
        self.created.append({"body": body, "created_by": created_by})
        return {
            "id": "00000000-0000-0000-0000-000000000041",
            "rfq_id": str(body.rfq_id),
            "rfq_stage_id": str(body.rfq_stage_id) if body.rfq_stage_id else None,
            "type": body.type,
            "message": body.message,
            "due_date": body.due_date,
            "assigned_to": body.assigned_to,
            "status": "open",
            "source": "manual",
            "delay_days": 0,
            "created_by": created_by,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_sent_at": None,
            "send_count": 0,
        }

    def resolve(self, reminder_id):
        self.resolved.append(str(reminder_id))
        return {
            "id": str(reminder_id),
            "rfq_id": "00000000-0000-0000-0000-000000000042",
            "rfq_stage_id": None,
            "type": "internal",
            "message": "Reminder",
            "due_date": "2030-01-01",
            "assigned_to": "Engineering",
            "status": "resolved",
            "source": "manual",
            "delay_days": 0,
            "created_by": "System",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_sent_at": None,
            "send_count": 1,
        }


mock_reminder_ctrl = MockReminderController()


def override_get_reminder_controller():
    return mock_reminder_ctrl


@pytest.fixture
def api_client(app, client):
    app.dependency_overrides[get_rfq_controller] = override_get_rfq_controller
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_rfq_controller, None)


@pytest.fixture
def stage_api_client(app, client):
    app.dependency_overrides[get_rfq_stage_controller] = override_get_rfq_stage_controller
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_rfq_stage_controller, None)


@pytest.fixture
def reminder_api_client(app, client):
    app.dependency_overrides[get_reminder_controller] = override_get_reminder_controller
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_reminder_controller, None)


def test_422_validation_error_format(api_client):
    """Verify that FastAPI RequestValidationErrors are formatted matching AppError structure."""
    # Send an invalid priority to trigger 422 (must be 'normal' or 'critical')
    response = api_client.get("/rfq-manager/v1/rfqs?priority=invalid_priority")
    
    assert response.status_code == 422
    data = response.json()
    
    # Assert the uniform error contract
    assert "error" in data
    assert "message" in data
    assert data["error"] == "UnprocessableEntityError"
    
    # Ensure validation clarity is preserved (tells consumer exactly what failed)
    assert "Validation failed" in data["message"]
    assert "query.priority" in data["message"]
    assert "Input should be" in data["message"]

def test_rich_filters_parsing(api_client):
    """Verify that FastAPI correctly parses multi-value status, dates, and other Phase 2 filters."""
    # Note: Using valid enums for status and priority
    response = api_client.get(
        "/rfq-manager/v1/rfqs",
        params={
            "status": ["Awarded", "In preparation"],
            "priority": "critical",
            "owner": "Engineering Team",
            "created_after": "2023-01-01",
            "created_before": "2023-12-31",
            "search": "Pump"
        }
    )
    
    assert response.status_code == 200
    filters = mock_ctrl.last_kwargs
    
    # Assert FastAPI correctly extracted the multi-value status as a list
    assert filters["status"] == ["Awarded", "In preparation"]
    
    # Assert other parameters
    assert filters["priority"] == "critical"
    assert filters["owner"] == "Engineering Team"
    assert filters["created_after"] == "2023-01-01"
    assert filters["created_before"] == "2023-12-31"
    assert filters["search"] == "Pump"

def test_export_csv_endpoint(api_client):
    """Verify that the GET /rfqs/export natively returns CSV files and attachment headers"""
    response = api_client.get("/rfq-manager/v1/rfqs/export?status=Awarded")
    
    assert response.status_code == 200
    # Allow for optional charset=utf-8 which FastAPI injects
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename" in response.headers["content-disposition"]
    assert "rfqs_export.csv" in response.headers["content-disposition"]
    assert "RFQ Code,Name" in response.text


def test_get_rfq_detail_exposes_intelligence_milestones(api_client):
    response = api_client.get(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000009",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_package_available"] is False
    assert payload["source_package_updated_at"] is None
    assert payload["workbook_available"] is False
    assert payload["workbook_updated_at"] is None


def test_list_rejects_dormant_operational_status_filter(api_client):
    response = api_client.get("/rfq-manager/v1/rfqs?status=Submitted")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "UnprocessableEntityError"
    assert "query.status.0" in payload["message"]


def test_invalid_sort_returns_clean_400_error(api_client, app):
    class BadSortController:
        def list(self, **_kwargs):
            raise BadRequestError("Invalid sort field 'workflow_id'. Allowed fields: client, created_at, deadline, name, owner, priority, progress, status.")

    app.dependency_overrides[get_rfq_controller] = lambda: BadSortController()
    try:
        response = api_client.get("/rfq-manager/v1/rfqs?sort=workflow_id")
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"] == "BadRequestError"
        assert "Invalid sort field" in payload["message"]
    finally:
        app.dependency_overrides[get_rfq_controller] = override_get_rfq_controller


def test_metadata_only_patch_calls_controller_update(api_client):
    mock_ctrl.update_calls.clear()
    response = api_client.patch(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000010",
        json={"name": "Updated Name"},
    )

    assert response.status_code == 200
    assert len(mock_ctrl.update_calls) == 1
    assert mock_ctrl.update_calls[0]["body"].name == "Updated Name"


@pytest.mark.parametrize("status_value", ["In preparation", "Awarded"])
def test_generic_patch_rejects_status_field_before_controller_runs(api_client, status_value):
    mock_ctrl.update_calls.clear()
    response = api_client.patch(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000011",
        json={"name": "Should Not Persist", "status": status_value},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "UnprocessableEntityError"
    assert "body.status" in payload["message"]
    assert "Extra inputs are not permitted" in payload["message"]
    assert mock_ctrl.update_calls == []


def test_cancel_endpoint_calls_controller_cancel(api_client):
    mock_ctrl.cancel_calls.clear()
    response = api_client.post(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000012/cancel",
        json={"outcome_reason": "Client withdrew scope."},
    )

    assert response.status_code == 200
    assert len(mock_ctrl.cancel_calls) == 1
    assert mock_ctrl.cancel_calls[0]["body"].outcome_reason == "Client withdrew scope."
    assert response.json()["status"] == "Cancelled"


def test_cancel_endpoint_requires_reason_before_controller_runs(api_client):
    mock_ctrl.cancel_calls.clear()
    response = api_client.post(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000013/cancel",
        json={"outcome_reason": "   "},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "UnprocessableEntityError"
    assert "Please provide a cancellation reason before cancelling this RFQ." in payload["message"]
    assert mock_ctrl.cancel_calls == []


def test_stage_advance_accepts_no_go_confirmation_body(stage_api_client):
    mock_stage_ctrl.advance_calls.clear()
    response = stage_api_client.post(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000021/stages/00000000-0000-0000-0000-000000000022/advance",
        json={
            "confirm_no_go_cancel": True,
            "outcome_reason": "Client withdrew the opportunity after go/no-go review.",
        },
    )

    assert response.status_code == 200
    assert len(mock_stage_ctrl.advance_calls) == 1
    request = mock_stage_ctrl.advance_calls[0]["request"]
    assert request.confirm_no_go_cancel is True
    assert request.outcome_reason == "Client withdrew the opportunity after go/no-go review."
    assert "rfq_stage:*" in mock_stage_ctrl.advance_calls[0]["kwargs"]["actor_permissions"]
    assert "*" not in mock_stage_ctrl.advance_calls[0]["kwargs"]["actor_permissions"]
    assert response.json()["status"] == "Skipped"


def test_stage_update_forwards_actor_name(stage_api_client):
    mock_stage_ctrl.update_calls.clear()
    response = stage_api_client.patch(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000025/stages/00000000-0000-0000-0000-000000000026",
        json={
            "captured_data": {"design_approved": "yes"},
            "blocker_status": "Resolved",
        },
    )

    assert response.status_code == 200
    assert len(mock_stage_ctrl.update_calls) == 1
    assert mock_stage_ctrl.update_calls[0]["kwargs"]["actor_name"] == "System"
    assert response.json()["captured_data"]["design_approved"] == "yes"


def test_stage_advance_accepts_terminal_outcome_body(stage_api_client):
    mock_stage_ctrl.advance_calls.clear()
    response = stage_api_client.post(
        "/rfq-manager/v1/rfqs/00000000-0000-0000-0000-000000000031/stages/00000000-0000-0000-0000-000000000032/advance",
        json={
            "terminal_outcome": "lost",
            "lost_reason_code": "commercial_gap",
        },
    )

    assert response.status_code == 200
    assert len(mock_stage_ctrl.advance_calls) == 1
    request = mock_stage_ctrl.advance_calls[0]["request"]
    assert request.terminal_outcome == "lost"
    assert request.lost_reason_code == "commercial_gap"
    assert "rfq_stage:*" in mock_stage_ctrl.advance_calls[0]["kwargs"]["actor_permissions"]
    assert "*" not in mock_stage_ctrl.advance_calls[0]["kwargs"]["actor_permissions"]


def test_reminder_create_accepts_stage_link(reminder_api_client):
    mock_reminder_ctrl.created.clear()
    response = reminder_api_client.post(
        "/rfq-manager/v1/reminders",
        json={
            "rfq_id": "00000000-0000-0000-0000-000000000051",
            "rfq_stage_id": "00000000-0000-0000-0000-000000000052",
            "type": "internal",
            "message": "Follow up on blocked stage",
            "due_date": "2030-01-01",
            "assigned_to": "Engineering",
        },
    )

    assert response.status_code == 201
    assert len(mock_reminder_ctrl.created) == 1
    assert str(mock_reminder_ctrl.created[0]["body"].rfq_stage_id) == "00000000-0000-0000-0000-000000000052"
    assert response.json()["source"] == "manual"


def test_reminder_resolve_endpoint_calls_controller(reminder_api_client):
    mock_reminder_ctrl.resolved.clear()
    response = reminder_api_client.post(
        "/rfq-manager/v1/reminders/00000000-0000-0000-0000-000000000053/resolve",
    )

    assert response.status_code == 200
    assert mock_reminder_ctrl.resolved == ["00000000-0000-0000-0000-000000000053"]
    assert response.json()["status"] == "resolved"

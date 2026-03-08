import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.app_context import get_rfq_controller

class MockRfqController:
    def __init__(self):
        self.last_kwargs = {}

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

mock_ctrl = MockRfqController()

def override_get_rfq_controller():
    return mock_ctrl

# Set up dependency override
app.dependency_overrides[get_rfq_controller] = override_get_rfq_controller
client = TestClient(app)

def test_422_validation_error_format():
    """Verify that FastAPI RequestValidationErrors are formatted matching AppError structure."""
    # Send an invalid priority to trigger 422 (must be 'normal' or 'critical')
    response = client.get("/rfq-manager/v1/rfqs?priority=invalid_priority")
    
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

def test_rich_filters_parsing():
    """Verify that FastAPI correctly parses multi-value status, dates, and other Phase 2 filters."""
    # Note: Using valid enums for status and priority
    response = client.get(
        "/rfq-manager/v1/rfqs"
        "?status=Submitted&status=In preparation"
        "&priority=critical"
        "&owner=Engineering Team"
        "&created_after=2023-01-01"
        "&created_before=2023-12-31"
        "&search=Pump"
    )
    
    assert response.status_code == 200
    filters = mock_ctrl.last_kwargs
    
    # Assert FastAPI correctly extracted the multi-value status as a list
    assert filters["status"] == ["Submitted", "In preparation"]
    
    # Assert other parameters
    assert filters["priority"] == "critical"
    assert filters["owner"] == "Engineering Team"
    assert filters["created_after"] == "2023-01-01"
    assert filters["created_before"] == "2023-12-31"
    assert filters["search"] == "Pump"

# Clean up override
def teardown_module():
    app.dependency_overrides.clear()

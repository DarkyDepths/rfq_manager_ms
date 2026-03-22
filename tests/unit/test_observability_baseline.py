from uuid import UUID, uuid4

from fastapi import Request
from fastapi.testclient import TestClient

from src.utils.errors import BadRequestError


def test_request_without_incoming_id_gets_generated_x_request_id(client):
    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    UUID(request_id)


def test_request_with_incoming_x_request_id_is_preserved(client):
    incoming = "cli-request-12345"

    response = client.get("/health", headers={"X-Request-ID": incoming})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


def test_request_with_incoming_x_correlation_id_is_normalized_to_x_request_id(client):
    incoming = "upstream-correlation-abcde"

    response = client.get("/health", headers={"X-Correlation-ID": incoming})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


def test_invalid_incoming_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": "   "})

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    UUID(request_id)


def test_error_response_still_includes_x_request_id_header(app):
    @app.get("/_test/observability-error")
    def _error_route(_request: Request):
        raise BadRequestError("observability test error")

    with TestClient(app) as client:
        response = client.get("/_test/observability-error")

    assert response.status_code == 400
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    payload = response.json()
    assert payload["request_id"] == request_id


def test_metrics_endpoint_is_reachable(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


def test_metrics_expose_expected_request_counter_and_latency_families(client):
    client.get("/health")
    metrics_response = client.get("/metrics")
    body = metrics_response.text

    assert "rfq_manager_http_requests_total" in body
    assert "rfq_manager_http_request_duration_seconds_bucket" in body


def test_metrics_route_label_uses_template_not_raw_uuid(app):
    @app.get("/_test/items/{item_id}")
    def _item(item_id: str):
        return {"id": item_id}

    rfq_id = str(uuid4())

    with TestClient(app) as client:
        client.get(f"/_test/items/{rfq_id}")
        metrics_response = client.get("/metrics")
        body = metrics_response.text

    assert 'route="/_test/items/{item_id}"' in body
    assert rfq_id not in body


def test_health_still_works_as_before(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

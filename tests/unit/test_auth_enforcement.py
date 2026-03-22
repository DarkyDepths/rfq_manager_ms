from fastapi.testclient import TestClient
from datetime import date
from uuid import uuid4

from src.app import create_app
from src.app_context import get_iam_service_connector, get_reminder_controller, get_rfq_controller
from src.config.settings import settings
from src.connectors.iam_service import IAMPrincipal
from src.utils.errors import ServiceUnavailableError


class _MockRfqController:
    def __init__(self):
        self.last_kwargs = {}

    def list(self, **kwargs):
        self.last_kwargs = kwargs
        return {"data": [], "total": 0, "page": kwargs.get("page", 1), "size": kwargs.get("size", 20)}

    def get_stats(self):
        return {
            "total_rfqs_12m": 0,
            "open_rfqs": 0,
            "critical_rfqs": 0,
            "avg_cycle_days": 0,
        }


class _MockReminderController:
    def create(self, body, created_by: str):
        return {
            "id": str(uuid4()),
            "rfq_id": str(body.rfq_id),
            "rfq_stage_id": None,
            "type": body.type,
            "message": body.message,
            "due_date": body.due_date,
            "assigned_to": body.assigned_to,
            "status": "open",
            "delay_days": 0,
            "created_by": created_by,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_sent_at": None,
            "send_count": 0,
        }


class _AllowReadConnector:
    def resolve_principal(self, _authorization_header: str) -> IAMPrincipal:
        return IAMPrincipal(
            user_id="u-1",
            user_name="Reader",
            team="workspace",
            permissions=["rfq:read"],
        )


class _AllowStatsConnector:
    def resolve_principal(self, _authorization_header: str) -> IAMPrincipal:
        return IAMPrincipal(
            user_id="u-2",
            user_name="Stats",
            team="workspace",
            permissions=["rfq:stats"],
        )


class _DenyAllConnector:
    def resolve_principal(self, _authorization_header: str) -> IAMPrincipal:
        return IAMPrincipal(
            user_id="u-3",
            user_name="Denied",
            team="workspace",
            permissions=[],
        )


class _TimeoutConnector:
    def resolve_principal(self, _authorization_header: str) -> IAMPrincipal:
        raise ServiceUnavailableError("IAM service timeout during auth resolution")


def _make_client(*, bypass_enabled: bool, connector_override=None) -> TestClient:
    settings.AUTH_BYPASS_ENABLED = bypass_enabled
    if not bypass_enabled:
        settings.IAM_SERVICE_URL = "http://iam.local/iam/v1"

    app = create_app()
    app.dependency_overrides[get_rfq_controller] = lambda: _MockRfqController()

    if connector_override is not None:
        app.dependency_overrides[get_iam_service_connector] = lambda: connector_override

    return TestClient(app)


def _make_client_with_reminder_write(*, bypass_enabled: bool, connector_override=None) -> TestClient:
    settings.AUTH_BYPASS_ENABLED = bypass_enabled
    if not bypass_enabled:
        settings.IAM_SERVICE_URL = "http://iam.local/iam/v1"

    app = create_app()
    app.dependency_overrides[get_reminder_controller] = lambda: _MockReminderController()

    if connector_override is not None:
        app.dependency_overrides[get_iam_service_connector] = lambda: connector_override

    return TestClient(app)


def test_unauthenticated_request_is_rejected_when_bypass_disabled():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_AllowReadConnector()) as client:
            response = client.get("/rfq-manager/v1/rfqs")

        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "UnauthorizedError"
        assert "Missing bearer token" in payload["message"]
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_authenticated_but_unauthorized_request_returns_403():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_DenyAllConnector()) as client:
            response = client.get(
                "/rfq-manager/v1/rfqs",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 403
        payload = response.json()
        assert payload["error"] == "ForbiddenError"
        assert "rfq:read" in payload["message"]
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_authorized_request_succeeds_with_matching_permission():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_AllowReadConnector()) as client:
            response = client.get(
                "/rfq-manager/v1/rfqs",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert response.json()["data"] == []
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_bypass_mode_only_works_when_explicitly_enabled():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_AllowReadConnector()) as client_enforced:
            enforced_response = client_enforced.get("/rfq-manager/v1/rfqs")

        with _make_client(bypass_enabled=True) as client_bypass:
            bypass_response = client_bypass.get("/rfq-manager/v1/rfqs")

        assert enforced_response.status_code == 401
        assert bypass_response.status_code == 200
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_permission_mapping_distinguishes_read_vs_stats_actions():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_AllowReadConnector()) as client_read_only:
            list_response = client_read_only.get(
                "/rfq-manager/v1/rfqs",
                headers={"Authorization": "Bearer test-token"},
            )
            stats_forbidden = client_read_only.get(
                "/rfq-manager/v1/rfqs/stats",
                headers={"Authorization": "Bearer test-token"},
            )

        with _make_client(bypass_enabled=False, connector_override=_AllowStatsConnector()) as client_stats:
            stats_allowed = client_stats.get(
                "/rfq-manager/v1/rfqs/stats",
                headers={"Authorization": "Bearer test-token"},
            )

        assert list_response.status_code == 200
        assert stats_forbidden.status_code == 403
        assert stats_allowed.status_code == 200
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_iam_failure_returns_controlled_503_response():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client(bypass_enabled=False, connector_override=_TimeoutConnector()) as client:
            response = client.get(
                "/rfq-manager/v1/rfqs",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 503
        payload = response.json()
        assert payload["error"] == "ServiceUnavailableError"
        assert "IAM service timeout" in payload["message"]
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_write_request_is_401_without_token_when_bypass_disabled():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client_with_reminder_write(bypass_enabled=False, connector_override=_AllowReadConnector()) as client:
            response = client.post(
                "/rfq-manager/v1/reminders",
                json={
                    "rfq_id": str(uuid4()),
                    "type": "internal",
                    "message": "follow up",
                    "due_date": date.today().isoformat(),
                },
            )

        assert response.status_code == 401
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_write_request_is_403_without_required_permission():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    try:
        with _make_client_with_reminder_write(bypass_enabled=False, connector_override=_AllowReadConnector()) as client:
            response = client.post(
                "/rfq-manager/v1/reminders",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "rfq_id": str(uuid4()),
                    "type": "internal",
                    "message": "follow up",
                    "due_date": date.today().isoformat(),
                },
            )

        assert response.status_code == 403
        payload = response.json()
        assert payload["error"] == "ForbiddenError"
        assert "reminder:create" in payload["message"]
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url

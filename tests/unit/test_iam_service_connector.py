from unittest.mock import Mock, patch

import pytest

from src.connectors.iam_service import IAMServiceConnector
from src.utils.errors import ForbiddenError, ServiceUnavailableError


def test_iam_connector_maps_403_to_forbidden_error():
    connector = IAMServiceConnector("http://iam.local/iam/v1", timeout_seconds=1.0)

    response = Mock()
    response.status_code = 403
    response.content = b'{"message": "forbidden"}'

    with patch("src.connectors.iam_service.httpx.get", return_value=response):
        with pytest.raises(ForbiddenError) as exc:
            connector.resolve_principal("Bearer token")

    assert "forbidden" in str(exc.value).lower()


def test_iam_connector_non_json_payload_is_controlled_service_unavailable():
    connector = IAMServiceConnector("http://iam.local/iam/v1", timeout_seconds=1.0)

    response = Mock()
    response.status_code = 200
    response.content = b"<html>not-json</html>"
    response.json.side_effect = ValueError("invalid json")

    with patch("src.connectors.iam_service.httpx.get", return_value=response):
        with pytest.raises(ServiceUnavailableError) as exc:
            connector.resolve_principal("Bearer token")

    assert "non-json" in str(exc.value).lower()


def test_iam_connector_missing_identity_is_controlled_service_unavailable():
    connector = IAMServiceConnector("http://iam.local/iam/v1", timeout_seconds=1.0)

    response = Mock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {"permissions": ["rfq:read"]}

    with patch("src.connectors.iam_service.httpx.get", return_value=response):
        with pytest.raises(ServiceUnavailableError) as exc:
            connector.resolve_principal("Bearer token")

    assert "missing required user identity" in str(exc.value).lower()

from unittest.mock import Mock, patch

import pytest

from src.connectors.event_bus import EventBusConnector
from src.utils.errors import EventBusPublishError


def test_publish_fails_when_event_bus_url_is_blank():
    connector = EventBusConnector(base_url="", timeout_seconds=1.0)

    with pytest.raises(EventBusPublishError) as exc:
        connector.publish("rfq.created", {"rfq_id": "1"})

    assert "EVENT_BUS_URL" in str(exc.value)


def test_publish_posts_expected_event_envelope():
    connector = EventBusConnector(base_url="http://event-bus.local/events", timeout_seconds=1.0)

    response = Mock(status_code=202)
    with patch("src.connectors.event_bus.httpx.post", return_value=response) as post_mock:
        connector.publish(
            "rfq.created",
            {"rfq_id": "rfq-1", "rfq_code": "IF-0001"},
            metadata={"request_id": "req-12345678", "actor_user_id": "u-1"},
        )

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["timeout"] == 1.0
    envelope = call_kwargs["json"]

    assert envelope["event_type"] == "rfq.created"
    assert envelope["source"] == "rfq_manager_ms"
    assert envelope["payload"]["rfq_id"] == "rfq-1"
    assert envelope["metadata"]["request_id"] == "req-12345678"
    assert envelope["metadata"]["actor_user_id"] == "u-1"
    assert envelope["occurred_at"]


def test_publish_raises_on_non_2xx_response():
    connector = EventBusConnector(base_url="http://event-bus.local/events", timeout_seconds=1.0)

    response = Mock(status_code=503, text="downstream unavailable")
    with patch("src.connectors.event_bus.httpx.post", return_value=response):
        with pytest.raises(EventBusPublishError) as exc:
            connector.publish("rfq.created", {"rfq_id": "1"})

    assert "status 503" in str(exc.value)

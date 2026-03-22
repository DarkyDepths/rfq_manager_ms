"""Event bus connector.

Publishes domain events over HTTP to EVENT_BUS_URL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from src.utils.errors import EventBusPublishError


class EventBusConnector:
	def __init__(self, base_url: str, timeout_seconds: float = 3.0):
		self.base_url = (base_url or "").strip()
		self.timeout_seconds = timeout_seconds

	def publish(self, event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> None:
		if not self.base_url:
			raise EventBusPublishError("EVENT_BUS_URL is not configured")

		envelope = {
			"event_type": event_type,
			"occurred_at": datetime.now(timezone.utc).isoformat(),
			"source": "rfq_manager_ms",
			"payload": payload,
			"metadata": metadata or {},
		}

		try:
			response = httpx.post(
				self.base_url,
				json=envelope,
				timeout=self.timeout_seconds,
			)
		except httpx.TimeoutException as exc:
			raise EventBusPublishError("Event bus publish timeout") from exc
		except httpx.HTTPError as exc:
			raise EventBusPublishError("Event bus publish transport error") from exc

		if response.status_code < 200 or response.status_code >= 300:
			body_text = response.text[:200] if getattr(response, "text", None) else ""
			raise EventBusPublishError(
				f"Event bus publish rejected with status {response.status_code}: {body_text}"
			)

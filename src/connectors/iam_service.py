"""IAM connector used for request authentication/authorization resolution.

Expected IAM response shape (either form is accepted):
1) {
	 "user": {"id": "u1", "name": "Alice", "team": "workspace"},
	 "permissions": ["rfq:read", "rfq:create"]
   }
2) {
	 "user_id": "u1",
	 "user_name": "Alice",
	 "team": "workspace",
	 "permissions": ["rfq:read", "rfq:create"]
   }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.utils.errors import ForbiddenError, ServiceUnavailableError, UnauthorizedError


@dataclass
class IAMPrincipal:
	user_id: str
	user_name: str
	team: str
	permissions: list[str]


class IAMServiceConnector:
	def __init__(self, base_url: str, timeout_seconds: float = 3.0):
		self.base_url = (base_url or "").rstrip("/")
		self.timeout_seconds = timeout_seconds

	def resolve_principal(self, authorization_header: str) -> IAMPrincipal:
		if not self.base_url:
			raise ServiceUnavailableError("IAM service is not configured")

		try:
			response = httpx.get(
				f"{self.base_url}/auth/resolve",
				headers={"Authorization": authorization_header},
				timeout=self.timeout_seconds,
			)
		except httpx.TimeoutException as exc:
			raise ServiceUnavailableError("IAM service timeout during auth resolution") from exc
		except httpx.HTTPError as exc:
			raise ServiceUnavailableError("IAM service is unavailable for auth resolution") from exc

		if response.status_code == 401:
			raise UnauthorizedError("Invalid or expired bearer token")

		if response.status_code == 403:
			raise ForbiddenError("Access forbidden by IAM")

		if response.status_code >= 500:
			raise ServiceUnavailableError("IAM service returned a server error")

		if response.status_code != 200:
			raise UnauthorizedError("Authentication rejected by IAM")

		try:
			payload = response.json() if response.content else {}
		except ValueError as exc:
			raise ServiceUnavailableError("IAM service returned a non-JSON auth response") from exc

		return self._parse_principal_payload(payload)

	@staticmethod
	def _parse_principal_payload(payload: dict[str, Any]) -> IAMPrincipal:
		user_obj = payload.get("user") or {}

		user_id = str(user_obj.get("id") or payload.get("user_id") or "").strip()
		user_name = str(user_obj.get("name") or payload.get("user_name") or "").strip()
		team = str(user_obj.get("team") or payload.get("team") or "").strip()

		raw_permissions = payload.get("permissions")
		permissions = [str(item) for item in raw_permissions] if isinstance(raw_permissions, list) else []

		if not user_id:
			raise ServiceUnavailableError("IAM response is missing required user identity")

		return IAMPrincipal(
			user_id=user_id,
			user_name=user_name or user_id,
			team=team or "workspace",
			permissions=permissions,
		)

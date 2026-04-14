"""Authentication + authorization dependencies for FastAPI routes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.app_context import get_iam_service_connector
from src.config.settings import settings
from src.connectors.iam_service import IAMServiceConnector
from src.utils.errors import ForbiddenError, UnauthorizedError


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    user_id: str
    user_name: str
    team: str
    permissions: list[str]

    def has_permission(self, required: str) -> bool:
        if "*" in self.permissions:
            return True

        if required in self.permissions:
            return True

        if ":" in required:
            resource, _action = required.split(":", 1)
            if f"{resource}:*" in self.permissions:
                return True

        return False


class Permissions:
    RFQ_CREATE = "rfq:create"
    RFQ_READ = "rfq:read"
    RFQ_UPDATE = "rfq:update"
    RFQ_EXPORT = "rfq:export"
    RFQ_STATS = "rfq:stats"
    RFQ_ANALYTICS = "rfq:analytics"

    WORKFLOW_READ = "workflow:read"
    WORKFLOW_UPDATE = "workflow:update"

    RFQ_STAGE_READ = "rfq_stage:read"
    RFQ_STAGE_UPDATE = "rfq_stage:update"
    RFQ_STAGE_ADVANCE = "rfq_stage:advance"
    RFQ_STAGE_ADD_NOTE = "rfq_stage:add_note"
    RFQ_STAGE_ADD_FILE = "rfq_stage:add_file"

    SUBTASK_CREATE = "subtask:create"
    SUBTASK_READ = "subtask:read"
    SUBTASK_UPDATE = "subtask:update"
    SUBTASK_DELETE = "subtask:delete"

    REMINDER_CREATE = "reminder:create"
    REMINDER_READ = "reminder:read"
    REMINDER_UPDATE = "reminder:update"
    REMINDER_UPDATE_RULES = "reminder:update_rules"
    REMINDER_TEST = "reminder:test"
    REMINDER_PROCESS = "reminder:process"

    FILE_LIST = "file:list"
    FILE_DOWNLOAD = "file:download"
    FILE_DELETE = "file:delete"


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    iam_connector: IAMServiceConnector = Depends(get_iam_service_connector),
) -> AuthContext:
    if settings.AUTH_BYPASS_ENABLED:
        permissions = _parse_permissions_csv(settings.AUTH_BYPASS_PERMISSIONS)
        debug_user_id = None
        debug_user_name = None
        debug_team = None
        debug_permissions = None

        if settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED:
            debug_user_id = request.headers.get("X-Debug-User-Id")
            debug_user_name = request.headers.get("X-Debug-User-Name")
            debug_team = request.headers.get("X-Debug-User-Team")
            debug_permissions = request.headers.get("X-Debug-Permissions")
        elif any(
            request.headers.get(header)
            for header in (
                "X-Debug-User-Id",
                "X-Debug-User-Name",
                "X-Debug-User-Team",
                "X-Debug-Permissions",
            )
        ):
            logger.warning(
                "Ignoring X-Debug-* headers because AUTH_BYPASS_DEBUG_HEADERS_ENABLED=false"
            )

        if debug_permissions:
            parsed = _parse_permissions_csv(debug_permissions)
            if parsed:
                permissions = parsed

        context = AuthContext(
            user_id=debug_user_id or settings.AUTH_BYPASS_USER_ID,
            user_name=debug_user_name or settings.AUTH_BYPASS_USER_NAME,
            team=debug_team or settings.AUTH_BYPASS_TEAM,
            permissions=permissions,
        )
        request.state.user = {
            "id": context.user_id,
            "name": context.user_name,
            "team": context.team,
            "permissions": context.permissions,
        }
        return context

    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Missing bearer token")

    principal = iam_connector.resolve_principal(
        f"{credentials.scheme} {credentials.credentials}"
    )

    context = AuthContext(
        user_id=principal.user_id,
        user_name=principal.user_name,
        team=principal.team,
        permissions=principal.permissions,
    )
    request.state.user = {
        "id": context.user_id,
        "name": context.user_name,
        "team": context.team,
        "permissions": context.permissions,
    }
    return context


def require_permission(permission: str):
    def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not auth.has_permission(permission):
            raise ForbiddenError(f"Missing permission: {permission}")
        return auth

    return dependency


def _parse_permissions_csv(raw_permissions: str | None) -> list[str]:
    return [item.strip() for item in (raw_permissions or "").split(",") if item.strip()]

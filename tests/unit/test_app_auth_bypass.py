import logging

from fastapi import Depends, Request
from fastapi.testclient import TestClient

from src.app import create_app
from src.config.settings import settings
from src.utils.auth import get_auth_context


def test_auth_bypass_injects_demo_user_context():
    original = (
        settings.AUTH_BYPASS_ENABLED,
        settings.AUTH_BYPASS_USER_ID,
        settings.AUTH_BYPASS_USER_NAME,
        settings.AUTH_BYPASS_TEAM,
        settings.AUTH_BYPASS_PERMISSIONS,
        settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED,
    )

    settings.AUTH_BYPASS_ENABLED = True
    settings.AUTH_BYPASS_USER_ID = "demo-user"
    settings.AUTH_BYPASS_USER_NAME = "Demo User"
    settings.AUTH_BYPASS_TEAM = "workspace"
    settings.AUTH_BYPASS_PERMISSIONS = "rfq:read,file:*"
    settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED = False

    try:
        app = create_app()

        @app.get("/_test/auth-context")
        def auth_context(
            request: Request,
            _auth=Depends(get_auth_context),
        ):
            return getattr(request.state, "user", {})

        with TestClient(app) as client:
            response = client.get("/_test/auth-context")

        assert response.status_code == 200
        assert response.json() == {
            "id": "demo-user",
            "name": "Demo User",
            "team": "workspace",
            "permissions": ["rfq:read", "file:*"],
        }
    finally:
        (
            settings.AUTH_BYPASS_ENABLED,
            settings.AUTH_BYPASS_USER_ID,
            settings.AUTH_BYPASS_USER_NAME,
            settings.AUTH_BYPASS_TEAM,
            settings.AUTH_BYPASS_PERMISSIONS,
            settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED,
        ) = original


def test_auth_bypass_ignores_debug_headers_unless_explicitly_enabled():
    original = (
        settings.AUTH_BYPASS_ENABLED,
        settings.AUTH_BYPASS_USER_ID,
        settings.AUTH_BYPASS_USER_NAME,
        settings.AUTH_BYPASS_TEAM,
        settings.AUTH_BYPASS_PERMISSIONS,
        settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED,
    )

    settings.AUTH_BYPASS_ENABLED = True
    settings.AUTH_BYPASS_USER_ID = "demo-user"
    settings.AUTH_BYPASS_USER_NAME = "Demo User"
    settings.AUTH_BYPASS_TEAM = "workspace"
    settings.AUTH_BYPASS_PERMISSIONS = "rfq:read"
    settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED = False

    try:
        app = create_app()

        @app.get("/_test/auth-context-ignore-debug")
        def auth_context(
            request: Request,
            _auth=Depends(get_auth_context),
        ):
            return getattr(request.state, "user", {})

        with TestClient(app) as client:
            response = client.get(
                "/_test/auth-context-ignore-debug",
                headers={
                    "X-Debug-User-Id": "spoofed-user",
                    "X-Debug-User-Name": "Spoofed User",
                    "X-Debug-User-Team": "sales",
                    "X-Debug-Permissions": "file:delete",
                },
            )

        assert response.status_code == 200
        assert response.json() == {
            "id": "demo-user",
            "name": "Demo User",
            "team": "workspace",
            "permissions": ["rfq:read"],
        }
    finally:
        (
            settings.AUTH_BYPASS_ENABLED,
            settings.AUTH_BYPASS_USER_ID,
            settings.AUTH_BYPASS_USER_NAME,
            settings.AUTH_BYPASS_TEAM,
            settings.AUTH_BYPASS_PERMISSIONS,
            settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED,
        ) = original


def test_auth_bypass_startup_logs_warning(caplog):
    original = settings.AUTH_BYPASS_ENABLED
    settings.AUTH_BYPASS_ENABLED = True

    try:
        caplog.set_level(logging.WARNING)
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert any(
            "Auth bypass enabled for local/dev mode only." in record.message
            for record in caplog.records
        )
    finally:
        settings.AUTH_BYPASS_ENABLED = original

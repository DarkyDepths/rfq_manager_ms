import logging

from fastapi import Request
from fastapi.testclient import TestClient

from src.app import create_app
from src.config.settings import settings


def test_auth_bypass_injects_demo_user_context():
    original = (
        settings.AUTH_BYPASS_ENABLED,
        settings.AUTH_BYPASS_USER_ID,
        settings.AUTH_BYPASS_USER_NAME,
        settings.AUTH_BYPASS_TEAM,
    )

    settings.AUTH_BYPASS_ENABLED = True
    settings.AUTH_BYPASS_USER_ID = "demo-user"
    settings.AUTH_BYPASS_USER_NAME = "Demo User"
    settings.AUTH_BYPASS_TEAM = "workspace"

    try:
        app = create_app()

        @app.get("/_test/auth-context")
        def auth_context(request: Request):
            return getattr(request.state, "user", {})

        with TestClient(app) as client:
            response = client.get("/_test/auth-context")

        assert response.status_code == 200
        assert response.json() == {
            "id": "demo-user",
            "name": "Demo User",
            "team": "workspace",
        }
    finally:
        (
            settings.AUTH_BYPASS_ENABLED,
            settings.AUTH_BYPASS_USER_ID,
            settings.AUTH_BYPASS_USER_NAME,
            settings.AUTH_BYPASS_TEAM,
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
            "V1: auth bypassed, see rfq_iam_ms integration plan." in record.message
            for record in caplog.records
        )
    finally:
        settings.AUTH_BYPASS_ENABLED = original

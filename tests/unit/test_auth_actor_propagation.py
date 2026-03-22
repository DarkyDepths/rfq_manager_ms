from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from src.app import create_app
from src.app_context import (
    get_iam_service_connector,
    get_reminder_controller,
    get_rfq_stage_controller,
)
from src.config.settings import settings
from src.connectors.iam_service import IAMPrincipal


class _AllowAllConnector:
    def resolve_principal(self, _authorization_header: str) -> IAMPrincipal:
        return IAMPrincipal(
            user_id="auth-user-id",
            user_name="Auth User",
            team="workspace",
            permissions=["*"],
        )


class _MockStageController:
    def __init__(self):
        self.last_note_user_name = None
        self.last_file_uploaded_by = None

    def add_note(self, _rfq_id, _stage_id, body, user_name: str):
        self.last_note_user_name = user_name
        return {
            "id": str(uuid4()),
            "user_name": user_name,
            "text": body.text,
            "created_at": datetime.now(timezone.utc),
        }

    def upload_file(self, _rfq_id, _stage_id, filename, file_type, file_content, uploaded_by: str):
        self.last_file_uploaded_by = uploaded_by
        return {
            "id": str(uuid4()),
            "filename": filename,
            "download_url": f"/rfq-manager/v1/files/{uuid4()}/download",
            "type": file_type,
            "uploaded_by": uploaded_by,
            "size_bytes": len(file_content),
            "uploaded_at": datetime.now(timezone.utc),
        }


class _MockReminderController:
    def __init__(self):
        self.last_created_by = None

    def create(self, body, created_by: str):
        self.last_created_by = created_by
        now = datetime.now(timezone.utc)
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
            "created_at": now,
            "updated_at": now,
            "last_sent_at": None,
            "send_count": 0,
        }


def test_stage_note_route_forwards_authenticated_actor_name():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    stage_ctrl = _MockStageController()

    try:
        settings.AUTH_BYPASS_ENABLED = False
        settings.IAM_SERVICE_URL = "http://iam.local/iam/v1"

        app = create_app()
        app.dependency_overrides[get_rfq_stage_controller] = lambda: stage_ctrl
        app.dependency_overrides[get_iam_service_connector] = lambda: _AllowAllConnector()

        with TestClient(app) as client:
            response = client.post(
                f"/rfq-manager/v1/rfqs/{uuid4()}/stages/{uuid4()}/notes",
                headers={"Authorization": "Bearer test-token"},
                json={"text": "actor note"},
            )

        assert response.status_code == 201
        assert response.json()["user_name"] == "Auth User"
        assert stage_ctrl.last_note_user_name == "Auth User"
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_stage_file_upload_route_forwards_authenticated_actor_name():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    stage_ctrl = _MockStageController()

    try:
        settings.AUTH_BYPASS_ENABLED = False
        settings.IAM_SERVICE_URL = "http://iam.local/iam/v1"

        app = create_app()
        app.dependency_overrides[get_rfq_stage_controller] = lambda: stage_ctrl
        app.dependency_overrides[get_iam_service_connector] = lambda: _AllowAllConnector()

        with TestClient(app) as client:
            response = client.post(
                f"/rfq-manager/v1/rfqs/{uuid4()}/stages/{uuid4()}/files",
                headers={"Authorization": "Bearer test-token"},
                data={"type": "Other"},
                files={"file": ("actor.txt", b"payload", "text/plain")},
            )

        assert response.status_code == 201
        assert response.json()["uploaded_by"] == "Auth User"
        assert stage_ctrl.last_file_uploaded_by == "Auth User"
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url


def test_reminder_create_route_forwards_authenticated_actor_name():
    original_bypass = settings.AUTH_BYPASS_ENABLED
    original_iam_url = settings.IAM_SERVICE_URL

    reminder_ctrl = _MockReminderController()

    try:
        settings.AUTH_BYPASS_ENABLED = False
        settings.IAM_SERVICE_URL = "http://iam.local/iam/v1"

        app = create_app()
        app.dependency_overrides[get_reminder_controller] = lambda: reminder_ctrl
        app.dependency_overrides[get_iam_service_connector] = lambda: _AllowAllConnector()

        with TestClient(app) as client:
            response = client.post(
                "/rfq-manager/v1/reminders",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "rfq_id": str(uuid4()),
                    "type": "internal",
                    "message": "follow up",
                    "due_date": date.today().isoformat(),
                    "assigned_to": "Engineering",
                },
            )

        assert response.status_code == 201
        assert response.json()["created_by"] == "Auth User"
        assert reminder_ctrl.last_created_by == "Auth User"
    finally:
        settings.AUTH_BYPASS_ENABLED = original_bypass
        settings.IAM_SERVICE_URL = original_iam_url

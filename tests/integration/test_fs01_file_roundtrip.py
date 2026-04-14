import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app import app
from src.config.settings import settings
from src.database import Base, get_db
from src.models.rfq import RFQ
from src.models.rfq_file import RFQFile
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow

# Ensure models are imported so Base.metadata is complete for test DB
import src.models.rfq_history  # noqa: F401
import src.models.rfq_note  # noqa: F401
import src.models.rfq_stage_field_value  # noqa: F401
import src.models.reminder  # noqa: F401
import src.models.subtask  # noqa: F401


@pytest.fixture
def fs01_env(tmp_path):
    db_path = tmp_path / "fs01.sqlite3"
    storage_root = tmp_path / "uploads"

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    Base.metadata.create_all(bind=engine)

    seed_session = TestingSessionLocal()
    workflow_id = uuid.uuid4()
    rfq_id = uuid.uuid4()
    stage_id = uuid.uuid4()

    workflow = Workflow(
        id=workflow_id,
        name="FS01 Workflow",
        code="FS01-WF",
        is_active=True,
        is_default=False,
    )
    rfq = RFQ(
        id=rfq_id,
        name="FS01 RFQ",
        client="FS01 Client",
        deadline=date(2030, 1, 1),
        owner="FS01 Owner",
        workflow_id=workflow_id,
        status="In preparation",
        progress=0,
        rfq_code="IF-9001",
    )
    stage = RFQStage(
        id=stage_id,
        rfq_id=rfq_id,
        name="FS01 Stage",
        order=1,
        assigned_team="workspace",
        status="In Progress",
        progress=0,
    )

    seed_session.add(workflow)
    seed_session.add(rfq)
    seed_session.add(stage)
    seed_session.commit()
    seed_session.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    original_storage = settings.FILE_STORAGE_PATH
    original_bypass = settings.AUTH_BYPASS_ENABLED
    settings.FILE_STORAGE_PATH = str(storage_root)
    settings.AUTH_BYPASS_ENABLED = True
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
            "session_factory": TestingSessionLocal,
            "rfq_id": rfq_id,
            "stage_id": stage_id,
            "storage_root": storage_root,
        }

    app.dependency_overrides.pop(get_db, None)
    settings.FILE_STORAGE_PATH = original_storage
    settings.AUTH_BYPASS_ENABLED = original_bypass
    engine.dispose()


def test_fs01_roundtrip_upload_list_download_delete_with_legacy_path_support(fs01_env):
    client = fs01_env["client"]
    session_factory = fs01_env["session_factory"]
    rfq_id = fs01_env["rfq_id"]
    stage_id = fs01_env["stage_id"]
    storage_root = fs01_env["storage_root"]

    file_bytes = b"FS01 deterministic payload\nline-2\n"

    upload_resp = client.post(
        f"/rfq-manager/v1/rfqs/{rfq_id}/stages/{stage_id}/files",
        files={"file": ("fs01.txt", file_bytes, "text/plain")},
        data={"type": "Other"},
    )
    assert upload_resp.status_code == 201, upload_resp.text

    uploaded = upload_resp.json()
    file_id = uuid.UUID(uploaded["id"])

    db = session_factory()
    try:
        file_row = db.query(RFQFile).filter(RFQFile.id == file_id).first()
        assert file_row is not None

        expected_relative = f"{rfq_id}/{stage_id}/{file_id}_fs01.txt"
        assert file_row.file_path == expected_relative

        physical_path = storage_root / Path(file_row.file_path)
        assert physical_path.exists()
        assert physical_path.read_bytes() == file_bytes

        list_resp = client.get(f"/rfq-manager/v1/rfqs/{rfq_id}/stages/{stage_id}/files")
        assert list_resp.status_code == 200
        assert any(item["id"] == str(file_id) for item in list_resp.json()["data"])

        download_resp = client.get(f"/rfq-manager/v1/files/{file_id}/download")
        assert download_resp.status_code == 200
        assert download_resp.content == file_bytes

        file_row.file_path = f"uploads/{file_row.file_path}"
        db.commit()

        legacy_download_resp = client.get(f"/rfq-manager/v1/files/{file_id}/download")
        assert legacy_download_resp.status_code == 200
        assert legacy_download_resp.content == file_bytes

    finally:
        db.close()

    delete_resp = client.delete(f"/rfq-manager/v1/files/{file_id}")
    assert delete_resp.status_code == 204

    post_delete_download = client.get(f"/rfq-manager/v1/files/{file_id}/download")
    assert post_delete_download.status_code == 404


def test_fs01_download_returns_404_when_file_missing_on_disk(fs01_env):
    client = fs01_env["client"]
    session_factory = fs01_env["session_factory"]
    rfq_id = fs01_env["rfq_id"]
    stage_id = fs01_env["stage_id"]

    ghost_id = uuid.uuid4()

    db = session_factory()
    try:
        ghost = RFQFile(
            id=ghost_id,
            rfq_stage_id=stage_id,
            filename="ghost.txt",
            file_path=f"{rfq_id}/{stage_id}/{ghost_id}_ghost.txt",
            type="Other",
            uploaded_by="FS01",
            size_bytes=12,
        )
        db.add(ghost)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/rfq-manager/v1/files/{ghost_id}/download")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"] == "NotFoundError"
    assert "not found on disk" in payload["message"]


def test_fs01_upload_sanitizes_path_segments_in_filename(fs01_env):
    client = fs01_env["client"]
    session_factory = fs01_env["session_factory"]
    rfq_id = fs01_env["rfq_id"]
    stage_id = fs01_env["stage_id"]

    upload_resp = client.post(
        f"/rfq-manager/v1/rfqs/{rfq_id}/stages/{stage_id}/files",
        files={"file": ("../nested/evil.txt", b"payload", "text/plain")},
        data={"type": "Other"},
    )
    assert upload_resp.status_code == 201, upload_resp.text

    file_id = uuid.UUID(upload_resp.json()["id"])
    db = session_factory()
    try:
        file_row = db.query(RFQFile).filter(RFQFile.id == file_id).first()
        assert file_row is not None
        assert file_row.file_path.endswith(f"{file_id}_evil.txt")
        assert "../" not in file_row.file_path
        assert "..\\" not in file_row.file_path
    finally:
        db.close()

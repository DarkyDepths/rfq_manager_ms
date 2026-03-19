import pytest
import uuid
from unittest.mock import patch
from src.controllers.file_controller import FileController
from src.models.rfq_file import RFQFile
from src.models.rfq_stage import RFQStage
from src.utils.errors import NotFoundError

RFQ1 = str(uuid.uuid4())
ST1 = str(uuid.uuid4())
F1 = str(uuid.uuid4())

from datetime import datetime

class MockFileDatasource:
    def list_by_stage(self, stage_id):
        return [RFQFile(id=F1, rfq_stage_id=stage_id, filename="doc.pdf", type="application/pdf", uploaded_by="User A", size_bytes=1000, file_path="/fake/path/doc.pdf", uploaded_at=datetime.now())]
        
    def get_by_id(self, file_id):
        if str(file_id) == F1:
            return RFQFile(id=F1, filename="doc.pdf", file_path="/fake/path/doc.pdf", uploaded_at=datetime.now())
        return None
        
    def soft_delete(self, file):
        self.deleted = True

class MockStageDatasource:
    def get_by_id(self, stage_id):
        if str(stage_id) == ST1:
            return RFQStage(id=ST1, rfq_id=RFQ1)
        return None

class MockSession:
    def commit(self): pass

def test_list_for_stage_success():
    ctrl = FileController(MockFileDatasource(), MockStageDatasource(), MockSession())
    res = ctrl.list_for_stage(RFQ1, ST1)
    assert len(res["data"]) == 1
    assert res["data"][0].filename == "doc.pdf"
    payload = res["data"][0].model_dump()
    assert "file_path" not in payload
    assert payload["download_url"] == f"/rfq-manager/v1/files/{F1}/download"

def test_list_for_stage_not_found():
    ctrl = FileController(MockFileDatasource(), MockStageDatasource(), MockSession())
    with pytest.raises(NotFoundError):
        ctrl.list_for_stage(RFQ1, str(uuid.uuid4()))

@patch("src.controllers.file_controller.os.path.exists")
@patch("src.controllers.file_controller._resolve_physical_path")
def test_get_file_path_success(mock_resolve, mock_exists):
    mock_resolve.return_value = "/fake/abs/path/doc.pdf"
    mock_exists.return_value = True
    ctrl = FileController(MockFileDatasource(), MockStageDatasource(), MockSession())
    path, filename = ctrl.get_file_path(F1)
    assert path == "/fake/abs/path/doc.pdf"
    assert filename == "doc.pdf"

@patch("src.controllers.file_controller.os.path.exists")
@patch("src.controllers.file_controller._resolve_physical_path")
def test_get_file_path_not_on_disk(mock_resolve, mock_exists):
    mock_resolve.return_value = "/fake/abs/path/doc.pdf"
    mock_exists.return_value = False
    ctrl = FileController(MockFileDatasource(), MockStageDatasource(), MockSession())
    with pytest.raises(NotFoundError):
        ctrl.get_file_path(F1)

def test_resolve_physical_path_legacy():
    from src.controllers.file_controller import _resolve_physical_path
    from src.config.settings import settings
    # For a legacy path in the DB
    path = _resolve_physical_path("uploads/123/456/file.txt")
    assert path.endswith("123/456/file.txt")

def test_resolve_physical_path_new():
    from src.controllers.file_controller import _resolve_physical_path
    from src.config.settings import settings
    # For a modern path in the DB
    path = _resolve_physical_path("123/456/file.txt")
    assert path.endswith("123/456/file.txt")

def test_delete_success():
    ds = MockFileDatasource()
    ctrl = FileController(ds, MockStageDatasource(), MockSession())
    ctrl.delete(F1)
    assert ds.deleted is True

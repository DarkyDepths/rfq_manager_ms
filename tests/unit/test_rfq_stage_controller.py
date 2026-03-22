import pytest
import uuid
from unittest.mock import patch, MagicMock
from datetime import date, datetime
from src.controllers.rfq_stage_controller import RfqStageController
from src.models.rfq_stage import RFQStage
from src.models.rfq import RFQ
from src.utils.errors import ConflictError, UnprocessableEntityError, BadRequestError
from src.translators.rfq_stage_translator import RfqStageUpdateRequest, NoteCreateRequest

RFQ1 = str(uuid.uuid4())
ST1 = str(uuid.uuid4())
ST2 = str(uuid.uuid4())

class MockStageDatasource:
    def list_by_rfq(self, rfq_id):
        if str(rfq_id) == RFQ1:
            return [RFQStage(id=ST1, rfq_id=RFQ1, progress=0, name="Stage 1", status="In preparation", order=1)]
        return []
        
    def get_by_id(self, stage_id):
        if str(stage_id) == ST1:
            return RFQStage(id=ST1, rfq_id=RFQ1, name="Stage 1", progress=50, blocker_status="None", status="In preparation", order=1)
        return None
        
    def get_notes(self, stage_id): return []
    def list_files(self, stage_id): return []
    def update(self, stage, data):
        for k, v in data.items():
            setattr(stage, k, v)
        return stage
    def add_note(self, data):
        return MagicMock(id=str(uuid.uuid4()), text=data["text"], user_name=data["user_name"], created_at=date.today())
    def add_file(self, data):
        # Prevent Path mock from confusing pydantic by casting file_path to string explicitly
        return MagicMock(id=data["id"], filename=data["filename"], file_path=str(data["file_path"]), type=data["type"], uploaded_by=data["uploaded_by"], size_bytes=data["size_bytes"], uploaded_at=datetime.now())
    def get_next_stage(self, rfq_id, order):
        return RFQStage(id=ST2, rfq_id=RFQ1, order=order+1)

class MockRfqDatasource:
    def get_by_id(self, rfq_id):
        return RFQ(id=rfq_id, current_stage_id=ST1, status="In preparation", progress=0)

class MockSession:
    def __init__(self):
        self.query_mock = MagicMock()
        self.filter_mock = MagicMock()
        self.query_mock.filter.return_value = self.filter_mock
        self.filter_mock.order_by.return_value.all.return_value = []
        self.filter_mock.count.return_value = 0
    def query(self, model): return self.query_mock
    def commit(self): pass
    def flush(self): pass
    def refresh(self, obj): pass

def test_stage_list():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    res = ctrl.list(RFQ1)
    assert len(res["data"]) == 1

def test_stage_get():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    res = ctrl.get(RFQ1, ST1)
    assert res.name == "Stage 1"

def test_stage_update():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    req = RfqStageUpdateRequest(progress=75)
    res = ctrl.update(RFQ1, ST1, req)
    assert res.progress == 75

def test_stage_update_rejected_with_subtasks():
    session = MockSession()
    session.filter_mock.count.return_value = 1
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), session)
    req = RfqStageUpdateRequest(progress=75)
    with pytest.raises(ConflictError) as exc:
        ctrl.update(RFQ1, ST1, req)
    assert "Cannot manually update progress" in str(exc.value)

def test_stage_update_non_progress_allowed_with_subtasks():
    session = MockSession()
    session.filter_mock.count.return_value = 1
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), session)
    req = RfqStageUpdateRequest(blocker_status="Blocked")
    res = ctrl.update(RFQ1, ST1, req)
    assert res.blocker_status == "Blocked"

def test_add_note():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    res = ctrl.add_note(RFQ1, ST1, NoteCreateRequest(text="Hello"), "User A")
    assert res.text == "Hello"
    assert res.user_name == "User A"

@patch("src.controllers.rfq_stage_controller.settings")
def test_upload_file_size_limit(mock_settings):
    mock_settings.MAX_FILE_SIZE_MB = 1 # 1MB limit
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    
    with pytest.raises(BadRequestError):
        ctrl.upload_file(RFQ1, ST1, "big.pdf", "application/pdf", b"0" * (2 * 1024 * 1024), uploaded_by="User A")

@patch("src.controllers.rfq_stage_controller.open")
@patch("src.controllers.rfq_stage_controller.Path")
@patch("src.controllers.rfq_stage_controller.settings")
def test_upload_file_success(mock_settings, mock_path, mock_open):
    mock_settings.MAX_FILE_SIZE_MB = 10
    mock_settings.FILE_STORAGE_PATH = "/tmp"
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    
    res = ctrl.upload_file(RFQ1, ST1, "test.txt", "text/plain", b"abc", uploaded_by="User A")
    assert res.filename == "test.txt"
    assert res.size_bytes == 3
    assert res.uploaded_by == "User A"
    payload = res.model_dump()
    assert "file_path" not in payload
    assert payload["download_url"] == f"/rfq-manager/v1/files/{res.id}/download"

def test_advance_blocked():
    stage_ds = MockStageDatasource()
    # Override get_by_id to return blocked stage
    stage_ds.get_by_id = lambda id: RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="Blocked", blocker_reason_code="WAITING_CLIENT")
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    
    with pytest.raises(ConflictError):
        ctrl.advance(RFQ1, ST1)

def test_advance_missing_mandatory():
    stage_ds = MockStageDatasource()
    stage = RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="None", mandatory_fields="po_number, value", captured_data={"po_number": "123"}, order=1, name="Stage 1")
    stage_ds.get_by_id = lambda id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    
    with pytest.raises(UnprocessableEntityError):
        ctrl.advance(RFQ1, ST1)

def test_advance_success():
    stage_ds = MockStageDatasource()
    stage = RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="None", mandatory_fields="po_number", captured_data={"po_number": "123"}, order=1, name="Stage 1")
    stage_ds.get_by_id = lambda id: stage
    
    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda id: rfq
    
    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())
    
    ctrl.advance(RFQ1, ST1)
    assert stage.status == "Completed"
    assert stage.progress == 100
    assert rfq.current_stage_id == ST2


def test_advance_last_stage_does_not_force_submitted_status():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Final Stage",
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=40)
    rfq_ds.get_by_id = lambda _id: rfq

    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())
    ctrl.advance(RFQ1, ST1)

    assert stage.status == "Completed"
    assert rfq.status == "In preparation"
    assert rfq.progress == 100


def test_update_rfq_progress_ignores_skipped_stages():
    stage_ds = MockStageDatasource()
    stage_ds.list_by_rfq = lambda _rfq_id: [
        RFQStage(id=ST1, rfq_id=RFQ1, status="Completed", progress=100, order=1, name="A"),
        RFQStage(id=ST2, rfq_id=RFQ1, status="Skipped", progress=0, order=2, name="B"),
    ]

    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=0)
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    ctrl._update_rfq_progress(rfq)

    assert rfq.progress == 100


def test_update_rfq_progress_excludes_skipped_from_average():
    stage_ds = MockStageDatasource()
    stage_ds.list_by_rfq = lambda _rfq_id: [
        RFQStage(id=ST1, rfq_id=RFQ1, status="Completed", progress=100, order=1, name="A"),
        RFQStage(id=ST2, rfq_id=RFQ1, status="In Progress", progress=50, order=2, name="B"),
        RFQStage(id=str(uuid.uuid4()), rfq_id=RFQ1, status="Skipped", progress=0, order=3, name="C"),
    ]

    rfq = RFQ(id=RFQ1, current_stage_id=ST2, status="In preparation", progress=0)
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    ctrl._update_rfq_progress(rfq)

    assert rfq.progress == 75


def test_stage_detail_file_response_hides_file_path():
    stage_ds = MockStageDatasource()
    file_id = uuid.uuid4()
    stage_ds.list_files = lambda _stage_id: [
        MagicMock(
            id=file_id,
            filename="scope.pdf",
            file_path=f"{RFQ1}/{ST1}/{file_id}_scope.pdf",
            type="application/pdf",
            uploaded_by="User A",
            size_bytes=123,
            uploaded_at=datetime.now(),
        )
    ]

    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    res = ctrl.get(RFQ1, ST1)

    assert len(res.files) == 1
    payload = res.files[0].model_dump()
    assert "file_path" not in payload
    assert payload["download_url"] == f"/rfq-manager/v1/files/{file_id}/download"

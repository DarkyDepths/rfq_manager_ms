import pytest
import uuid
from unittest.mock import patch, MagicMock
from datetime import date, datetime
from pydantic import ValidationError
from src.controllers.rfq_stage_controller import RfqStageController
from src.models.rfq_stage import RFQStage
from src.models.rfq import RFQ
from src.models.subtask import Subtask
from src.translators import rfq_stage_translator
from src.utils.errors import ConflictError, UnprocessableEntityError, BadRequestError
from src.translators.rfq_stage_translator import (
    NoteCreateRequest,
    RfqStageAdvanceRequest,
    RfqStageUpdateRequest,
)
from src.utils.observability import request_id_context

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
            return RFQStage(id=ST1, rfq_id=RFQ1, name="Stage 1", progress=50, blocker_status="None", status="In preparation", order=1, assigned_team="Team A")
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


def _get_history_events(captured_data):
    return captured_data.get(rfq_stage_translator.LIFECYCLE_HISTORY_EVENTS_FIELD, [])

def test_stage_list():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    res = ctrl.list(RFQ1)
    assert len(res["data"]) == 1

def test_stage_get():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    res = ctrl.get(RFQ1, ST1)
    assert res.name == "Stage 1"
    assert res.blocker_status is None
    assert res.blocker_reason_code is None


def test_stage_get_sanitizes_malformed_workflow_history_events_in_captured_data():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Stage 1",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=1,
        assigned_team="Team A",
        captured_data={
            "go_nogo_decision": "go",
            "workflow_history_events": [
                {"type": "decision_recorded", "value": "go", "actor_name": "  Reviewer  "},
                {"type": "unknown_event", "value": "bad"},
                "not-a-dict",
                {"type": "blocker_created", "source": "AUTOMATIC", "reason": " waiting_client_input "},
            ],
        },
    )

    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    res = ctrl.get(RFQ1, ST1)

    history_events = _get_history_events(res.captured_data)
    assert len(history_events) == 2
    assert history_events[0]["type"] == "decision_recorded"
    assert history_events[0]["actor_name"] == "Reviewer"
    assert history_events[1]["type"] == "blocker_created"
    assert history_events[1]["source"] == "automatic"
    assert history_events[1]["reason"] == "waiting_client_input"

def test_stage_update_persists_blocker_fields():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    req = RfqStageUpdateRequest(
        blocker_status="Blocked",
        blocker_reason_code="waiting_client_input",
    )
    res = ctrl.update(RFQ1, ST1, req)
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "waiting_client_input"


def test_stage_update_ignores_assigned_team_override():
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), MockSession())
    req = RfqStageUpdateRequest.model_validate({"assigned_team": "Engineering"})
    res = ctrl.update(RFQ1, ST1, req)
    assert res.assigned_team == "Team A"


def test_stage_update_persists_canonical_no_go_decision():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Go / No-Go",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=1,
        assigned_team="Team A",
        captured_data={},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(captured_data={"go_nogo_decision": "No-Go"}),
    )

    assert res.captured_data["go_nogo_decision"] == "no_go"
    history_events = _get_history_events(res.captured_data)
    assert len(history_events) == 1
    assert history_events[0]["type"] == "decision_recorded"
    assert history_events[0]["field_key"] == "go_nogo_decision"
    assert history_events[0]["value"] == "no_go"


def test_stage_update_persists_structured_estimation_fields():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Cost estimation",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=7,
        assigned_team="Estimation",
        mandatory_fields="estimation_completed",
        captured_data={},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(
            captured_data={
                "estimation_amount": "125000",
                "estimation_currency": "usd",
            }
        ),
    )

    assert res.captured_data == {
        "estimation_completed": True,
        "estimation_amount": 125000.0,
        "estimation_currency": "USD",
    }

def test_stage_update_request_rejects_manual_progress_updates():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(progress=75)

    assert "Stage progress is derived truth and cannot be updated manually" in str(exc.value)

def test_stage_update_non_progress_allowed_with_subtasks():
    session = MockSession()
    session.filter_mock.count.return_value = 1
    ctrl = RfqStageController(MockStageDatasource(), MockRfqDatasource(), session)
    req = RfqStageUpdateRequest(
        blocker_status="Blocked",
        blocker_reason_code="waiting_client_input",
    )
    res = ctrl.update(RFQ1, ST1, req)
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "waiting_client_input"


def test_stage_update_request_rejects_blocked_without_reason():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(blocker_status="Blocked")

    assert "Please choose a blocker reason when marking the stage as blocked." in str(exc.value)


def test_stage_update_clears_blocker_reason_when_blocker_status_is_cleared():
    session = MockSession()
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Stage 1",
        progress=50,
        blocker_status="Blocked",
        blocker_reason_code="waiting_client_input",
        status="In preparation",
        order=1,
        assigned_team="Team A",
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), session)

    res = ctrl.update(RFQ1, ST1, RfqStageUpdateRequest(blocker_status=None))

    assert res.blocker_status is None
    assert res.blocker_reason_code is None


def test_stage_update_request_rejects_blocker_reason_without_blocker_status():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(blocker_reason_code="waiting_client_input")

    assert "blocker_reason_code requires blocker_status" in str(exc.value)


def test_stage_update_resolved_clears_blocker_reason():
    req = RfqStageUpdateRequest(
        blocker_status="Resolved",
        blocker_reason_code="waiting_client_input",
    )

    assert req.blocker_status == "Resolved"
    assert req.blocker_reason_code is None


def test_stage_update_request_canonicalizes_go_no_go_to_go():
    req = RfqStageUpdateRequest(captured_data={"go_nogo_decision": "Go"})

    assert req.captured_data == {"go_nogo_decision": "go"}


def test_stage_update_request_canonicalizes_legacy_proceed_to_go():
    req = RfqStageUpdateRequest(captured_data={"go_nogo_decision": "proceed"})

    assert req.captured_data == {"go_nogo_decision": "go"}


def test_stage_update_request_canonicalizes_go_no_go_to_no_go():
    req = RfqStageUpdateRequest(captured_data={"go_nogo_decision": "No-Go"})

    assert req.captured_data == {"go_nogo_decision": "no_go"}


def test_stage_update_request_rejects_invalid_go_no_go_value():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(captured_data={"go_nogo_decision": "maybe"})

    assert "Please choose Go or No-Go before continuing." in str(exc.value)


def test_stage_update_request_canonicalizes_design_approved_to_yes():
    req = RfqStageUpdateRequest(captured_data={"design_approved": True})

    assert req.captured_data == {"design_approved": "yes"}


def test_stage_update_request_canonicalizes_boq_completed_to_no():
    req = RfqStageUpdateRequest(
        captured_data={"boq_completed": "No"},
        blocker_reason_code="awaiting_supplier_takeoff",
    )

    assert req.captured_data == {"boq_completed": "no"}
    assert req.blocker_status == "Blocked"


def test_stage_update_request_normalizes_estimation_amount_and_defaults_currency():
    req = RfqStageUpdateRequest(
        captured_data={"estimation_amount": "125000.50"},
    )

    assert req.captured_data == {
        "estimation_completed": True,
        "estimation_amount": 125000.5,
        "estimation_currency": "SAR",
    }


def test_stage_update_request_rejects_invalid_estimation_amount():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(captured_data={"estimation_amount": "abc"})

    assert rfq_stage_translator.ESTIMATION_AMOUNT_VALIDATION_MESSAGE in str(exc.value)


def test_stage_update_request_normalizes_final_price_and_defaults_currency():
    req = RfqStageUpdateRequest(
        captured_data={"final_price": "971150"},
    )

    assert req.captured_data == {
        "final_price": 971150.0,
        "final_price_currency": "SAR",
    }


def test_stage_update_request_trims_approval_signature_reference():
    req = RfqStageUpdateRequest(
        captured_data={"approval_signature": "  APP-4481  "},
    )

    assert req.captured_data == {"approval_signature": "APP-4481"}


def test_stage_update_request_rejects_negative_design_decision_without_blocker_reason():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(captured_data={"design_approved": "No"})

    assert "Please choose a blocker reason when Design Approved is set to No." in str(exc.value)


def test_stage_update_auto_blocks_when_design_not_approved():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Preliminary design",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=4,
        mandatory_fields="design_approved",
        assigned_team="Engineering",
        captured_data={},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(
            captured_data={"design_approved": "No"},
            blocker_reason_code="awaiting_design_revision",
        ),
    )

    assert res.captured_data["design_approved"] == "no"
    assert (
        res.captured_data[rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD]
        == "design_approved"
    )
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "awaiting_design_revision"
    history_events = _get_history_events(res.captured_data)
    assert [event["type"] for event in history_events] == [
        "decision_recorded",
        "blocker_created",
    ]
    assert history_events[1]["reason"] == "awaiting_design_revision"
    assert history_events[1]["source"] == "automatic"


def test_stage_update_auto_blocks_when_boq_not_completed():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="BOQ / BOM preparation",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=5,
        mandatory_fields="boq_completed",
        assigned_team="Estimation",
        captured_data={},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(
            captured_data={"boq_completed": "No"},
            blocker_reason_code="missing_vendor_quantities",
        ),
    )

    assert res.captured_data["boq_completed"] == "no"
    assert (
        res.captured_data[rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD]
        == "boq_completed"
    )
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "missing_vendor_quantities"
    history_events = _get_history_events(res.captured_data)
    assert [event["type"] for event in history_events] == [
        "decision_recorded",
        "blocker_created",
    ]
    assert history_events[1]["reason"] == "missing_vendor_quantities"


def test_stage_update_yes_resolves_only_matching_auto_blocker_source():
    session = MockSession()
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Preliminary design",
        progress=50,
        blocker_status="Blocked",
        blocker_reason_code="awaiting_design_revision",
        status="In preparation",
        order=4,
        mandatory_fields="design_approved",
        assigned_team="Engineering",
        captured_data={
            "design_approved": "no",
            "workflow_auto_blocker_source": "design_approved",
        },
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), session)

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(captured_data={"design_approved": "Yes"}),
    )

    assert res.captured_data["design_approved"] == "yes"
    assert res.blocker_status == "Resolved"
    assert res.blocker_reason_code is None
    history_events = _get_history_events(res.captured_data)
    assert [event["type"] for event in history_events] == [
        "decision_recorded",
        "blocker_resolved",
    ]
    assert history_events[1]["reason"] == "awaiting_design_revision"
    assert history_events[1]["source"] == "automatic"


def test_stage_update_yes_does_not_resolve_manual_blocker_without_auto_source():
    session = MockSession()
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Preliminary design",
        progress=50,
        blocker_status="Blocked",
        blocker_reason_code="waiting_client_input",
        status="In preparation",
        order=4,
        mandatory_fields="design_approved",
        assigned_team="Engineering",
        captured_data={"design_approved": "no"},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), session)

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(captured_data={"design_approved": "Yes"}),
    )

    assert res.captured_data["design_approved"] == "yes"
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "waiting_client_input"
    history_events = _get_history_events(res.captured_data)
    assert [event["type"] for event in history_events] == ["decision_recorded"]


def test_stage_update_yes_does_not_resolve_auto_blocker_from_other_step():
    session = MockSession()
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Commercial review",
        progress=50,
        blocker_status="Blocked",
        blocker_reason_code="waiting_for_boq",
        status="In preparation",
        order=4,
        mandatory_fields="design_approved,boq_completed",
        assigned_team="Engineering",
        captured_data={
            "design_approved": "no",
            "boq_completed": "no",
            "workflow_auto_blocker_source": "boq_completed",
        },
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), session)

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(captured_data={"design_approved": "Yes"}),
    )

    assert res.captured_data["design_approved"] == "yes"
    assert res.captured_data["boq_completed"] == "no"
    assert (
        res.captured_data[rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD]
        == "boq_completed"
    )
    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "waiting_for_boq"
    history_events = _get_history_events(res.captured_data)
    assert [event["type"] for event in history_events] == ["decision_recorded"]


def test_stage_update_records_manual_blocker_history_with_actor_name():
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Clarifications",
        progress=50,
        blocker_status="None",
        status="In preparation",
        order=3,
        assigned_team="Estimation",
        captured_data={},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(
            blocker_status="Blocked",
            blocker_reason_code="waiting_client_input",
        ),
        actor_name="History Tester",
    )

    history_events = _get_history_events(res.captured_data)
    assert len(history_events) == 1
    assert history_events[0]["type"] == "blocker_created"
    assert history_events[0]["reason"] == "waiting_client_input"
    assert history_events[0]["source"] == "manual"
    assert history_events[0]["actor_name"] == "History Tester"


def test_stage_update_cannot_resolve_blocker_while_design_decision_remains_no():
    session = MockSession()
    stage_ds = MockStageDatasource()
    stage_ds.get_by_id = lambda _stage_id: RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        name="Preliminary design",
        progress=50,
        blocker_status="Blocked",
        blocker_reason_code="awaiting_design_revision",
        status="In preparation",
        order=4,
        mandatory_fields="design_approved",
        assigned_team="Engineering",
        captured_data={"design_approved": "no"},
    )
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), session)

    res = ctrl.update(
        RFQ1,
        ST1,
        RfqStageUpdateRequest(blocker_status="Resolved"),
    )

    assert res.blocker_status == "Blocked"
    assert res.blocker_reason_code == "awaiting_design_revision"


def test_stage_advance_request_trims_outcome_reason():
    req = RfqStageAdvanceRequest(confirm_no_go_cancel=True, outcome_reason="  Client withdrew scope  ")

    assert req.outcome_reason == "Client withdrew scope"


def test_stage_update_request_rejects_lost_terminal_outcome_without_reason():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(captured_data={"rfq_terminal_outcome": "lost"})

    assert "Please choose a lost reason before completing this RFQ as Lost." in str(exc.value)


def test_stage_update_request_rejects_lost_other_without_detail():
    with pytest.raises(ValidationError) as exc:
        RfqStageUpdateRequest(
            captured_data={
                "rfq_terminal_outcome": "lost",
                "rfq_lost_reason_code": "other",
            }
        )

    assert "Please enter the lost reason details when Other is selected." in str(exc.value)


def test_stage_update_request_normalizes_terminal_outcome_and_clears_stale_lost_reason():
    req = RfqStageUpdateRequest(
        captured_data={
            "rfq_terminal_outcome": "Awarded",
            "rfq_lost_reason_code": "commercial_gap",
        }
    )

    assert req.captured_data == {"rfq_terminal_outcome": "awarded"}


def test_stage_advance_request_normalizes_terminal_outcome_and_lost_reason():
    req = RfqStageAdvanceRequest(
        terminal_outcome="Lost",
        lost_reason_code="delivery schedule",
        outcome_reason="  Client needed an earlier ship date.  ",
    )

    assert req.terminal_outcome == "lost"
    assert req.lost_reason_code == "delivery_schedule"
    assert req.outcome_reason == "Client needed an earlier ship date."

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
    stage_ds.get_by_id = lambda id: RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="Blocked", blocker_reason_code="WAITING_CLIENT", assigned_team="Team A")
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    
    with pytest.raises(ConflictError):
        ctrl.advance(RFQ1, ST1, actor_team="Team A")

def test_advance_missing_mandatory():
    stage_ds = MockStageDatasource()
    stage = RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="None", mandatory_fields="po_number, value", captured_data={"po_number": "123"}, order=1, name="Stage 1", assigned_team="Team A")
    stage_ds.get_by_id = lambda id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())
    
    with pytest.raises(UnprocessableEntityError):
        ctrl.advance(RFQ1, ST1, actor_team="Team A")


def test_advance_missing_go_no_go_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="go_nogo_decision",
        captured_data={},
        order=1,
        name="Go / No-Go",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert "Please choose Go or No-Go before continuing." in str(exc.value)


def test_advance_missing_design_approved_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="design_approved",
        captured_data={},
        order=4,
        name="Preliminary design",
        assigned_team="Engineering",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(
            RFQ1,
            ST1,
            actor_team="Estimation",
            actor_permissions=["rfq_stage:advance"],
        )

    assert "Please choose Yes or No for Design Approved before continuing." in str(exc.value)


def test_advance_missing_boq_completed_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="boq_completed",
        captured_data={},
        order=5,
        name="BOQ / BOM preparation",
        assigned_team="Estimation",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Estimation")

    assert "Please choose Yes or No for BOQ Completed before continuing." in str(exc.value)


def test_advance_missing_estimation_amount_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="estimation_completed",
        captured_data={},
        order=7,
        name="Cost estimation",
        assigned_team="Estimation",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Estimation")

    assert rfq_stage_translator.ESTIMATION_AMOUNT_VALIDATION_MESSAGE in str(exc.value)


def test_advance_missing_final_price_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="final_price",
        captured_data={},
        order=9,
        name="Offer submission",
        assigned_team="Estimation",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Estimation")

    assert rfq_stage_translator.FINAL_PRICE_VALIDATION_MESSAGE in str(exc.value)


def test_advance_missing_approval_signature_uses_friendly_message():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="approval_signature",
        captured_data={},
        order=8,
        name="Internal approval",
        assigned_team="Estimation",
    )
    stage_ds.get_by_id = lambda _id: stage
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Estimation")

    assert rfq_stage_translator.APPROVAL_SIGNATURE_VALIDATION_MESSAGE in str(exc.value)


def test_advance_rejects_incomplete_active_subtasks_before_mutating_stage():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        progress=50,
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Stage 1",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=40)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    session.filter_mock.order_by.return_value.all.return_value = [
        Subtask(
            id=str(uuid.uuid4()),
            rfq_stage_id=ST1,
            name="Clarify scope",
            progress=30,
            status="In progress",
            created_at=datetime.now(),
        )
    ]

    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    with pytest.raises(ConflictError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert "All active subtasks must be completed before advancing this stage." in str(exc.value)
    assert stage.status == "In preparation"
    assert stage.progress == 50
    assert rfq.current_stage_id == ST1
    assert rfq.status == "In preparation"
    assert session.committed is False

def test_advance_success():
    stage_ds = MockStageDatasource()
    stage = RFQStage(id=ST1, rfq_id=RFQ1, status="In preparation", blocker_status="None", mandatory_fields="po_number", captured_data={"po_number": "123"}, order=1, name="Stage 1", assigned_team="Team A")
    stage_ds.get_by_id = lambda id: stage
    
    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda id: rfq
    
    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())
    
    ctrl.advance(RFQ1, ST1, actor_team="Team A")
    assert stage.status == "Completed"
    assert stage.progress == 100
    assert rfq.current_stage_id == ST2


def test_advance_allows_progression_when_all_active_subtasks_are_complete():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Stage 1",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    session.filter_mock.order_by.return_value.all.return_value = [
        Subtask(
            id=str(uuid.uuid4()),
            rfq_stage_id=ST1,
            name="Clarify scope",
            progress=100,
            status="Done",
            created_at=datetime.now(),
        )
    ]

    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert stage.status == "Completed"
    assert stage.progress == 100
    assert rfq.current_stage_id == ST2


def test_advance_go_no_go_with_go_allows_normal_progression():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="go_nogo_decision",
        captured_data={"go_nogo_decision": "go"},
        order=1,
        name="Go / No-Go",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=25)
    rfq_ds.get_by_id = lambda _id: rfq

    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())

    ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert stage.status == "Completed"
    assert stage.progress == 100
    assert rfq.current_stage_id == ST2


def test_advance_go_no_go_with_no_go_blocks_normal_progression():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        progress=40,
        blocker_status="None",
        mandatory_fields="go_nogo_decision",
        captured_data={"go_nogo_decision": "no_go"},
        order=1,
        name="Go / No-Go",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=40)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    with pytest.raises(ConflictError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert "requires confirmation to cancel the RFQ" in str(exc.value)
    assert stage.status == "In preparation"
    assert stage.progress == 40
    assert stage.actual_end is None
    assert rfq.current_stage_id == ST1
    assert rfq.status == "In preparation"
    assert rfq.progress == 40
    assert session.committed is False


def test_advance_go_no_go_with_confirmation_requires_reason():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        progress=40,
        blocker_status="None",
        mandatory_fields="go_nogo_decision",
        captured_data={"go_nogo_decision": "no_go"},
        order=1,
        name="Go / No-Go",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=40)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(
            RFQ1,
            ST1,
            request=RfqStageAdvanceRequest(confirm_no_go_cancel=True),
            actor_team="Team A",
        )

    assert "Please provide a cancellation reason for the No-Go decision." in str(exc.value)
    assert stage.status == "In preparation"
    assert rfq.status == "In preparation"
    assert session.committed is False


def test_advance_go_no_go_with_confirmation_cancels_rfq_and_preserves_history():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        progress=40,
        blocker_status="None",
        mandatory_fields="go_nogo_decision",
        captured_data={"go_nogo_decision": "no_go"},
        order=2,
        name="Go / No-Go",
        assigned_team="Team A",
        actual_end=None,
    )
    next_stage = RFQStage(
        id=ST2,
        rfq_id=RFQ1,
        status="Not Started",
        progress=0,
        order=3,
        name="Pre-bid clarifications",
        assigned_team="Team A",
    )
    completed_stage = RFQStage(
        id=str(uuid.uuid4()),
        rfq_id=RFQ1,
        status="Completed",
        progress=100,
        order=1,
        name="RFQ received",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.list_by_rfq = lambda _rfq_id: [completed_stage, stage, next_stage]

    rfq = RFQ(
        id=RFQ1,
        current_stage_id=ST1,
        status="In preparation",
        progress=40,
        outcome_reason=None,
    )

    class _Query:
        def filter_by(self, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return [completed_stage, stage, next_stage]

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    session = _TrackingSession()
    original_query = session.query

    def _session_query(model):
        if model is Subtask:
            return original_query(model)
        return _Query()

    session.query = _session_query

    class _RfqDatasource(MockRfqDatasource):
        def __init__(self):
            self.last_update_data = None

        def get_by_id(self, _rfq_id):
            return rfq

        def update(self, entity, data):
            self.last_update_data = dict(data)
            for key, value in data.items():
                setattr(entity, key, value)
            return entity

    rfq_ds = _RfqDatasource()
    bus = _TrackingEventBus()
    ctrl = RfqStageController(stage_ds, rfq_ds, session, event_bus_connector=bus)

    result = ctrl.advance(
        RFQ1,
        ST1,
        request=RfqStageAdvanceRequest(
            confirm_no_go_cancel=True,
            outcome_reason="Client declined to proceed after commercial review.",
        ),
        actor_team="Team A",
        actor_user_id="u-stage-1",
        actor_name="Stage Manager",
    )

    assert result.status == "Skipped"
    assert result.captured_data == {"go_nogo_decision": "no_go"}
    assert stage.status == "Skipped"
    assert stage.actual_end == date.today()
    assert next_stage.status == "Skipped"
    assert rfq.status == "Cancelled"
    assert rfq.current_stage_id is None
    assert rfq.outcome_reason == "Client declined to proceed after commercial review."
    assert rfq.progress == 100
    assert session.committed is True
    assert rfq_ds.last_update_data is not None
    assert rfq_ds.last_update_data["status"] == "Cancelled"
    assert any(call["event_type"] == "rfq.status_changed" for call in bus.calls)


def test_advance_last_stage_requires_explicit_terminal_outcome():
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
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=40)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert "Please choose Awarded or Lost before completing this RFQ." in str(exc.value)
    assert stage.status == "In preparation"
    assert rfq.status == "In preparation"
    assert rfq.progress == 40
    assert rfq.current_stage_id == ST1
    assert session.committed is False


def test_advance_last_stage_awarded_updates_rfq_terminal_truth():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        blocker_status="None",
        mandatory_fields=None,
        captured_data={},
        order=5,
        name="Award / Lost",
        assigned_team="Team A",
        actual_end=None,
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=88)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    bus = _TrackingEventBus()
    ctrl = RfqStageController(stage_ds, rfq_ds, session, event_bus_connector=bus)

    result = ctrl.advance(
        RFQ1,
        ST1,
        actor_team="Team A",
        request=RfqStageAdvanceRequest(terminal_outcome="awarded"),
        actor_user_id="u-final-1",
        actor_name="Closer",
    )

    assert result.status == "Completed"
    assert result.captured_data["rfq_terminal_outcome"] == "awarded"
    assert stage.status == "Completed"
    assert stage.progress == 100
    assert stage.actual_end == date.today()
    assert rfq.status == "Awarded"
    assert rfq.current_stage_id is None
    assert rfq.progress == 100
    assert rfq.outcome_reason is None
    assert session.committed is True
    history_events = _get_history_events(result.captured_data)
    assert history_events[-1]["type"] == "terminal_outcome_recorded"
    assert history_events[-1]["value"] == "awarded"
    assert history_events[-1]["actor_name"] == "Closer"
    assert any(call["event_type"] == "rfq.status_changed" for call in bus.calls)
    assert any(call["event_type"] == "stage.advanced" for call in bus.calls)


def test_advance_last_stage_does_not_duplicate_existing_terminal_outcome_history_event():
    stage_ds = MockStageDatasource()
    existing_event = {
        "id": "evt-1",
        "type": "terminal_outcome_recorded",
        "at": "2026-01-01T00:00:00Z",
        "field_key": "rfq_terminal_outcome",
        "value": "awarded",
        "actor_name": "Closer",
    }
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        blocker_status="None",
        mandatory_fields=None,
        captured_data={
            "rfq_terminal_outcome": "awarded",
            "workflow_history_events": [existing_event],
        },
        order=5,
        name="Award / Lost",
        assigned_team="Team A",
        actual_end=None,
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=88)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    result = ctrl.advance(
        RFQ1,
        ST1,
        actor_team="Team A",
        request=RfqStageAdvanceRequest(terminal_outcome="awarded"),
        actor_name="Closer",
    )

    history_events = _get_history_events(result.captured_data)
    assert len(history_events) == 1
    assert history_events[0]["type"] == "terminal_outcome_recorded"
    assert history_events[0]["value"] == "awarded"


def test_advance_last_stage_lost_requires_reason():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        blocker_status="None",
        mandatory_fields=None,
        captured_data={"rfq_terminal_outcome": "lost"},
        order=5,
        name="Award / Lost",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=88)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    with pytest.raises(UnprocessableEntityError) as exc:
        ctrl.advance(
            RFQ1,
            ST1,
            actor_team="Team A",
            request=RfqStageAdvanceRequest(),
        )

    assert "Please choose a lost reason before completing this RFQ as Lost." in str(exc.value)
    assert stage.status == "In Progress"
    assert rfq.status == "In preparation"
    assert session.committed is False


def test_advance_last_stage_lost_updates_rfq_status_and_reason():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        blocker_status="None",
        mandatory_fields=None,
        captured_data={},
        order=5,
        name="Award / Lost",
        assigned_team="Team A",
        actual_end=None,
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=88)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    result = ctrl.advance(
        RFQ1,
        ST1,
        actor_team="Team A",
        request=RfqStageAdvanceRequest(
            terminal_outcome="lost",
            lost_reason_code="commercial_gap",
        ),
    )

    assert result.status == "Completed"
    assert result.captured_data["rfq_terminal_outcome"] == "lost"
    assert result.captured_data["rfq_lost_reason_code"] == "commercial_gap"
    assert stage.status == "Completed"
    assert stage.actual_end == date.today()
    assert rfq.status == "Lost"
    assert rfq.current_stage_id is None
    assert rfq.progress == 100
    assert rfq.outcome_reason == "Commercial competitiveness"
    assert session.committed is True
    history_events = _get_history_events(result.captured_data)
    assert history_events[-1]["type"] == "terminal_outcome_recorded"
    assert history_events[-1]["reason"] == "Commercial competitiveness"


def test_advance_last_stage_lost_with_other_reason_detail_updates_terminal_truth():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In Progress",
        blocker_status="None",
        mandatory_fields=None,
        captured_data={
            "rfq_terminal_outcome": "lost",
            "rfq_lost_reason_code": "other",
            "rfq_lost_reason_other": "Customer merged this scope into another package",
        },
        order=5,
        name="Award / Lost",
        assigned_team="Team A",
        actual_end=None,
    )
    stage_ds.get_by_id = lambda _id: stage
    stage_ds.get_next_stage = lambda _rfq_id, _order: None

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", progress=88)
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session)

    result = ctrl.advance(
        RFQ1,
        ST1,
        actor_team="Team A",
        request=RfqStageAdvanceRequest(
            terminal_outcome="lost",
            lost_reason_code="other",
        ),
    )

    assert result.status == "Completed"
    assert result.captured_data["rfq_terminal_outcome"] == "lost"
    assert result.captured_data["rfq_lost_reason_code"] == "other"
    assert (
        result.captured_data["rfq_lost_reason_other"]
        == "Customer merged this scope into another package"
    )
    assert stage.status == "Completed"
    assert rfq.status == "Lost"
    assert rfq.current_stage_id is None
    assert rfq.progress == 100
    assert (
        rfq.outcome_reason
        == "Other: Customer merged this scope into another package"
    )
    assert session.committed is True
    history_events = _get_history_events(result.captured_data)
    assert history_events[-1]["type"] == "terminal_outcome_recorded"
    assert (
        history_events[-1]["reason"]
        == "Other: Customer merged this scope into another package"
    )


def test_advance_rejects_wrong_team_with_forbidden_error():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Stage 1",
        assigned_team="Engineering",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda _id: rfq

    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())

    from src.utils.errors import ForbiddenError

    with pytest.raises(ForbiddenError) as exc:
        ctrl.advance(RFQ1, ST1, actor_team="Sales")

    assert "does not match assigned team" in str(exc.value)


def test_advance_allows_cross_team_with_explicit_stage_advance_permission():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Preliminary design",
        assigned_team="Engineering",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda _id: rfq

    ctrl = RfqStageController(stage_ds, rfq_ds, MockSession())

    ctrl.advance(
        RFQ1,
        ST1,
        actor_team="Estimation",
        actor_permissions=["rfq_stage:advance"],
    )

    assert stage.status == "Completed"
    assert stage.progress == 100
    assert rfq.current_stage_id == ST2


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

    assert rfq.progress == 50


def test_update_rfq_progress_does_not_grant_partial_credit_for_active_stage():
    stage_ds = MockStageDatasource()
    stage_ds.list_by_rfq = lambda _rfq_id: [
        RFQStage(id=ST1, rfq_id=RFQ1, status="Completed", progress=100, order=1, name="A"),
        RFQStage(id=ST2, rfq_id=RFQ1, status="In Progress", progress=95, order=2, name="B"),
        RFQStage(id=str(uuid.uuid4()), rfq_id=RFQ1, status="Not Started", progress=0, order=3, name="C"),
    ]

    rfq = RFQ(id=RFQ1, current_stage_id=ST2, status="In preparation", progress=0)
    ctrl = RfqStageController(stage_ds, MockRfqDatasource(), MockSession())

    ctrl._update_rfq_progress(rfq)

    assert rfq.progress == 33


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


class _TrackingSession(MockSession):
    def __init__(self):
        super().__init__()
        self.committed = False

    def commit(self):
        self.committed = True


class _TrackingEventBus:
    def __init__(self, on_publish=None):
        self.calls = []
        self.on_publish = on_publish

    def publish(self, event_type, payload, metadata):
        if self.on_publish:
            self.on_publish(event_type, payload, metadata)
        self.calls.append({"event_type": event_type, "payload": payload, "metadata": metadata})


def test_advance_publishes_stage_advanced_after_commit_with_metadata():
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Stage 1",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation", rfq_code="IF-1001")
    rfq_ds.get_by_id = lambda _id: rfq

    session = _TrackingSession()

    def _assert_commit_happened(_event_type, _payload, _metadata):
        assert session.committed is True

    bus = _TrackingEventBus(on_publish=_assert_commit_happened)
    ctrl = RfqStageController(stage_ds, rfq_ds, session, event_bus_connector=bus)

    token = request_id_context.set("req-h4-stage-12345678")
    try:
        ctrl.advance(
            RFQ1,
            ST1,
            actor_team="Team A",
            actor_user_id="u-adv-1",
            actor_name="Advancer",
        )
    finally:
        request_id_context.reset(token)

    assert len(bus.calls) == 1
    call = bus.calls[0]
    assert call["event_type"] == "stage.advanced"
    assert call["payload"]["stage_id"] == ST1
    assert call["payload"]["new_stage_status"] == "Completed"
    assert call["metadata"]["request_id"] == "req-h4-stage-12345678"
    assert call["metadata"]["actor_user_id"] == "u-adv-1"


def test_advance_event_publish_failure_is_non_blocking_and_logged(caplog):
    stage_ds = MockStageDatasource()
    stage = RFQStage(
        id=ST1,
        rfq_id=RFQ1,
        status="In preparation",
        blocker_status="None",
        mandatory_fields="po_number",
        captured_data={"po_number": "123"},
        order=1,
        name="Stage 1",
        assigned_team="Team A",
    )
    stage_ds.get_by_id = lambda _id: stage

    rfq_ds = MockRfqDatasource()
    rfq = RFQ(id=RFQ1, current_stage_id=ST1, status="In preparation")
    rfq_ds.get_by_id = lambda _id: rfq

    class _FailingEventBus:
        def publish(self, _event_type, _payload, _metadata):
            raise RuntimeError("event bus unavailable")

    session = _TrackingSession()
    ctrl = RfqStageController(stage_ds, rfq_ds, session, event_bus_connector=_FailingEventBus())

    result = ctrl.advance(RFQ1, ST1, actor_team="Team A")

    assert result.status == "Completed"
    assert session.committed is True
    assert any("event_publish_failed" in record.message for record in caplog.records)

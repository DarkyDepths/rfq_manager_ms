import pytest
import uuid
from src.controllers.workflow_controller import WorkflowController
from src.utils.errors import NotFoundError
from src.translators.workflow_translator import WorkflowUpdateRequest

U1 = str(uuid.uuid4())
U2 = str(uuid.uuid4())

class MockWorkflowDatasource:
    @staticmethod
    def _build_workflow(
        workflow_id,
        name,
        code,
        is_active,
        is_default,
        *,
        selection_mode="fixed",
        base_workflow_id=None,
        base_workflow=None,
        stages=None,
    ):
        workflow = type("Workflow", (), {})()
        workflow.id = workflow_id
        workflow.name = name
        workflow.code = code
        workflow.description = None
        workflow.is_active = is_active
        workflow.is_default = is_default
        workflow.selection_mode = selection_mode
        workflow.base_workflow_id = base_workflow_id
        workflow.base_workflow = base_workflow
        workflow.stages = stages or []
        return workflow

    def list_all(self):
        base_stage = type(
            "StageTemplate",
            (),
            {
                "id": uuid.uuid4(),
                "name": "RFQ received",
                "order": 1,
                "default_team": "Estimation",
                "planned_duration_days": 2,
                "is_required": True,
            },
        )()
        w1 = self._build_workflow(
            U1,
            "WF 1",
            "W1",
            True,
            True,
            stages=[base_stage],
        )
        w2 = self._build_workflow(
            U2,
            "WF 2",
            "W2",
            False,
            False,
            selection_mode="customizable",
            base_workflow_id=w1.id,
            base_workflow=w1,
            stages=[],
        )
        return [w1, w2]
        
    def get_by_id(self, wf_id):
        if str(wf_id) == U1:
            stage = type(
                "StageTemplate",
                (),
                {
                    "id": uuid.uuid4(),
                    "name": "RFQ received",
                    "order": 1,
                    "default_team": "Estimation",
                    "planned_duration_days": 2,
                    "is_required": True,
                },
            )()
            return self._build_workflow(
                U1,
                "WF 1",
                "W1",
                True,
                True,
                stages=[stage],
            )
        if str(wf_id) == U2:
            base_stage = type(
                "StageTemplate",
                (),
                {
                    "id": uuid.uuid4(),
                    "name": "RFQ received",
                    "order": 1,
                    "default_team": "Estimation",
                    "planned_duration_days": 2,
                    "is_required": True,
                },
            )()
            base = self._build_workflow(
                U1,
                "WF 1",
                "W1",
                True,
                True,
                stages=[base_stage],
            )
            return self._build_workflow(
                U2,
                "WF 2",
                "W2",
                False,
                False,
                selection_mode="customizable",
                base_workflow_id=U1,
                base_workflow=base,
                stages=[],
            )
        return None
        
    def clear_default(self):
        self.default_cleared = True
        
    def update(self, wf, update_data):
        for k, v in update_data.items():
            setattr(wf, k, v)
        return wf

class MockSession:
    def commit(self): pass
    def refresh(self, obj): pass

def test_workflow_list():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())
    
    result = ctrl.list()
    assert len(result["data"]) == 2
    assert result["data"][0].name == "WF 1"
    assert result["data"][1].name == "WF 2"

def test_workflow_get_success():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())
    
    result = ctrl.get(U1)
    assert result.name == "WF 1"
    assert result.selection_mode == "fixed"
    assert result.stage_count == 1


def test_workflow_get_customizable_uses_base_stage_catalog():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())

    result = ctrl.get(U2)

    assert result.selection_mode == "customizable"
    assert str(result.base_workflow_id) == U1
    assert result.stage_count == 1
    assert result.stages[0].name == "RFQ received"
    assert result.stages[0].is_required is True

def test_workflow_get_not_found():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())
    
    with pytest.raises(NotFoundError):
        ctrl.get(str(uuid.uuid4()))

def test_workflow_update_is_default_logic():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())
    
    request = WorkflowUpdateRequest(is_default=True)
    result = ctrl.update(U1, request)
    
    # Assert datasource.clear_default was called
    assert getattr(ds, "default_cleared", False) is True
    assert result.is_default is True

def test_workflow_update_not_found():
    ds = MockWorkflowDatasource()
    ctrl = WorkflowController(datasource=ds, session=MockSession())
    
    request = WorkflowUpdateRequest(name="New Name")
    with pytest.raises(NotFoundError):
        ctrl.update(str(uuid.uuid4()), request)

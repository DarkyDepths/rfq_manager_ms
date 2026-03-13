import pytest
import uuid
from src.controllers.workflow_controller import WorkflowController
from src.models.workflow import Workflow
from src.utils.errors import NotFoundError
from src.translators.workflow_translator import WorkflowUpdateRequest

U1 = str(uuid.uuid4())
U2 = str(uuid.uuid4())

class MockWorkflowDatasource:
    def list_all(self):
        w1 = Workflow(id=U1, name="WF 1", code="W1", is_active=True, is_default=True)
        w2 = Workflow(id=U2, name="WF 2", code="W2", is_active=False, is_default=False)
        return [w1, w2]
        
    def get_by_id(self, wf_id):
        if str(wf_id) == U1:
            return Workflow(id=U1, name="WF 1", code="W1", is_active=True, is_default=True)
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

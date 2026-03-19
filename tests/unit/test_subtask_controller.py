import pytest
import uuid
from datetime import datetime
from src.controllers.subtask_controller import SubtaskController
from src.models.subtask import Subtask
from src.models.rfq_stage import RFQStage
from src.utils.errors import NotFoundError
from src.translators.subtask_translator import SubtaskCreateRequest, SubtaskUpdateRequest

RFQ1 = str(uuid.uuid4())
ST1 = str(uuid.uuid4())
S1_ID = str(uuid.uuid4())
S2_ID = str(uuid.uuid4())

class MockSubtaskDatasource:
    def __init__(self, subtasks=None):
        self.subtasks = subtasks or []
        self.deleted = []
        
    def create(self, data):
        s = Subtask(**data, id=str(uuid.uuid4()), progress=0, status="Open", created_at=datetime.now())
        self.subtasks.append(s)
        return s
        
    def list_by_stage(self, stage_id):
        return [s for s in self.subtasks if s.rfq_stage_id == stage_id]
        
    def get_by_id(self, subtask_id):
        for s in self.subtasks:
            if s.id == subtask_id:
                return s
        for s in self.deleted:
            if s.id == subtask_id:
                return s
        return None
        
    def update(self, subtask, update_data):
        for k, v in update_data.items():
            setattr(subtask, k, v)
        return subtask
        
    def soft_delete(self, subtask):
        self.subtasks = [s for s in self.subtasks if s.id != subtask.id]
        self.deleted.append(subtask)

class MockStageDatasource:
    def __init__(self, stages=None):
        self.stages = stages or []
        
    def get_by_id(self, stage_id):
        return next((s for s in self.stages if s.id == stage_id), None)

class MockSession:
    def commit(self): pass
    def flush(self): pass

def test_subtask_create():
    stage_ds = MockStageDatasource([RFQStage(id=ST1, rfq_id=RFQ1)])
    subtask_ds = MockSubtaskDatasource()
    ctrl = SubtaskController(datasource=subtask_ds, stage_datasource=stage_ds, session=MockSession())
    
    req = SubtaskCreateRequest(name="Task 1", assigned_to="User 1")
    result = ctrl.create(RFQ1, ST1, req)
    
    assert result.name == "Task 1"
    assert result.rfq_stage_id == uuid.UUID(ST1)
    assert len(subtask_ds.subtasks) == 1

def test_subtask_create_stage_not_found():
    stage_ds = MockStageDatasource([])
    subtask_ds = MockSubtaskDatasource()
    ctrl = SubtaskController(datasource=subtask_ds, stage_datasource=stage_ds, session=MockSession())
    
    req = SubtaskCreateRequest(name="Task 1", assigned_to="User 1")
    with pytest.raises(NotFoundError):
        ctrl.create(RFQ1, str(uuid.uuid4()), req)

def test_subtask_list():
    stage_ds = MockStageDatasource([RFQStage(id=ST1, rfq_id=RFQ1)])
    subtask_ds = MockSubtaskDatasource([
        Subtask(id=S1_ID, rfq_stage_id=ST1, name="Task 1", progress=0, status="Open", created_at=datetime.now()),
        Subtask(id=S2_ID, rfq_stage_id=ST1, name="Task 2", progress=50, status="Open", created_at=datetime.now())
    ])
    ctrl = SubtaskController(datasource=subtask_ds, stage_datasource=stage_ds, session=MockSession())
    
    res = ctrl.list(RFQ1, ST1)
    assert len(res["data"]) == 2

def test_subtask_update_and_rollup():
    stage = RFQStage(id=ST1, rfq_id=RFQ1, progress=0)
    stage_ds = MockStageDatasource([stage])
    subtask_ds = MockSubtaskDatasource([
        Subtask(id=S1_ID, rfq_stage_id=ST1, name="Task 1", progress=100, status="Completed", created_at=datetime.now()),
        Subtask(id=S2_ID, rfq_stage_id=ST1, name="Task 2", progress=0, status="Open", created_at=datetime.now())
    ])
    ctrl = SubtaskController(datasource=subtask_ds, stage_datasource=stage_ds, session=MockSession())
    
    req = SubtaskUpdateRequest(progress=100)
    res = ctrl.update(RFQ1, ST1, S2_ID, req)
    
    assert res.progress == 100
    # Rollup average should be (100 + 100) // 2 = 100
    assert stage.progress == 99

def test_subtask_delete_and_rollup():
    stage = RFQStage(id=ST1, rfq_id=RFQ1, progress=50)
    stage_ds = MockStageDatasource([stage])
    s1 = Subtask(id=S1_ID, rfq_stage_id=ST1, name="Task 1", progress=100, status="Completed", created_at=datetime.now())
    s2 = Subtask(id=S2_ID, rfq_stage_id=ST1, name="Task 2", progress=0, status="Open", created_at=datetime.now())
    
    subtask_ds = MockSubtaskDatasource([s1, s2])
    ctrl = SubtaskController(datasource=subtask_ds, stage_datasource=stage_ds, session=MockSession())
    
    # After deleting s2, only s1 exists with 100% progress, so average is 100
    ctrl.delete(RFQ1, ST1, S2_ID)
    
    assert len(subtask_ds.subtasks) == 1
    assert len(subtask_ds.deleted) == 1
    assert stage.progress == 99

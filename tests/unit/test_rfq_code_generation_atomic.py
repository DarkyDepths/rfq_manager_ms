from datetime import date

from src.datasources.rfq_datasource import RfqDatasource
from src.models.rfq import RFQ
from src.models.workflow import Workflow


def _create_workflow(db_session, code: str = "WF-LG06") -> Workflow:
    workflow = Workflow(name="LG-06 Workflow", code=code, description="test workflow")
    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)
    return workflow


def _insert_rfq_with_code(db_session, workflow_id, rfq_code: str) -> RFQ:
    rfq = RFQ(
        name=f"RFQ {rfq_code}",
        client="Client",
        deadline=date(2030, 1, 1),
        owner="Owner",
        workflow_id=workflow_id,
        rfq_code=rfq_code,
        status="In preparation",
        progress=0,
        priority="normal",
    )
    db_session.add(rfq)
    db_session.commit()
    db_session.refresh(rfq)
    return rfq


def test_atomic_code_generation_returns_expected_format_and_unique_monotonic_values(db_session):
    _create_workflow(db_session)
    ds = RfqDatasource(db_session)

    code_1 = ds.get_next_code("IF")
    code_2 = ds.get_next_code("IF")
    code_3 = ds.get_next_code("IF")

    assert code_1 == "IF-0001"
    assert code_2 == "IF-0002"
    assert code_3 == "IF-0003"
    assert len({code_1, code_2, code_3}) == 3


def test_atomic_code_generation_bootstraps_from_existing_rfq_data(db_session):
    workflow = _create_workflow(db_session, code="WF-LG06-BOOT")
    _insert_rfq_with_code(db_session, workflow.id, "IF-0006")
    _insert_rfq_with_code(db_session, workflow.id, "IF-0002")
    _insert_rfq_with_code(db_session, workflow.id, "IB-0009")

    ds = RfqDatasource(db_session)

    assert ds.get_next_code("IF") == "IF-0007"
    assert ds.get_next_code("IB") == "IB-0010"


def test_atomic_code_generation_no_longer_tracks_table_max_after_counter_initialization(db_session):
    workflow = _create_workflow(db_session, code="WF-LG06-NOMAX")
    _insert_rfq_with_code(db_session, workflow.id, "IF-0003")

    ds = RfqDatasource(db_session)

    assert ds.get_next_code("IF") == "IF-0004"

    _insert_rfq_with_code(db_session, workflow.id, "IF-9999")

    # Counter-based allocation must continue from counter state, not table max value.
    assert ds.get_next_code("IF") == "IF-0005"

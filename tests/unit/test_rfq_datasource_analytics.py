from datetime import date, datetime, timezone
import uuid

from src.datasources.rfq_datasource import RfqDatasource
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow


def test_get_stats_uses_terminal_stage_end_dates_for_cycle_time(db_session):
    workflow_id = uuid.uuid4()
    db_session.add(
        Workflow(
            id=workflow_id,
            name="Analytics Workflow",
            code="AN-WF",
            is_active=True,
            is_default=False,
        )
    )

    awarded_rfq = RFQ(
        id=uuid.uuid4(),
        name="Awarded RFQ",
        client="Client A",
        deadline=date(2030, 1, 20),
        owner="Owner A",
        workflow_id=workflow_id,
        status="Awarded",
        progress=100,
        rfq_code="IF-2001",
        created_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2030, 1, 30, tzinfo=timezone.utc),
    )
    lost_rfq = RFQ(
        id=uuid.uuid4(),
        name="Lost RFQ",
        client="Client B",
        deadline=date(2030, 1, 25),
        owner="Owner B",
        workflow_id=workflow_id,
        status="Lost",
        progress=100,
        rfq_code="IF-2002",
        created_at=datetime(2030, 1, 2, tzinfo=timezone.utc),
        updated_at=datetime(2030, 2, 15, tzinfo=timezone.utc),
    )
    db_session.add_all([awarded_rfq, lost_rfq])
    db_session.flush()

    db_session.add_all(
        [
            RFQStage(
                id=uuid.uuid4(),
                rfq_id=awarded_rfq.id,
                name="Final",
                order=1,
                status="Completed",
                progress=100,
                actual_end=date(2030, 1, 11),
            ),
            RFQStage(
                id=uuid.uuid4(),
                rfq_id=lost_rfq.id,
                name="Final",
                order=1,
                status="Completed",
                progress=100,
                actual_end=date(2030, 1, 12),
            ),
        ]
    )
    db_session.commit()

    stats = RfqDatasource(db_session).get_stats()

    assert stats["avg_cycle_days"] == 10


def test_get_stats_counts_only_in_preparation_as_open(db_session):
    workflow_id = uuid.uuid4()
    db_session.add(
        Workflow(
            id=workflow_id,
            name="Lifecycle Workflow",
            code="LC-WF",
            is_active=True,
            is_default=False,
        )
    )
    db_session.add_all(
        [
            RFQ(
                id=uuid.uuid4(),
                name="Open RFQ",
                client="Client A",
                deadline=date(2030, 1, 20),
                owner="Owner A",
                workflow_id=workflow_id,
                status="In preparation",
                priority="critical",
                progress=10,
                rfq_code="IF-2100",
            ),
            RFQ(
                id=uuid.uuid4(),
                name="Legacy Submitted RFQ",
                client="Client B",
                deadline=date(2030, 1, 21),
                owner="Owner B",
                workflow_id=workflow_id,
                status="Submitted",
                priority="critical",
                progress=90,
                rfq_code="IF-2101",
            ),
        ]
    )
    db_session.commit()

    stats = RfqDatasource(db_session).get_stats()

    assert stats["open_rfqs"] == 1
    assert stats["critical_rfqs"] == 1


def test_get_analytics_returns_null_for_unavailable_margin_metrics(db_session):
    workflow_id = uuid.uuid4()
    db_session.add(
        Workflow(
            id=workflow_id,
            name="Analytics Workflow",
            code="AN-WF",
            is_active=True,
            is_default=False,
        )
    )
    db_session.add_all(
        [
            RFQ(
                id=uuid.uuid4(),
                name="Awarded RFQ",
                client="Client A",
                deadline=date(2030, 1, 20),
                owner="Owner A",
                workflow_id=workflow_id,
                status="Awarded",
                progress=100,
                rfq_code="IF-2010",
            ),
            RFQ(
                id=uuid.uuid4(),
                name="Lost RFQ",
                client="Client A",
                deadline=date(2030, 1, 22),
                owner="Owner B",
                workflow_id=workflow_id,
                status="Lost",
                progress=100,
                rfq_code="IF-2011",
            ),
        ]
    )
    db_session.commit()

    analytics = RfqDatasource(db_session).get_analytics()

    assert analytics["win_rate"] == 50.0
    assert analytics["avg_margin_submitted"] is None
    assert analytics["avg_margin_awarded"] is None
    assert analytics["estimation_accuracy"] is None
    assert analytics["by_client"][0]["avg_margin"] is None

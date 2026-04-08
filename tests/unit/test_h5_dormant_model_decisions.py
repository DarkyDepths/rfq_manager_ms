from datetime import date

from src.controllers.rfq_controller import RfqController
from src.controllers.rfq_stage_controller import RfqStageController
from src.datasources.rfq_datasource import RfqDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.datasources.workflow_datasource import WorkflowDatasource
from src.models.rfq import RFQ
from src.models.rfq_history import RFQHistory
from src.models.rfq_stage import RFQStage
from src.models.rfq_stage_field_value import RFQStageFieldValue
from src.models.workflow import StageTemplate, Workflow
from src.translators.rfq_stage_translator import RfqStageAdvanceRequest, RfqStageUpdateRequest
from src.translators.rfq_translator import RfqCreateRequest, RfqUpdateRequest


def _create_workflow_with_stage(db_session) -> Workflow:
    workflow = Workflow(name="H5 Workflow", code="WF-H5", description="Dormant model decision test")
    db_session.add(workflow)
    db_session.flush()

    stage_template = StageTemplate(
        workflow_id=workflow.id,
        name="Stage 1",
        order=1,
        default_team="Engineering",
        planned_duration_days=5,
        mandatory_fields=None,
    )
    db_session.add(stage_template)
    db_session.commit()
    db_session.refresh(workflow)
    return workflow


def _build_controllers(db_session):
    rfq_ds = RfqDatasource(db_session)
    stage_ds = RfqStageDatasource(db_session)
    workflow_ds = WorkflowDatasource(db_session)

    rfq_ctrl = RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=workflow_ds,
        rfq_stage_datasource=stage_ds,
        session=db_session,
        event_bus_connector=None,
    )
    stage_ctrl = RfqStageController(
        stage_datasource=stage_ds,
        rfq_datasource=rfq_ds,
        session=db_session,
        event_bus_connector=None,
    )
    return rfq_ctrl, stage_ctrl


def test_v1_stage_form_source_of_truth_remains_captured_data(db_session):
    workflow = _create_workflow_with_stage(db_session)
    rfq_ctrl, stage_ctrl = _build_controllers(db_session)

    created = rfq_ctrl.create(
        RfqCreateRequest(
            name="H5 RFQ",
            client="Client",
            deadline=date(2030, 1, 1),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="normal",
            workflow_id=workflow.id,
            code_prefix="IF",
        )
    )

    stage = db_session.query(RFQStage).filter(RFQStage.rfq_id == created.id).first()
    assert stage is not None

    stage_ctrl.update(
        created.id,
        stage.id,
        RfqStageUpdateRequest(captured_data={"margin": 18.5, "currency": "USD"}),
    )

    refreshed_stage = db_session.query(RFQStage).filter(RFQStage.id == stage.id).first()
    assert refreshed_stage.captured_data == {"margin": 18.5, "currency": "USD"}
    assert db_session.query(RFQStageFieldValue).count() == 0


def test_controller_flows_do_not_persist_dormant_tables_in_v1(db_session):
    workflow = _create_workflow_with_stage(db_session)
    rfq_ctrl, stage_ctrl = _build_controllers(db_session)

    created = rfq_ctrl.create(
        RfqCreateRequest(
            name="H5 RFQ",
            client="Client",
            deadline=date(2030, 2, 1),
            industry="Industrial Systems",
            owner="Owner",
            country="Saudi Arabia",
            priority="normal",
            workflow_id=workflow.id,
            code_prefix="IF",
        )
    )

    rfq_ctrl.update(created.id, RfqUpdateRequest(deadline=date(2030, 2, 15)))

    rfq_row = db_session.query(RFQ).filter(RFQ.id == created.id).first()
    stage = db_session.query(RFQStage).filter(RFQStage.rfq_id == created.id).first()
    stage_ctrl.advance(
        rfq_row.id,
        stage.id,
        actor_team="Engineering",
        request=RfqStageAdvanceRequest(terminal_outcome="awarded"),
    )

    assert db_session.query(RFQHistory).count() == 0
    assert db_session.query(RFQStageFieldValue).count() == 0

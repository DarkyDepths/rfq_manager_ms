import re

from scripts.bootstrap_base_data import seed_base_data
from scripts.seed_rfqmgmt_scenarios import seed_manager_scenarios
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow, StageTemplate


def _prepare_seed_context(db_session):
    seed_base_data(db_session)
    wf_long = db_session.query(Workflow).filter_by(code="GHI-LONG").first()
    wf_short = db_session.query(Workflow).filter_by(code="GHI-SHORT").first()
    wf_custom = db_session.query(Workflow).filter_by(code="GHI-CUSTOM").first()
    assert wf_long is not None
    assert wf_short is not None
    assert wf_custom is not None
    return wf_long, wf_short, wf_custom


def test_seeded_scenarios_use_runtime_codes_and_stage_template_ids(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfqs = db_session.query(RFQ).all()
    assert rfqs

    code_pattern = re.compile(r"^(IF|IB)-\d{4}$")
    assert all(rfq.rfq_code and code_pattern.match(rfq.rfq_code) for rfq in rfqs)

    stages = db_session.query(RFQStage).all()
    assert stages

    for stage in stages:
        assert stage.stage_template_id is not None
        template = db_session.query(StageTemplate).filter(StageTemplate.id == stage.stage_template_id).one()
        assert template.name == stage.name


def test_seeded_terminal_scenarios_clear_current_stage_pointer(db_session):
    seed_manager_scenarios(db_session, batch="all")

    terminal_rfqs = (
        db_session.query(RFQ)
        .filter(RFQ.status.in_(["Awarded", "Lost", "Cancelled"]))
        .all()
    )

    assert terminal_rfqs
    assert all(rfq.current_stage_id is None for rfq in terminal_rfqs)
    assert all(rfq.progress == 100 for rfq in terminal_rfqs)


def test_seed_base_data_adds_customizable_workflow_and_short_go_no_go_stage(db_session):
    wf_long, wf_short, wf_custom = _prepare_seed_context(db_session)

    short_stage_names = [stage.name for stage in sorted(wf_short.stages, key=lambda stage: stage.order)]
    assert short_stage_names == [
        "RFQ received",
        "Go / No-Go",
        "Cost estimation",
        "Internal approval",
        "Offer submission",
        "Award / Lost",
    ]
    assert wf_custom.selection_mode == "customizable"
    assert wf_custom.base_workflow_id == wf_long.id
    assert wf_custom.stages == []

    required_long_stage_names = {
        stage.name
        for stage in wf_long.stages
        if stage.is_required
    }
    assert required_long_stage_names == {
        "RFQ received",
        "Go / No-Go",
        "Award / Lost",
    }

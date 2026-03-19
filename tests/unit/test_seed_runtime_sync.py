import random
import re
from pathlib import Path

from faker import Faker

from scripts.seed import seed_base_data, generate_scenario
from src.models.rfq import RFQ
from src.models.rfq_stage import RFQStage
from src.models.workflow import Workflow, StageTemplate


def _prepare_seed_context(db_session):
    seed_base_data(db_session)
    wf_long = db_session.query(Workflow).filter_by(code="GHI-LONG").first()
    wf_short = db_session.query(Workflow).filter_by(code="GHI-SHORT").first()
    assert wf_long is not None
    assert wf_short is not None
    return wf_long, wf_short


def test_seed_script_no_longer_assigns_phantom_blocker_description():
    seed_source = Path("scripts/seed.py").read_text(encoding="utf-8")
    assert "blocker_description" not in seed_source


def test_seeded_rfq_codes_and_stage_template_ids_match_runtime_truth(db_session):
    random.seed(7)
    Faker.seed(7)
    fake = Faker()

    wf_long, wf_short = _prepare_seed_context(db_session)
    generate_scenario(db_session, fake, "demo", wf_long, wf_short)

    rfqs = db_session.query(RFQ).all()
    assert rfqs

    code_pattern = re.compile(r"^(IF|IB)-\d{4}$")
    assert all(rfq.rfq_code and code_pattern.match(rfq.rfq_code) for rfq in rfqs)

    template_lookup = {
        (template.workflow_id, template.order): template.id
        for template in db_session.query(StageTemplate).all()
    }
    stages = db_session.query(RFQStage).all()
    assert stages

    for stage in stages:
        workflow_id = db_session.query(RFQ.workflow_id).filter(RFQ.id == stage.rfq_id).scalar()
        assert stage.stage_template_id is not None
        assert stage.stage_template_id == template_lookup[(workflow_id, stage.order)]


def test_seeded_terminal_rfqs_clear_current_stage_pointer(db_session):
    random.seed(11)
    Faker.seed(11)
    fake = Faker()

    wf_long, wf_short = _prepare_seed_context(db_session)
    generate_scenario(db_session, fake, "completed-lifecycle", wf_long, wf_short)

    terminal_rfqs = (
        db_session.query(RFQ)
        .filter(RFQ.status.in_(["Awarded", "Lost", "Cancelled"]))
        .all()
    )

    assert terminal_rfqs
    assert all(rfq.current_stage_id is None for rfq in terminal_rfqs)
    assert all(rfq.progress == 100 for rfq in terminal_rfqs)

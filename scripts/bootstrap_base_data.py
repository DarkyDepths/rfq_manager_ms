from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.reminder import ReminderRule  # noqa: E402
from src.models.workflow import StageTemplate, Workflow  # noqa: E402


GHI_LONG = {
    "code": "GHI-LONG",
    "name": "GHI long workflow",
    "description": "Full lifecycle for complex, engineered RFQs with design, BOQ/BOM and vendor inquiries.",
    "is_default": True,
    "selection_mode": "fixed",
    "base_workflow_code": None,
    "stages": [
        {"name": "RFQ received", "order": 1, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": None, "is_required": True},
        {"name": "Go / No-Go", "order": 2, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": "go_nogo_decision", "is_required": True},
        {"name": "Pre-bid clarifications", "order": 3, "default_team": "Estimation", "planned_duration_days": 3, "mandatory_fields": None, "is_required": False},
        {"name": "Preliminary design", "order": 4, "default_team": "Engineering", "planned_duration_days": 5, "mandatory_fields": "design_approved", "is_required": False},
        {"name": "BOQ / BOM preparation", "order": 5, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": "boq_completed", "is_required": False},
        {"name": "Vendor inquiry", "order": 6, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": None, "is_required": False},
        {"name": "Cost estimation", "order": 7, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": "estimation_completed", "is_required": False},
        {"name": "Internal approval", "order": 8, "default_team": "Estimation", "planned_duration_days": 3, "mandatory_fields": "approval_signature", "is_required": False},
        {"name": "Offer submission", "order": 9, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": "final_price", "is_required": False},
        {"name": "Post-bid clarifications", "order": 10, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": None, "is_required": False},
        {"name": "Award / Lost", "order": 11, "default_team": "Estimation", "planned_duration_days": 1, "mandatory_fields": None, "is_required": True},
    ],
}

GHI_SHORT = {
    "code": "GHI-SHORT",
    "name": "GHI short workflow",
    "description": "Simplified path for repeat orders, standard items or small-value RFQs.",
    "is_default": False,
    "selection_mode": "fixed",
    "base_workflow_code": None,
    "stages": [
        {"name": "RFQ received", "order": 1, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": None, "is_required": True},
        {"name": "Go / No-Go", "order": 2, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": "go_nogo_decision", "is_required": True},
        {"name": "Cost estimation", "order": 3, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": "estimation_completed", "is_required": True},
        {"name": "Internal approval", "order": 4, "default_team": "Estimation", "planned_duration_days": 3, "mandatory_fields": "approval_signature", "is_required": True},
        {"name": "Offer submission", "order": 5, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": "final_price", "is_required": True},
        {"name": "Award / Lost", "order": 6, "default_team": "Estimation", "planned_duration_days": 1, "mandatory_fields": None, "is_required": True},
    ],
}

GHI_CUSTOM = {
    "code": "GHI-CUSTOM",
    "name": "GHI customized workflow",
    "description": "Customizable lifecycle that reuses the full GHI long workflow catalog at RFQ creation time.",
    "is_default": False,
    "selection_mode": "customizable",
    "base_workflow_code": "GHI-LONG",
    "stages": [],
}

WORKFLOWS = [GHI_LONG, GHI_SHORT, GHI_CUSTOM]

REMINDER_RULES = [
    {
        "name": "Internal due soon",
        "description": "Auto-create internal reminders for RFQs or stages approaching due date.",
        "scope": "all_rfqs",
        "is_active": True,
    },
    {
        "name": "Internal overdue alert",
        "description": "Auto-create internal reminders when an RFQ or stage becomes overdue.",
        "scope": "stage_overdue",
        "is_active": True,
    },
    {
        "name": "Critical RFQ follow-up",
        "description": "Auto-create reminders only for critical RFQs requiring closer follow-up.",
        "scope": "critical_only",
        "is_active": True,
    },
    {
        "name": "External client follow-up",
        "description": "Auto-create reminders for external follow-up with client or vendor.",
        "scope": "external_followup",
        "is_active": False,
    },
]


def make_engine_and_session():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example:\n"
            "  $env:DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5433/rfq_manager_db'"
        )
    engine = create_engine(db_url, future=True)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, session_local


def run_migrations(reset: bool):
    project_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(project_root / "alembic.ini"))

    if reset:
        print(">> Reset requested: downgrading schema to base via Alembic...")
        command.downgrade(alembic_cfg, "base")

    print(">> Applying schema via Alembic (upgrade head)...")
    command.upgrade(alembic_cfg, "head")


def seed_base_data(session):
    workflow_lookup = {}
    for wf_def in WORKFLOWS:
        existing = session.query(Workflow).filter_by(code=wf_def["code"]).first()
        if existing:
            workflow = existing
            workflow.name = wf_def["name"]
            workflow.description = wf_def["description"]
            workflow.is_active = True
            workflow.is_default = wf_def["is_default"]
            workflow.selection_mode = wf_def.get("selection_mode", "fixed")
        else:
            workflow = Workflow(
                name=wf_def["name"],
                code=wf_def["code"],
                description=wf_def["description"],
                is_active=True,
                is_default=wf_def["is_default"],
                selection_mode=wf_def.get("selection_mode", "fixed"),
            )
            session.add(workflow)
            session.flush()

        workflow_lookup[wf_def["code"]] = workflow

        existing_templates = {template.name: template for template in workflow.stages}
        for stage_data in wf_def["stages"]:
            template = existing_templates.get(stage_data["name"])
            if template:
                template.order = stage_data["order"]
                template.default_team = stage_data["default_team"]
                template.planned_duration_days = stage_data["planned_duration_days"]
                template.mandatory_fields = stage_data["mandatory_fields"]
                template.is_required = stage_data.get("is_required", False)
            else:
                template = StageTemplate(
                    workflow_id=workflow.id,
                    **stage_data,
                )
                session.add(template)

    session.flush()

    for wf_def in WORKFLOWS:
        base_workflow_code = wf_def.get("base_workflow_code")
        if not base_workflow_code:
            continue
        workflow = workflow_lookup[wf_def["code"]]
        base_workflow = workflow_lookup.get(base_workflow_code)
        workflow.base_workflow_id = base_workflow.id if base_workflow else None

    for rule_def in REMINDER_RULES:
        if not session.query(ReminderRule).filter_by(name=rule_def["name"]).first():
            session.add(ReminderRule(**rule_def))
    session.commit()


_make_engine_and_session = make_engine_and_session
_run_migrations = run_migrations

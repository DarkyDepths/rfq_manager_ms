"""
Seed script — creates tables and inserts default workflows + stage templates.

Workflows:
- GHI-LONG  (11 stages) — full lifecycle for complex, engineered RFQs
- GHI-SHORT ( 5 stages) — simplified path for repeat orders / small-value RFQs

Usage:
  python seed.py

Idempotent: skips insert if workflow already exists.
Requires a running PostgreSQL instance and valid DATABASE_URL (env var).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base  # Base is shared across models

# Import ALL models so Base.metadata registers every table
from src.models.rfq import RFQ                                   # noqa: F401
from src.models.workflow import Workflow, StageTemplate           # noqa: F401
from src.models.rfq_stage import RFQStage                         # noqa: F401
from src.models.subtask import Subtask                            # noqa: F401
from src.models.rfq_note import RFQNote                           # noqa: F401
from src.models.rfq_file import RFQFile                           # noqa: F401
from src.models.rfq_stage_field_value import RFQStageFieldValue   # noqa: F401
from src.models.rfq_history import RFQHistory                     # noqa: F401
from src.models.reminder import Reminder, ReminderRule            # noqa: F401


# ═══════ WORKFLOW DEFINITIONS ═════════════════════════

GHI_LONG = {
    "code": "GHI-LONG",
    "name": "GHI long workflow",
    "description": "Full lifecycle for complex, engineered RFQs with design, BOQ/BOM and vendor inquiries.",
    "is_default": True,
    "stages": [
        {"name": "RFQ received",            "order": 1,  "default_team": "Estimation",  "planned_duration_days": 2,  "mandatory_fields": None},
        {"name": "Go / No-Go",              "order": 2,  "default_team": "Estimation",  "planned_duration_days": 2,  "mandatory_fields": "go_nogo_decision"},
        {"name": "Pre-bid clarifications",   "order": 3,  "default_team": "Estimation",  "planned_duration_days": 3,  "mandatory_fields": None},
        {"name": "Preliminary design",       "order": 4,  "default_team": "Engineering", "planned_duration_days": 5,  "mandatory_fields": "design_approved"},
        {"name": "BOQ / BOM preparation",    "order": 5,  "default_team": "Estimation",  "planned_duration_days": 5,  "mandatory_fields": "boq_completed"},
        {"name": "Vendor inquiry",           "order": 6,  "default_team": "Estimation",  "planned_duration_days": 5,  "mandatory_fields": None},
        {"name": "Cost estimation",          "order": 7,  "default_team": "Estimation",  "planned_duration_days": 5,  "mandatory_fields": "estimation_completed"},
        {"name": "Internal approval",        "order": 8,  "default_team": "Estimation",  "planned_duration_days": 3,  "mandatory_fields": "approval_signature"},
        {"name": "Offer submission",         "order": 9,  "default_team": "Estimation",  "planned_duration_days": 2,  "mandatory_fields": "final_price"},
        {"name": "Post-bid clarifications",  "order": 10, "default_team": "Estimation",  "planned_duration_days": 5,  "mandatory_fields": None},
        {"name": "Award / Lost",             "order": 11, "default_team": "Estimation",  "planned_duration_days": 1,  "mandatory_fields": None},
    ],
}

GHI_SHORT = {
    "code": "GHI-SHORT",
    "name": "GHI short workflow",
    "description": "Simplified path for repeat orders, standard items or small-value RFQs.",
    "is_default": False,
    "stages": [
        {"name": "RFQ received",      "order": 1, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": None},
        {"name": "Cost estimation",   "order": 2, "default_team": "Estimation", "planned_duration_days": 5, "mandatory_fields": "estimation_completed"},
        {"name": "Internal approval", "order": 3, "default_team": "Estimation", "planned_duration_days": 3, "mandatory_fields": "approval_signature"},
        {"name": "Offer submission",  "order": 4, "default_team": "Estimation", "planned_duration_days": 2, "mandatory_fields": "final_price"},
        {"name": "Award / Lost",      "order": 5, "default_team": "Estimation", "planned_duration_days": 1, "mandatory_fields": None},
    ],
}

WORKFLOWS = [GHI_LONG, GHI_SHORT]

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

def _make_engine_and_session():
    """
    Create engine/session from DATABASE_URL env var.
    This avoids any config/.env overrides inside src.database.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example:\n"
            "  $env:DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5433/rfq_manager_db'"
        )

    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal


def seed():
    engine, SessionLocal = _make_engine_and_session()

    # ── 1. Create all tables ──────────────────────────
    print("Creating tables...")
    Base.metadata.create_all(engine)
    print(f"  ✓ {len(Base.metadata.tables)} tables created/verified")

    # ── 2. Seed workflows + reminder rules ───────────
    session = SessionLocal()
    try:
        # Seed workflows
        for wf_def in WORKFLOWS:
            existing = session.query(Workflow).filter_by(code=wf_def["code"]).first()
            if existing:
                print(f"  ✓ Workflow '{wf_def['code']}' already exists (id={existing.id}) — skipping")
                continue

            workflow = Workflow(
                name=wf_def["name"],
                code=wf_def["code"],
                description=wf_def["description"],
                is_active=True,
                is_default=wf_def["is_default"],
            )
            session.add(workflow)
            session.flush()  # generate workflow.id

            for stage_data in wf_def["stages"]:
                template = StageTemplate(
                    workflow_id=workflow.id,
                    **stage_data,
                )
                session.add(template)

            print(f"  ✓ Workflow '{wf_def['code']}' created (id={workflow.id}) with {len(wf_def['stages'])} stages")

        # Seed reminder rules
        for rule_def in REMINDER_RULES:
            existing = session.query(ReminderRule).filter_by(name=rule_def["name"]).first()
            if existing:
                print(f"  ✓ Reminder rule '{rule_def['name']}' already exists (id={existing.id}) — skipping")
                continue

            rule = ReminderRule(**rule_def)
            session.add(rule)
            print(f"  ✓ Reminder rule '{rule_def['name']}' created")

        session.commit()

    except Exception as e:
        session.rollback()
        print(f"  ✗ Error: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    seed()
    print("\nDone! You can now start the app and test POST /rfqs.")
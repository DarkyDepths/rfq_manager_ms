"""
Seed script — creates tables and inserts default workflows + stage templates.
Upgraded to Phase 2: Scenario-driven CLI for dev/QA.

Usage:
  python scripts/seed.py --scenario=demo --reset --seed=42

Scenarios:
  minimal: Just base tables, 0 RFQs
  demo: 30 RFQs distributed across all stages
  edge-cases: 5 RFQs with weird data / extreme lengths
  blocked-rfqs: 10 RFQs where the current stage is Blocked
  completed-lifecycle: 5 fully completed (Awarded/Lost) RFQs
"""

import os
import sys
import json
import random
import argparse
from datetime import date, timedelta
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.rfq import RFQ
from src.models.workflow import Workflow, StageTemplate
from src.models.rfq_stage import RFQStage
from src.models.subtask import Subtask
from src.models.rfq_note import RFQNote
from src.models.rfq_file import RFQFile
from src.models.rfq_stage_field_value import RFQStageFieldValue
from src.models.rfq_history import RFQHistory
from src.models.reminder import Reminder, ReminderRule

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
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example:\\n"
            "  $env:DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5433/rfq_manager_db'"
        )
    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal

def seed_base_data(session):
    for wf_def in WORKFLOWS:
        existing = session.query(Workflow).filter_by(code=wf_def["code"]).first()
        if existing:
            continue
        workflow = Workflow(
            name=wf_def["name"], code=wf_def["code"],
            description=wf_def["description"], is_active=True, is_default=wf_def["is_default"]
        )
        session.add(workflow)
        session.flush()
        for stage_data in wf_def["stages"]:
            template = StageTemplate(workflow_id=workflow.id, **stage_data)
            session.add(template)

    for rule_def in REMINDER_RULES:
        if not session.query(ReminderRule).filter_by(name=rule_def["name"]).first():
            session.add(ReminderRule(**rule_def))
    session.commit()

def generate_scenario(session, fake, scenario, base_workflow_long, base_workflow_short):
    rfqs_created = 0
    status_counts = {"Draft": 0, "In preparation": 0, "Submitted": 0, "Awarded": 0, "Lost": 0, "Cancelled": 0}
    blocked_count = 0
    
    if scenario == "minimal":
        return 0, status_counts, 0

    templates_dict = {
        base_workflow_long.id: session.query(StageTemplate).filter_by(workflow_id=base_workflow_long.id).order_by(StageTemplate.order).all(),
        base_workflow_short.id: session.query(StageTemplate).filter_by(workflow_id=base_workflow_short.id).order_by(StageTemplate.order).all(),
    }

    def create_rfq(wf, target_status="In preparation", is_blocked=False, force_terminal=False, weird_data=False):
        nonlocal rfqs_created, blocked_count
        name = fake.catch_phrase()[:300] if not weird_data else ("A" * 299)
        client = fake.company()[:200] if not weird_data else ("DROP TABLE clients;--" * 10)[:200]
        owner = fake.name()[:200] if not weird_data else ("👻" * 50)[:200]
        
        rfq = RFQ(
            name=name,
            client=client,
            owner=owner,
            deadline=fake.date_between(start_date="-10d", end_date="+60d"),
            priority=random.choice(["normal", "critical"]),
            status="Draft" if target_status == "Draft" else target_status,
            workflow_id=wf.id,
            rfq_code=f"GHI-{fake.unique.random_int(min=1000, max=99999)}"
        )
        session.add(rfq)
        session.flush()
        
        templates = templates_dict[wf.id]
        stages = []
        for t in templates:
            stage = RFQStage(
                rfq_id=rfq.id, name=t.name, order=t.order, assigned_team=t.default_team,
                mandatory_fields=t.mandatory_fields, status="Not Started", progress=0
            )
            stages.append(stage)
            session.add(stage)
        
        session.flush()
        
        # Fast-forward stages based on target_status
        if target_status == "Draft":
            pass # No active stage
        else:
            stages[0].status = "In Progress"
            stages[0].actual_start = date.today() - timedelta(days=5)
            rfq.current_stage_id = stages[0].id
            
            # fast-forward some stages
            stages_to_complete = random.randint(0, len(stages) - 2)
            if force_terminal:
                stages_to_complete = len(stages) - 1
            
            for i in range(stages_to_complete):
                stages[i].status = "Completed"
                stages[i].progress = 100
                stages[i].actual_end = date.today()
                
                stages[i+1].status = "In Progress"
                stages[i+1].actual_start = date.today()
                rfq.current_stage_id = stages[i+1].id
                
            if stages_to_complete > 0 and not force_terminal:
                rfq.progress = int((stages_to_complete / len(stages)) * 100)
                if rfq.progress == 100:
                    rfq.progress = 99
                
            if force_terminal:
                stages[-1].status = "Completed"
                stages[-1].progress = 100
                rfq.current_stage_id = stages[-1].id
                rfq.status = random.choice(["Awarded", "Lost"])
                rfq.progress = 100
            
            if is_blocked and not force_terminal:
                cur_stage = next((s for s in stages if s.status == "In Progress"), None)
                if cur_stage:
                    cur_stage.blocker_status = "Blocked"
                    cur_stage.blocker_reason_code = "Waiting on Client"
                    cur_stage.blocker_description = fake.sentence()
                    blocked_count += 1
        
        rfqs_created += 1
        status_counts[rfq.status] += 1
        return rfq

    count_map = {
        "demo": 30,
        "edge-cases": 5,
        "blocked-rfqs": 10,
        "completed-lifecycle": 5
    }
    
    for _ in range(count_map.get(scenario, 0)):
        wf = random.choice([base_workflow_long, base_workflow_short])
        
        if scenario == "demo":
            target = random.choice(["Draft", "In preparation", "Submitted"])
            create_rfq(wf, target_status=target, is_blocked=(random.random() < 0.2))
        elif scenario == "edge-cases":
            create_rfq(wf, weird_data=True)
        elif scenario == "blocked-rfqs":
            create_rfq(wf, is_blocked=True)
        elif scenario == "completed-lifecycle":
            create_rfq(wf, force_terminal=True)

    session.commit()
    return rfqs_created, status_counts, blocked_count

def main():
    parser = argparse.ArgumentParser(description="Seed the RFQ Manager DB — Phase 2 CLI")
    parser.add_argument("--scenario", choices=["minimal", "demo", "edge-cases", "blocked-rfqs", "completed-lifecycle"], default="minimal", help="Data scenario to deploy")
    parser.add_argument("--reset", action="store_true", help="Drop all tables and recreate them safely BEFORE seeding")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic data generation", default=None)
    args = parser.parse_args()

    # Apply Random Seed
    if args.seed is not None:
        random.seed(args.seed)
        fake = Faker()
        Faker.seed(args.seed)
    else:
        fake = Faker()
        args.seed = "random"

    engine, SessionLocal = _make_engine_and_session()
    
    if args.reset:
        print(">> Dropping all tables (--reset)...")
        Base.metadata.drop_all(engine)
        
    Base.metadata.create_all(engine)
    
    session = SessionLocal()
    try:
        seed_base_data(session)
        
        wf_long = session.query(Workflow).filter_by(code="GHI-LONG").first()
        wf_short = session.query(Workflow).filter_by(code="GHI-SHORT").first()
        
        print(f">> Seeding scenario: {args.scenario}")
        rfqs_created, status_counts, blocked_count = generate_scenario(
            session, fake, args.scenario, wf_long, wf_short
        )
        
        summary = {
            "scenario": args.scenario,
            "reset_ran": args.reset,
            "seed_used": args.seed,
            "rfqs_created": rfqs_created,
            "status_counts": status_counts,
            "blocked_rfqs": blocked_count
        }
        
        print("\n=== Scenario Seed Summary ===")
        print(f"Scenario: {args.scenario} | Reset: {args.reset} | Seed: {args.seed}")
        print(f"Total RFQs created: {rfqs_created}")
        print(f"Total Blocked: {blocked_count}")
        print(f"Status Breakdown: {status_counts}")
        print("\n=== Machine Readable JSON Summary ===")
        print(json.dumps(summary, indent=2))
        
    except Exception as e:
        session.rollback()
        print(f"\\n[ERROR] Seeding failed: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
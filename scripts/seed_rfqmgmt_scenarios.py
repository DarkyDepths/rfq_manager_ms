from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed import _make_engine_and_session, _run_migrations, seed_base_data
from src.controllers.rfq_controller import RfqController
from src.datasources.rfq_datasource import RfqDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.datasources.workflow_datasource import WorkflowDatasource
from src.models.reminder import Reminder
from src.models.rfq import RFQ
from src.models.rfq_note import RFQNote
from src.models.rfq_stage import RFQStage
from src.models.subtask import Subtask
from src.models.workflow import Workflow
from src.translators.rfq_translator import RfqCreateRequest


BatchName = Literal["must-have", "later", "optional"]
SCENARIO_TAG_PREFIX = "[SCENARIO:"
GOLDEN_SCENARIO_KEY = "RFQ-06"
MANIFEST_VERSION = "rfqmgmt_manager_scenarios_v1"


@dataclass(frozen=True)
class NoteSeed:
    stage_name: str
    user_name: str
    text: str
    days_before_updated: int = 0


@dataclass(frozen=True)
class SubtaskSeed:
    stage_name: str
    name: str
    assigned_to: str
    progress: int
    status: str
    due_offset_days: int


@dataclass(frozen=True)
class ReminderSeed:
    message: str
    due_offset_days: int
    status: str
    reminder_type: str
    assigned_to: str | None = None
    send_count: int = 0
    last_sent_days_ago: int | None = None
    stage_name: str | None = None
    created_by: str = "Scenario Seeder"


@dataclass(frozen=True)
class ManagerScenarioSpec:
    key: str
    batch: BatchName
    workflow_code: str
    name: str
    client: str
    industry: str
    country: str
    owner: str
    priority: str
    status: str
    deadline_offset_days: int
    created_days_ago: int
    updated_days_ago: int
    summary: str
    current_stage_name: str | None
    current_stage_progress: int = 0
    completed_stage_names: tuple[str, ...] = ()
    blocker_reason_code: str | None = None
    outcome_reason: str | None = None
    code_prefix: Literal["IF", "IB"] = "IF"
    intelligence_profile: str = "none"
    notes: tuple[NoteSeed, ...] = ()
    subtasks: tuple[SubtaskSeed, ...] = ()
    reminders: tuple[ReminderSeed, ...] = ()
    captured_data_by_stage: dict[str, dict] = field(default_factory=dict)
    manual_only: bool = False

    @property
    def description(self) -> str:
        return f"{SCENARIO_TAG_PREFIX}{self.key}] {self.summary}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


SCENARIOS: tuple[ManagerScenarioSpec, ...] = (
    ManagerScenarioSpec(
        key="RFQ-01",
        batch="must-have",
        workflow_code="GHI-SHORT",
        name="SEC Auxiliary Skid Bid",
        client="Saudi Electricity Company",
        industry="Power",
        country="Saudi Arabia",
        owner="Lina Haddad",
        priority="normal",
        status="In preparation",
        deadline_offset_days=21,
        created_days_ago=2,
        updated_days_ago=0,
        summary="Fresh manager-only creation for a new SEC auxiliary skid opportunity.",
        current_stage_name="RFQ received",
        current_stage_progress=10,
        intelligence_profile="none",
        notes=(
            NoteSeed(
                stage_name="RFQ received",
                user_name="Lina Haddad",
                text="Kickoff logged. Scope acknowledged and owner assigned for first review.",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-02",
        batch="must-have",
        workflow_code="GHI-LONG",
        name="Aramco Collection Vessel Package",
        client="Saudi Aramco",
        industry="Oil & Gas",
        country="Saudi Arabia",
        owner="Karim Ben Ali",
        priority="normal",
        status="In preparation",
        deadline_offset_days=35,
        created_days_ago=12,
        updated_days_ago=1,
        summary="Early intake-parsed RFQ with preliminary briefing and go/no-go underway.",
        current_stage_name="Go / No-Go",
        current_stage_progress=60,
        completed_stage_names=("RFQ received",),
        intelligence_profile="early_partial",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        notes=(
            NoteSeed(
                stage_name="RFQ received",
                user_name="Karim Ben Ali",
                text="Initial package logged and RFQ ownership accepted by estimation.",
                days_before_updated=6,
            ),
            NoteSeed(
                stage_name="Go / No-Go",
                user_name="Karim Ben Ali",
                text="Commercial attractiveness looks acceptable pending technical review.",
                days_before_updated=1,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Finalize go/no-go summary before weekly proposals review.",
                due_offset_days=3,
                status="open",
                reminder_type="internal",
                assigned_to="Karim Ben Ali",
                stage_name="Go / No-Go",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-03",
        batch="must-have",
        workflow_code="GHI-LONG",
        name="SABIC Tie-In Modification",
        client="SABIC",
        industry="Petrochemicals",
        country="Qatar",
        owner="Maya Fares",
        priority="critical",
        status="In preparation",
        deadline_offset_days=-5,
        created_days_ago=18,
        updated_days_ago=0,
        summary="Critical blocked RFQ with overdue deadline and active reminder pressure.",
        current_stage_name="Pre-bid clarifications",
        current_stage_progress=38,
        completed_stage_names=("RFQ received", "Go / No-Go"),
        blocker_reason_code="waiting_client_docs",
        intelligence_profile="none",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        notes=(
            NoteSeed(
                stage_name="Pre-bid clarifications",
                user_name="Maya Fares",
                text="Blocked waiting for client clarification on nozzle material and scope split.",
                days_before_updated=0,
            ),
        ),
        subtasks=(
            SubtaskSeed(
                stage_name="Pre-bid clarifications",
                name="Track missing client datasheet pack",
                assigned_to="Maya Fares",
                progress=25,
                status="Open",
                due_offset_days=-2,
            ),
            SubtaskSeed(
                stage_name="Pre-bid clarifications",
                name="Prepare clarification matrix for escalation",
                assigned_to="Ahmed Proposal Ops",
                progress=50,
                status="In progress",
                due_offset_days=1,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Escalate missing client documents for blocked RFQ.",
                due_offset_days=-1,
                status="open",
                reminder_type="internal",
                assigned_to="Maya Fares",
                stage_name="Pre-bid clarifications",
            ),
            ReminderSeed(
                message="Follow up with client on outstanding clarification pack.",
                due_offset_days=-2,
                status="sent",
                reminder_type="external",
                assigned_to="Client Contact",
                send_count=1,
                last_sent_days_ago=1,
                stage_name="Pre-bid clarifications",
            ),
            ReminderSeed(
                message="Document blocker reason and impact for management review.",
                due_offset_days=2,
                status="open",
                reminder_type="internal",
                assigned_to="Maya Fares",
                stage_name="Pre-bid clarifications",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-04",
        batch="must-have",
        workflow_code="GHI-LONG",
        name="Aramco Pump Skid Upgrade",
        client="Saudi Aramco",
        industry="Oil & Gas",
        country="Bahrain",
        owner="Youssef Nasser",
        priority="normal",
        status="In preparation",
        deadline_offset_days=14,
        created_days_ago=24,
        updated_days_ago=0,
        summary="Engineering stage in progress with stale intelligence compared to manager activity.",
        current_stage_name="Preliminary design",
        current_stage_progress=90,
        completed_stage_names=("RFQ received", "Go / No-Go", "Pre-bid clarifications"),
        intelligence_profile="stale_partial",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        notes=(
            NoteSeed(
                stage_name="Preliminary design",
                user_name="Youssef Nasser",
                text="Engineering package updated after latest client sketch revision.",
                days_before_updated=0,
            ),
            NoteSeed(
                stage_name="Preliminary design",
                user_name="Dina Engineering",
                text="Hydraulic assumptions reviewed; pending final nozzle orientation confirmation.",
                days_before_updated=1,
            ),
        ),
        subtasks=(
            SubtaskSeed(
                stage_name="Preliminary design",
                name="Update GA drawing for pump skid revision",
                assigned_to="Dina Engineering",
                progress=100,
                status="Done",
                due_offset_days=-1,
            ),
            SubtaskSeed(
                stage_name="Preliminary design",
                name="Review nozzle orientation changes with estimation",
                assigned_to="Youssef Nasser",
                progress=80,
                status="In progress",
                due_offset_days=1,
            ),
            SubtaskSeed(
                stage_name="Preliminary design",
                name="Capture outstanding material assumptions",
                assigned_to="Dina Engineering",
                progress=90,
                status="In progress",
                due_offset_days=2,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Close preliminary design review before BOQ kickoff.",
                due_offset_days=2,
                status="open",
                reminder_type="internal",
                assigned_to="Youssef Nasser",
                stage_name="Preliminary design",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-05",
        batch="later",
        workflow_code="GHI-SHORT",
        name="Maaden Dosing Skid Estimate",
        client="Maaden",
        industry="Mining",
        country="Saudi Arabia",
        owner="Nour Haddad",
        priority="normal",
        status="In preparation",
        deadline_offset_days=12,
        created_days_ago=10,
        updated_days_ago=1,
        summary="Estimator-focused RFQ where workbook intelligence has not been started yet.",
        current_stage_name="Cost estimation",
        current_stage_progress=60,
        completed_stage_names=("RFQ received",),
        intelligence_profile="none",
        subtasks=(
            SubtaskSeed(
                stage_name="Cost estimation",
                name="Complete direct cost line check",
                assigned_to="Nour Haddad",
                progress=60,
                status="In progress",
                due_offset_days=2,
            ),
            SubtaskSeed(
                stage_name="Cost estimation",
                name="Validate vendor quote coverage",
                assigned_to="Bid Support",
                progress=40,
                status="In progress",
                due_offset_days=3,
            ),
            SubtaskSeed(
                stage_name="Cost estimation",
                name="Prepare estimator assumptions list",
                assigned_to="Nour Haddad",
                progress=80,
                status="In progress",
                due_offset_days=1,
            ),
        ),
        notes=(
            NoteSeed(
                stage_name="Cost estimation",
                user_name="Nour Haddad",
                text="Workbook expected from estimator later today; commercial review pending.",
                days_before_updated=1,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Close estimator assumptions before internal approval handoff.",
                due_offset_days=4,
                status="open",
                reminder_type="internal",
                assigned_to="Nour Haddad",
                stage_name="Cost estimation",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key=GOLDEN_SCENARIO_KEY,
        batch="must-have",
        workflow_code="GHI-LONG",
        name="SWCC Pretreatment Dosing Package",
        client="SWCC",
        industry="Water",
        country="UAE",
        owner="Manual Tester",
        priority="critical",
        status="In preparation",
        deadline_offset_days=8,
        created_days_ago=0,
        updated_days_ago=0,
        summary="Reserved manual-only golden journey. Never pre-seeded.",
        current_stage_name="RFQ received",
        intelligence_profile="manual_golden",
        manual_only=True,
    ),
    ManagerScenarioSpec(
        key="RFQ-07",
        batch="later",
        workflow_code="GHI-SHORT",
        name="SEC Cooling Water Module Retrofit",
        client="Saudi Electricity Company",
        industry="Power",
        country="Saudi Arabia",
        owner="Sara Ben Ali",
        priority="normal",
        status="In preparation",
        deadline_offset_days=16,
        created_days_ago=15,
        updated_days_ago=1,
        summary="Edge-case RFQ used for failed workbook intelligence coverage.",
        current_stage_name="Cost estimation",
        current_stage_progress=55,
        completed_stage_names=("RFQ received",),
        intelligence_profile="failed_workbook",
        notes=(
            NoteSeed(
                stage_name="Cost estimation",
                user_name="Sara Ben Ali",
                text="Estimator requested parser rerun after inconsistent workbook intake.",
                days_before_updated=0,
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-08",
        batch="later",
        workflow_code="GHI-SHORT",
        name="SWCC Filter Skid Bid",
        client="SWCC",
        industry="Water",
        country="Oman",
        owner="Omar Rahman",
        priority="critical",
        status="In preparation",
        deadline_offset_days=3,
        created_days_ago=21,
        updated_days_ago=0,
        summary="Near-submission RFQ with high urgency and best-available partial intelligence.",
        current_stage_name="Offer submission",
        current_stage_progress=95,
        completed_stage_names=("RFQ received", "Cost estimation", "Internal approval"),
        intelligence_profile="mature_partial",
        captured_data_by_stage={
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-4481"},
        },
        subtasks=(
            SubtaskSeed(
                stage_name="Offer submission",
                name="Finalize commercial summary letter",
                assigned_to="Omar Rahman",
                progress=100,
                status="Done",
                due_offset_days=0,
            ),
            SubtaskSeed(
                stage_name="Offer submission",
                name="Check client delivery portal package naming",
                assigned_to="Bid Support",
                progress=90,
                status="In progress",
                due_offset_days=0,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Submission deadline today. Validate package before upload.",
                due_offset_days=0,
                status="open",
                reminder_type="internal",
                assigned_to="Omar Rahman",
                stage_name="Offer submission",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-09",
        batch="must-have",
        workflow_code="GHI-SHORT",
        name="SABIC Nitrogen Header Debottleneck",
        client="SABIC",
        industry="Petrochemicals",
        country="Saudi Arabia",
        owner="Ahmed Proposal Ops",
        priority="critical",
        status="Submitted",
        deadline_offset_days=-2,
        created_days_ago=28,
        updated_days_ago=1,
        summary="Submitted RFQ awaiting client decision with mature but still partial intelligence.",
        current_stage_name="Award / Lost",
        current_stage_progress=25,
        completed_stage_names=("RFQ received", "Cost estimation", "Internal approval", "Offer submission"),
        intelligence_profile="mature_partial",
        captured_data_by_stage={
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-7720"},
            "Offer submission": {"final_price": 971150.0},
        },
        notes=(
            NoteSeed(
                stage_name="Offer submission",
                user_name="Ahmed Proposal Ops",
                text="Commercial offer submitted through client portal; awaiting technical clarification feedback.",
                days_before_updated=1,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Internal follow-up on submitted RFQ outcome window.",
                due_offset_days=1,
                status="open",
                reminder_type="internal",
                assigned_to="Ahmed Proposal Ops",
                stage_name="Award / Lost",
            ),
            ReminderSeed(
                message="External follow-up with client buyer after submission.",
                due_offset_days=2,
                status="sent",
                reminder_type="external",
                assigned_to="Client Buyer",
                send_count=1,
                last_sent_days_ago=0,
                stage_name="Award / Lost",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-10",
        batch="must-have",
        workflow_code="GHI-SHORT",
        name="Maaden Demineralized Water Package",
        client="Maaden",
        industry="Mining",
        country="Saudi Arabia",
        owner="Lina Haddad",
        priority="normal",
        status="Awarded",
        deadline_offset_days=-12,
        created_days_ago=58,
        updated_days_ago=13,
        summary="Awarded RFQ with complete operational closure but lagging intelligence refresh.",
        current_stage_name=None,
        completed_stage_names=("RFQ received", "Cost estimation", "Internal approval", "Offer submission", "Award / Lost"),
        outcome_reason="Best value and delivery commitment",
        intelligence_profile="mature_partial_stale_award",
        captured_data_by_stage={
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-8821"},
            "Offer submission": {"final_price": 842500.0},
        },
        notes=(
            NoteSeed(
                stage_name="Award / Lost",
                user_name="Lina Haddad",
                text="Award confirmed by client. Operational closure completed without additional intelligence refresh.",
                days_before_updated=0,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Archive awarded RFQ package and close action log.",
                due_offset_days=-10,
                status="resolved",
                reminder_type="internal",
                assigned_to="Lina Haddad",
                stage_name="Award / Lost",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-11",
        batch="must-have",
        workflow_code="GHI-LONG",
        name="Aramco Produced Water Polishing Unit",
        client="Saudi Aramco",
        industry="Oil & Gas",
        country="Saudi Arabia",
        owner="Karim Ben Ali",
        priority="normal",
        status="Lost",
        deadline_offset_days=-8,
        created_days_ago=47,
        updated_days_ago=6,
        summary="Lost RFQ with deep operational history and intentionally incomplete intelligence coverage.",
        current_stage_name=None,
        completed_stage_names=(
            "RFQ received",
            "Go / No-Go",
            "Pre-bid clarifications",
            "Preliminary design",
            "BOQ / BOM preparation",
            "Vendor inquiry",
            "Cost estimation",
            "Internal approval",
            "Offer submission",
            "Post-bid clarifications",
            "Award / Lost",
        ),
        outcome_reason="Lost on commercial ranking after final clarifications",
        intelligence_profile="thin_partial_stale",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
            "Preliminary design": {"design_approved": True},
            "BOQ / BOM preparation": {"boq_completed": True},
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-5543"},
            "Offer submission": {"final_price": 1184500.0},
        },
        notes=(
            NoteSeed(
                stage_name="Preliminary design",
                user_name="Dina Engineering",
                text="Design basis frozen after client comment cycle two.",
                days_before_updated=18,
            ),
            NoteSeed(
                stage_name="Offer submission",
                user_name="Karim Ben Ali",
                text="Submission issued with clarified commercial exclusions.",
                days_before_updated=9,
            ),
            NoteSeed(
                stage_name="Award / Lost",
                user_name="Karim Ben Ali",
                text="Loss recorded after final client ranking review.",
                days_before_updated=6,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Close lost RFQ action log and capture lessons learned.",
                due_offset_days=-4,
                status="resolved",
                reminder_type="internal",
                assigned_to="Karim Ben Ali",
                stage_name="Award / Lost",
            ),
        ),
    ),
    ManagerScenarioSpec(
        key="RFQ-12",
        batch="optional",
        workflow_code="GHI-SHORT",
        name="Pending Artifact Coverage RFQ",
        client="SEC",
        industry="Power",
        country="Saudi Arabia",
        owner="Nour Haddad",
        priority="normal",
        status="In preparation",
        deadline_offset_days=18,
        created_days_ago=7,
        updated_days_ago=1,
        summary="Optional manager shell reserved for pending-artifact enum coverage.",
        current_stage_name="RFQ received",
        current_stage_progress=25,
        intelligence_profile="pending_artifact",
    ),
    ManagerScenarioSpec(
        key="RFQ-13",
        batch="optional",
        workflow_code="GHI-LONG",
        name="Briefing Failure Coverage RFQ",
        client="SWCC",
        industry="Water",
        country="Saudi Arabia",
        owner="Omar Rahman",
        priority="normal",
        status="In preparation",
        deadline_offset_days=24,
        created_days_ago=9,
        updated_days_ago=1,
        summary="Optional manager shell reserved for explicit briefing failure coverage.",
        current_stage_name="Go / No-Go",
        current_stage_progress=45,
        completed_stage_names=("RFQ received",),
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        intelligence_profile="failed_briefing",
    ),
)


def scenario_registry() -> dict[str, ManagerScenarioSpec]:
    return {scenario.key: scenario for scenario in SCENARIOS}


def seeded_scenarios_for_batch(batch: Literal["must-have", "later", "optional", "all"]) -> list[ManagerScenarioSpec]:
    scenarios = [scenario for scenario in SCENARIOS if not scenario.manual_only]
    if batch == "all":
        return scenarios
    return [scenario for scenario in scenarios if scenario.batch == batch]


def _manual_reserved_entries() -> list[dict]:
    return [
        {
            "scenario_key": scenario.key,
            "name": scenario.name,
            "workflow_code": scenario.workflow_code,
            "priority": scenario.priority,
            "status": scenario.status,
            "summary": scenario.summary,
            "manual_only": True,
        }
        for scenario in SCENARIOS
        if scenario.manual_only
    ]


def _stage_lookup(session, workflow_code: str) -> Workflow:
    workflow = session.query(Workflow).filter(Workflow.code == workflow_code).first()
    if workflow is None:
        raise RuntimeError(f"Workflow '{workflow_code}' not found. Seed base data first.")
    return workflow


def _scenario_query(session, scenario_key: str):
    return session.query(RFQ).filter(RFQ.description.like(f"{SCENARIO_TAG_PREFIX}{scenario_key}]%"))


def _find_existing_scenario(session, scenario_key: str) -> RFQ | None:
    return _scenario_query(session, scenario_key).first()


def _scenario_timestamps(spec: ManagerScenarioSpec) -> tuple[datetime, datetime]:
    now = _utc_now()
    created_at = now - timedelta(days=spec.created_days_ago)
    updated_at = now - timedelta(days=spec.updated_days_ago)
    if updated_at < created_at:
        updated_at = created_at
    return created_at, updated_at


def _set_model_timestamps(model, *, created_at: datetime | None = None, updated_at: datetime | None = None) -> None:
    if created_at is not None and hasattr(model, "created_at"):
        model.created_at = created_at
    if updated_at is not None and hasattr(model, "updated_at"):
        model.updated_at = updated_at


def _set_stage_state(
    stage: RFQStage,
    *,
    status: str,
    progress: int,
    actual_start: date | None,
    actual_end: date | None,
    blocker_reason_code: str | None,
) -> None:
    stage.status = status
    stage.progress = progress
    stage.actual_start = actual_start
    stage.actual_end = actual_end
    if blocker_reason_code:
        stage.blocker_status = "Blocked"
        stage.blocker_reason_code = blocker_reason_code
    else:
        stage.blocker_status = None
        stage.blocker_reason_code = None


def _apply_stage_progress_from_subtasks(session, stage: RFQStage) -> None:
    subtasks = (
        session.query(Subtask)
        .filter(Subtask.rfq_stage_id == stage.id, Subtask.deleted_at.is_(None))
        .all()
    )
    if not subtasks:
        return
    average = sum(subtask.progress for subtask in subtasks) // len(subtasks)
    if average == 100 and stage.status != "Completed":
        average = 99
    stage.progress = average


def _calculate_rfq_progress(stages: list[RFQStage]) -> int:
    non_skipped = [stage for stage in stages if stage.status != "Skipped"]
    if not non_skipped:
        return 100
    if all(stage.status == "Completed" for stage in non_skipped):
        return 100
    return sum(stage.progress for stage in non_skipped) // len(non_skipped)


def _seed_notes(session, stage_map: dict[str, RFQStage], spec: ManagerScenarioSpec, updated_at: datetime) -> None:
    for index, note_seed in enumerate(spec.notes):
        stage = stage_map[note_seed.stage_name]
        note_time = updated_at - timedelta(days=note_seed.days_before_updated, hours=index)
        note = RFQNote(
            rfq_stage_id=stage.id,
            user_name=note_seed.user_name,
            text=note_seed.text,
        )
        session.add(note)
        session.flush()
        note.created_at = note_time


def _seed_subtasks(session, stage_map: dict[str, RFQStage], spec: ManagerScenarioSpec, updated_at: datetime) -> None:
    for index, subtask_seed in enumerate(spec.subtasks):
        stage = stage_map[subtask_seed.stage_name]
        created_at = updated_at - timedelta(days=max(subtask_seed.due_offset_days, 0) + 2, hours=index)
        subtask = Subtask(
            rfq_stage_id=stage.id,
            name=subtask_seed.name,
            assigned_to=subtask_seed.assigned_to,
            due_date=date.today() + timedelta(days=subtask_seed.due_offset_days),
            progress=subtask_seed.progress,
            status=subtask_seed.status,
        )
        session.add(subtask)
        session.flush()
        _set_model_timestamps(subtask, created_at=created_at, updated_at=updated_at)


def _seed_reminders(session, rfq: RFQ, stage_map: dict[str, RFQStage], spec: ManagerScenarioSpec, updated_at: datetime) -> None:
    for index, reminder_seed in enumerate(spec.reminders):
        reminder = Reminder(
            rfq_id=rfq.id,
            rfq_stage_id=stage_map[reminder_seed.stage_name].id if reminder_seed.stage_name else None,
            type=reminder_seed.reminder_type,
            message=reminder_seed.message,
            due_date=date.today() + timedelta(days=reminder_seed.due_offset_days),
            assigned_to=reminder_seed.assigned_to,
            status=reminder_seed.status,
            created_by=reminder_seed.created_by,
            send_count=reminder_seed.send_count,
        )
        if reminder_seed.last_sent_days_ago is not None:
            reminder.last_sent_at = _utc_now() - timedelta(days=reminder_seed.last_sent_days_ago)
        session.add(reminder)
        session.flush()
        reminder_created_at = updated_at - timedelta(days=index + 1)
        _set_model_timestamps(reminder, created_at=reminder_created_at, updated_at=updated_at)


def _apply_stage_blueprint(session, rfq: RFQ, spec: ManagerScenarioSpec) -> None:
    stages = (
        session.query(RFQStage)
        .filter(RFQStage.rfq_id == rfq.id)
        .order_by(RFQStage.order.asc())
        .all()
    )
    created_at, updated_at = _scenario_timestamps(spec)
    stage_map = {stage.name: stage for stage in stages}
    completed = set(spec.completed_stage_names)
    current_stage = stage_map.get(spec.current_stage_name) if spec.current_stage_name else None

    cursor_day = created_at.date()
    for stage in stages:
        stage.captured_data = dict(spec.captured_data_by_stage.get(stage.name, {}))
        if stage.name in completed:
            actual_start = cursor_day
            actual_end = actual_start + timedelta(days=1)
            _set_stage_state(
                stage,
                status="Completed",
                progress=100,
                actual_start=actual_start,
                actual_end=actual_end,
                blocker_reason_code=None,
            )
            cursor_day = actual_end
        elif current_stage and stage.id == current_stage.id:
            actual_start = max(cursor_day, (updated_at - timedelta(days=2)).date())
            _set_stage_state(
                stage,
                status="In Progress",
                progress=spec.current_stage_progress,
                actual_start=actual_start,
                actual_end=None,
                blocker_reason_code=spec.blocker_reason_code,
            )
        else:
            _set_stage_state(
                stage,
                status="Not Started",
                progress=0,
                actual_start=None,
                actual_end=None,
                blocker_reason_code=None,
            )

    _seed_notes(session, stage_map, spec, updated_at)
    _seed_subtasks(session, stage_map, spec, updated_at)

    for stage in stages:
        _apply_stage_progress_from_subtasks(session, stage)

    rfq.status = spec.status
    rfq.outcome_reason = spec.outcome_reason
    rfq.current_stage_id = current_stage.id if current_stage and spec.status not in {"Awarded", "Lost", "Cancelled"} else None
    rfq.progress = 100 if spec.status in {"Awarded", "Lost", "Cancelled"} else _calculate_rfq_progress(stages)

    _seed_reminders(session, rfq, stage_map, spec, updated_at)

    for index, stage in enumerate(stages):
        stage_created_at = created_at + timedelta(days=index)
        stage_updated_at = updated_at if (stage.status != "Not Started" or stage.blocker_status) else stage_created_at
        _set_model_timestamps(stage, created_at=stage_created_at, updated_at=stage_updated_at)

    _set_model_timestamps(rfq, created_at=created_at, updated_at=updated_at)


def _build_manifest_entry(session, scenario: ManagerScenarioSpec, rfq: RFQ) -> dict:
    current_stage_name = None
    if rfq.current_stage_id:
        current_stage = session.query(RFQStage).filter(RFQStage.id == rfq.current_stage_id).first()
        current_stage_name = current_stage.name if current_stage else None
    return {
        "scenario_key": scenario.key,
        "batch": scenario.batch,
        "manual_only": scenario.manual_only,
        "intelligence_profile": scenario.intelligence_profile,
        "rfq_id": str(rfq.id),
        "rfq_code": rfq.rfq_code,
        "name": rfq.name,
        "client": rfq.client,
        "industry": rfq.industry,
        "country": rfq.country,
        "priority": rfq.priority,
        "status": rfq.status,
        "workflow_code": scenario.workflow_code,
        "current_stage_id": str(rfq.current_stage_id) if rfq.current_stage_id else None,
        "current_stage_name": current_stage_name,
        "deadline": rfq.deadline.isoformat(),
        "owner": rfq.owner,
        "description": rfq.description,
        "outcome_reason": rfq.outcome_reason,
        "created_at": rfq.created_at.isoformat() if isinstance(rfq.created_at, datetime) else None,
        "updated_at": rfq.updated_at.isoformat() if isinstance(rfq.updated_at, datetime) else None,
    }


def _create_controller(session) -> RfqController:
    return RfqController(
        rfq_datasource=RfqDatasource(session),
        workflow_datasource=WorkflowDatasource(session),
        rfq_stage_datasource=RfqStageDatasource(session),
        session=session,
        event_bus_connector=None,
    )


def _create_scenario_rfq(session, scenario: ManagerScenarioSpec) -> RFQ:
    workflow = _stage_lookup(session, scenario.workflow_code)
    controller = _create_controller(session)
    request = RfqCreateRequest(
        name=scenario.name,
        client=scenario.client,
        deadline=date.today() + timedelta(days=scenario.deadline_offset_days),
        owner=scenario.owner,
        workflow_id=workflow.id,
        industry=scenario.industry,
        country=scenario.country,
        priority=scenario.priority,
        description=scenario.description,
        code_prefix=scenario.code_prefix,
    )
    detail = controller.create(request)
    rfq = session.query(RFQ).filter(RFQ.id == detail.id).first()
    if rfq is None:
        raise RuntimeError(f"Failed to create scenario RFQ '{scenario.key}'")
    _apply_stage_blueprint(session, rfq, scenario)
    session.commit()
    session.refresh(rfq)
    return rfq


def _load_existing_seeded_entries(session) -> list[dict]:
    entries: list[dict] = []
    registry = scenario_registry()
    for scenario_key, scenario in sorted(registry.items()):
        if scenario.manual_only:
            continue
        rfq = _find_existing_scenario(session, scenario_key)
        if rfq is None:
            continue
        entries.append(_build_manifest_entry(session, scenario, rfq))
    return entries


def seed_manager_scenarios(
    session,
    *,
    batch: Literal["must-have", "later", "optional", "all"] = "must-have",
) -> dict:
    seed_base_data(session)
    created: list[str] = []
    existing: list[str] = []

    for scenario in seeded_scenarios_for_batch(batch):
        current = _find_existing_scenario(session, scenario.key)
        if current is not None:
            existing.append(scenario.key)
            continue
        _create_scenario_rfq(session, scenario)
        created.append(scenario.key)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": _utc_now().isoformat(),
        "requested_batch": batch,
        "golden_reserved_scenario": GOLDEN_SCENARIO_KEY,
        "manual_reserved": _manual_reserved_entries(),
        "scenarios": _load_existing_seeded_entries(session),
    }
    return {
        "created_scenarios": created,
        "existing_scenarios": existing,
        "manifest": manifest,
    }


def write_manifest(manifest: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _cli_path(value: str) -> Path:
    # Normalize Windows-style separators so container execution on Linux
    # still resolves mounted paths like /app/seed_outputs correctly.
    return Path(value.replace("\\", "/"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed deterministic RFQMGMT manager scenarios and emit a manifest for intelligence seeding.",
    )
    parser.add_argument(
        "--batch",
        choices=["must-have", "later", "optional", "all"],
        default="must-have",
        help="Scenario batch to seed. RFQ-06 remains manual-only in every batch.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Downgrade to base and re-run Alembic migrations before seeding.",
    )
    parser.add_argument(
        "--manifest-out",
        default=str(Path("seed_outputs") / "rfqmgmt_manager_manifest.json"),
        help="Path to write the manager scenario manifest JSON.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    _run_migrations(reset=args.reset)
    _, session_factory = _make_engine_and_session()
    session = session_factory()
    try:
        result = seed_manager_scenarios(session, batch=args.batch)
    finally:
        session.close()

    output_path = _cli_path(args.manifest_out)
    write_manifest(result["manifest"], output_path)

    print(
        json.dumps(
            {
                "requested_batch": args.batch,
                "created_scenarios": result["created_scenarios"],
                "existing_scenarios": result["existing_scenarios"],
                "manifest_out": output_path.as_posix(),
                "seeded_scenarios_present": [item["scenario_key"] for item in result["manifest"]["scenarios"]],
                "golden_reserved_scenario": GOLDEN_SCENARIO_KEY,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

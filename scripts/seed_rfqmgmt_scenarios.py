from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap_base_data import make_engine_and_session, run_migrations, seed_base_data  # noqa: E402
from src.controllers.rfq_controller import RfqController  # noqa: E402
from src.datasources.rfq_datasource import RfqDatasource  # noqa: E402
from src.datasources.rfq_stage_datasource import RfqStageDatasource  # noqa: E402
from src.datasources.workflow_datasource import WorkflowDatasource  # noqa: E402
from src.models.reminder import Reminder  # noqa: E402
from src.models.rfq import RFQ  # noqa: E402
from src.models.rfq_file import RFQFile  # noqa: E402
from src.models.rfq_note import RFQNote  # noqa: E402
from src.models.rfq_stage import RFQStage  # noqa: E402
from src.models.subtask import Subtask  # noqa: E402
from src.models.workflow import Workflow  # noqa: E402
from src.translators.rfq_translator import RfqCreateRequest  # noqa: E402
from src.utils.rfq_lifecycle import calculate_rfq_lifecycle_progress  # noqa: E402


BatchName = Literal["must-have", "later", "optional"]
SCENARIO_TAG_PREFIX = "[SCENARIO:"
GOLDEN_SCENARIO_KEY = "RFQ-06"
MANIFEST_VERSION = "rfqmgmt_manager_scenarios_v3"


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
class FileSeed:
    stage_name: str
    filename: str
    file_type: str
    uploaded_by: str
    size_bytes: int = 0
    days_before_updated: int = 0


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
    family: str = "legacy_curated"
    current_stage_progress: int = 0
    completed_stage_names: tuple[str, ...] = ()
    blocker_reason_code: str | None = None
    outcome_reason: str | None = None
    code_prefix: Literal["IF", "IB"] = "IF"
    intelligence_profile: str = "none"
    tags: tuple[str, ...] = ()
    notes: tuple[NoteSeed, ...] = ()
    subtasks: tuple[SubtaskSeed, ...] = ()
    reminders: tuple[ReminderSeed, ...] = ()
    files: tuple[FileSeed, ...] = ()
    skip_stage_names: tuple[str, ...] = ()
    captured_data_by_stage: dict[str, dict] = field(default_factory=dict)
    verification_roles: tuple[str, ...] = ()
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
        owner="GHI Estimator",
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
                user_name="Estimation Manager",
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
        owner="GHI Estimator",
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
        verification_roles=("intelligence_snapshot_anchor",),
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
        owner="GHI Estimator",
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
                status="overdue",
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
        owner="GHI Estimator",
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
        verification_roles=("stale_snapshot_anchor",),
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
        owner="GHI Estimator",
        priority="normal",
        status="In preparation",
        deadline_offset_days=12,
        created_days_ago=10,
        updated_days_ago=1,
        summary="Estimator-focused RFQ where workbook intelligence has not been started yet.",
        current_stage_name="Cost estimation",
        current_stage_progress=60,
        completed_stage_names=("RFQ received", "Go / No-Go"),
        intelligence_profile="none",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        subtasks=(
            SubtaskSeed(
                stage_name="Cost estimation",
                name="Complete direct cost line check",
                assigned_to="GHI Estimator",
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
                assigned_to="GHI Estimator",
                progress=80,
                status="In progress",
                due_offset_days=1,
            ),
        ),
        notes=(
            NoteSeed(
                stage_name="Cost estimation",
                user_name="GHI Estimator",
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
                assigned_to="GHI Estimator",
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
        owner="GHI Estimator",
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
        owner="GHI Estimator",
        priority="normal",
        status="In preparation",
        deadline_offset_days=16,
        created_days_ago=15,
        updated_days_ago=1,
        summary="Edge-case RFQ used for failed workbook intelligence coverage.",
        current_stage_name="Cost estimation",
        current_stage_progress=55,
        completed_stage_names=("RFQ received", "Go / No-Go"),
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
        },
        intelligence_profile="failed_workbook",
        verification_roles=("failed_workbook_anchor",),
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
        owner="GHI Estimator",
        priority="critical",
        status="In preparation",
        deadline_offset_days=3,
        created_days_ago=21,
        updated_days_ago=0,
        summary="Near-submission RFQ with high urgency and best-available partial intelligence.",
        current_stage_name="Offer submission",
        current_stage_progress=95,
        completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval"),
        intelligence_profile="mature_partial",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
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
        owner="GHI Estimator",
        priority="critical",
        status="In preparation",
        deadline_offset_days=-2,
        created_days_ago=28,
        updated_days_ago=1,
        summary="Offer already delivered; RFQ is waiting in the final decision stage with mature but still partial intelligence.",
        current_stage_name="Award / Lost",
        current_stage_progress=25,
        completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission"),
        intelligence_profile="mature_partial",
        verification_roles=("decision_wait_anchor", "workbook_artifact_anchor"),
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-7720"},
            "Offer submission": {"final_price": 971150.0},
        },
        notes=(
            NoteSeed(
                stage_name="Offer submission",
                user_name="Ahmed Proposal Ops",
                text="Commercial offer delivered through client portal; awaiting technical clarification feedback.",
                days_before_updated=1,
            ),
        ),
        reminders=(
            ReminderSeed(
                message="Internal follow-up on the post-offer decision window.",
                due_offset_days=1,
                status="open",
                reminder_type="internal",
                assigned_to="Ahmed Proposal Ops",
                stage_name="Award / Lost",
            ),
            ReminderSeed(
                message="External follow-up with client buyer after offer delivery.",
                due_offset_days=2,
                status="open",
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
        owner="GHI Estimator",
        priority="normal",
        status="Awarded",
        deadline_offset_days=-12,
        created_days_ago=58,
        updated_days_ago=13,
        summary="Awarded RFQ with complete operational closure but lagging intelligence refresh.",
        current_stage_name=None,
        completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission", "Award / Lost"),
        outcome_reason="Best value and delivery commitment",
        intelligence_profile="mature_partial_stale_award",
        captured_data_by_stage={
            "Go / No-Go": {"go_nogo_decision": "proceed"},
            "Cost estimation": {"estimation_completed": True},
            "Internal approval": {"approval_signature": "APP-8821"},
            "Offer submission": {"final_price": 842500.0},
        },
        notes=(
            NoteSeed(
                stage_name="Award / Lost",
                user_name="Estimation Manager",
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
                assigned_to="Estimation Manager",
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
        owner="GHI Estimator",
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
        owner="GHI Estimator",
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
        owner="GHI Estimator",
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


def _scenario_number(key: str) -> int:
    return int(key.split("-")[1])


def _approval_signature_for_key(key: str) -> str:
    return f"APP-{4100 + (_scenario_number(key) * 19)}"


def _final_price_for_key(key: str) -> float:
    return float(225_000 + (_scenario_number(key) * 34_750))


def _default_stage_payload(
    *,
    stage_name: str,
    scenario_key: str,
    status: str,
    tags: tuple[str, ...],
    outcome_reason: str | None,
) -> dict:
    if stage_name == "Go / No-Go":
        return {"go_nogo_decision": "proceed"}
    if stage_name == "Preliminary design":
        return {"design_approved": True}
    if stage_name == "BOQ / BOM preparation":
        return {"boq_completed": True}
    if stage_name == "Cost estimation":
        return {
            "estimation_completed": True,
            "estimation_amount": round(_final_price_for_key(scenario_key) * 0.92, 3),
            "estimation_currency": "SAR",
        }
    if stage_name == "Internal approval":
        return {"approval_signature": _approval_signature_for_key(scenario_key)}
    if stage_name == "Offer submission":
        return {
            "final_price": round(_final_price_for_key(scenario_key), 3),
            "final_price_currency": "SAR",
        }
    if stage_name == "Award / Lost":
        if status == "Awarded":
            return {"rfq_terminal_outcome": "awarded"}
        if status == "Lost":
            payload = {
                "rfq_terminal_outcome": "lost",
                "rfq_lost_reason_code": "other" if "loss_other" in tags else "commercial_gap",
            }
            if "loss_other" in tags and outcome_reason:
                payload["rfq_lost_reason_detail"] = outcome_reason
            return payload
    return {}


def _build_captured_data(
    *,
    scenario_key: str,
    completed_stage_names: tuple[str, ...],
    status: str,
    tags: tuple[str, ...],
    outcome_reason: str | None,
    extra: dict[str, dict] | None,
) -> dict[str, dict]:
    captured_data: dict[str, dict] = {}
    for stage_name in completed_stage_names:
        payload = _default_stage_payload(
            stage_name=stage_name,
            scenario_key=scenario_key,
            status=status,
            tags=tags,
            outcome_reason=outcome_reason,
        )
        if payload:
            captured_data[stage_name] = payload

    for stage_name, payload in (extra or {}).items():
        base_payload = dict(captured_data.get(stage_name, {}))
        base_payload.update(payload)
        captured_data[stage_name] = base_payload

    return captured_data


def _default_note_text(family: str, stage_name: str, summary: str) -> str:
    messages = {
        "fresh_intake": "Initial intake logged and ownership confirmed for early qualification.",
        "healthy_mid_pipeline": f"{stage_name} is progressing on plan with dependencies actively managed.",
        "deadline_watch": "The RFQ is nearing deadline, but the team still has a controlled action plan.",
        "blocked_client_hold": "Client-side clarifications remain the main blocker to advancing the workflow.",
        "blocked_internal_hold": "An internal workflow decision is holding the stage until the technical/commercial position is cleared.",
        "stale_execution": "Execution has slowed and the stage is now leaning on catch-up actions rather than normal cadence.",
        "decision_wait_followup": "Offer has been delivered and follow-up cadence is being tracked while awaiting the award decision.",
        "awarded_terminal": "Award confirmed and closeout notes captured for handoff readiness.",
        "lost_terminal": "Loss rationale captured with follow-up actions for lessons learned.",
        "cancelled_terminal": "Cancellation was recorded and downstream stages were intentionally not executed.",
    }
    return messages.get(family, summary)


def _default_subtasks(
    *,
    family: str,
    current_stage_name: str | None,
    owner: str,
) -> tuple[SubtaskSeed, ...]:
    if current_stage_name is None:
        return ()

    if family == "healthy_mid_pipeline":
        if current_stage_name == "Preliminary design":
            return (
                SubtaskSeed(current_stage_name, "Finalize GA revision alignment", owner, 70, "In progress", 2),
                SubtaskSeed(current_stage_name, "Close remaining engineering assumptions", "Dina Engineering", 55, "In progress", 3),
            )
        if current_stage_name == "Vendor inquiry":
            return (
                SubtaskSeed(current_stage_name, "Normalize received vendor quote matrix", owner, 65, "In progress", 2),
                SubtaskSeed(current_stage_name, "Validate quote exclusions with procurement", "Bid Support", 40, "Open", 3),
            )
        if current_stage_name == "Cost estimation":
            return (
                SubtaskSeed(current_stage_name, "Finalize labor and freight allowances", owner, 78, "In progress", 2),
                SubtaskSeed(current_stage_name, "Cross-check estimator workbook assumptions", "Proposal Controls", 60, "In progress", 2),
            )

    if family == "deadline_watch":
        return (
            SubtaskSeed(current_stage_name, "Close final review items before deadline", owner, 85, "In progress", 1),
            SubtaskSeed(current_stage_name, "Prepare submission fallback package", "Bid Support", 50, "In progress", 1),
        )

    if family == "blocked_client_hold":
        return (
            SubtaskSeed(current_stage_name, "Track client clarification response pack", owner, 35, "Open", -1),
            SubtaskSeed(current_stage_name, "Prepare escalation summary for manager review", "Maya Fares", 45, "In progress", 1),
        )

    if family == "blocked_internal_hold":
        return (
            SubtaskSeed(current_stage_name, "Document open internal decision points", owner, 40, "Open", 1),
        )

    if family == "stale_execution":
        return (
            SubtaskSeed(current_stage_name, "Recover delayed action log and resync owners", owner, 30, "Open", -2),
            SubtaskSeed(current_stage_name, "Re-baseline outstanding scope assumptions", "Proposal Controls", 55, "In progress", 1),
        )

    return ()


def _default_reminders(
    *,
    family: str,
    current_stage_name: str | None,
    owner: str,
) -> tuple[ReminderSeed, ...]:
    if family == "fresh_intake" and current_stage_name == "Go / No-Go":
        return (
            ReminderSeed(
                message="Close early go/no-go posture before the next proposals review.",
                due_offset_days=2,
                status="open",
                reminder_type="internal",
                assigned_to=owner,
                stage_name=current_stage_name,
            ),
        )

    if family == "deadline_watch" and current_stage_name:
        return (
            ReminderSeed(
                message="RFQ is nearing deadline. Keep final actions tightly controlled.",
                due_offset_days=1,
                status="open",
                reminder_type="internal",
                assigned_to=owner,
                stage_name=current_stage_name,
            ),
        )

    if family == "blocked_client_hold" and current_stage_name:
        return (
            ReminderSeed(
                message="Escalate outstanding client dependencies on the blocked RFQ.",
                due_offset_days=0,
                status="open",
                reminder_type="internal",
                assigned_to=owner,
                stage_name=current_stage_name,
            ),
            ReminderSeed(
                message="Follow up with client on missing clarification or data package.",
                due_offset_days=-1,
                status="overdue",
                reminder_type="external",
                assigned_to="Client Contact",
                send_count=1,
                last_sent_days_ago=1,
                stage_name=current_stage_name,
            ),
        )

    if family == "blocked_internal_hold" and current_stage_name:
        return (
            ReminderSeed(
                message="Resolve the internal workflow decision that is holding the stage.",
                due_offset_days=1,
                status="open",
                reminder_type="internal",
                assigned_to=owner,
                stage_name=current_stage_name,
            ),
        )

    if family == "stale_execution" and current_stage_name:
        return (
            ReminderSeed(
                message="Stage is drifting late. Reset owner actions and recover momentum.",
                due_offset_days=-1,
                status="overdue",
                reminder_type="internal",
                assigned_to=owner,
                stage_name=current_stage_name,
            ),
        )

    if family == "decision_wait_followup":
        return (
            ReminderSeed(
                message="Internal follow-up on the post-offer decision window.",
                due_offset_days=1,
                status="open",
                reminder_type="internal",
                assigned_to=owner,
                stage_name="Award / Lost",
            ),
            ReminderSeed(
                message="External follow-up with client after offer delivery.",
                due_offset_days=2,
                status="open",
                reminder_type="external",
                assigned_to="Client Buyer",
                send_count=1,
                last_sent_days_ago=0,
                stage_name="Award / Lost",
            ),
        )

    return ()


def _default_files(
    *,
    family: str,
    current_stage_name: str | None,
    completed_stage_names: tuple[str, ...],
    intelligence_profile: str,
    status: str,
    owner: str,
) -> tuple[FileSeed, ...]:
    reached_stage_names = set(completed_stage_names)
    if current_stage_name:
        reached_stage_names.add(current_stage_name)

    target_stage = current_stage_name or (completed_stage_names[-1] if completed_stage_names else None)
    if not reached_stage_names or target_stage is None:
        return ()

    seeded_files: list[FileSeed] = []

    def add_file(
        stage_name: str,
        filename: str,
        file_type: str,
        *,
        size_bytes: int,
        days_before_updated: int,
    ) -> None:
        if stage_name not in reached_stage_names:
            return
        if any(
            item.stage_name == stage_name
            and item.filename == filename
            and item.file_type == file_type
            for item in seeded_files
        ):
            return
        seeded_files.append(
            FileSeed(
                stage_name=stage_name,
                filename=filename,
                file_type=file_type,
                uploaded_by=owner,
                size_bytes=size_bytes,
                days_before_updated=days_before_updated,
            ),
        )

    include_source_package = (
        "RFQ received" in reached_stage_names
        and not (
            current_stage_name == "RFQ received"
            and intelligence_profile in {"none", "manual_golden"}
        )
    )
    if include_source_package:
        add_file(
            "RFQ received",
            "client-rfq-source-package.zip",
            "Client RFQ",
            size_bytes=1_850_000,
            days_before_updated=2,
        )

    cost_estimation_reached = "Cost estimation" in reached_stage_names
    workbook_is_late_lifecycle = (
        current_stage_name in {"Internal approval", "Offer submission", "Post-bid clarifications", "Award / Lost"}
        or status in {"Awarded", "Lost", "Cancelled"}
    )
    workbook_profile_requires_seed = intelligence_profile in {
        "failed_workbook",
        "mature_partial",
        "mature_partial_stale_award",
        "thin_partial_stale",
    }
    if cost_estimation_reached and (workbook_is_late_lifecycle or workbook_profile_requires_seed):
        add_file(
            "Cost estimation",
            "estimation-workbook.xlsx",
            "Estimation Workbook",
            size_bytes=325_000,
            days_before_updated=1,
        )

    supplementary_templates = {
        "Preliminary design": ("design-basis-review.pdf", "Design report"),
        "BOQ / BOM preparation": ("boq-bom-register.xlsx", "BOQ / BOM"),
        "Vendor inquiry": ("vendor-inquiry-log.xlsx", "Other"),
        "Internal approval": ("approval-brief.pdf", "Other"),
        "Offer submission": ("offer-submission-summary.pdf", "Other"),
        "Award / Lost": ("closeout-summary.pdf", "Other"),
    }
    filename, file_type = supplementary_templates.get(target_stage, ("rfq-stage-note.pdf", "Other"))
    add_file(
        target_stage,
        filename,
        file_type,
        size_bytes=245_000,
        days_before_updated=1,
    )

    return tuple(seeded_files)


def _materialize_scenario_defaults(spec: ManagerScenarioSpec) -> ManagerScenarioSpec:
    if spec.manual_only and not spec.files:
        return spec

    default_files = _default_files(
        family=spec.family,
        current_stage_name=spec.current_stage_name,
        completed_stage_names=spec.completed_stage_names,
        intelligence_profile=spec.intelligence_profile,
        status=spec.status,
        owner=spec.owner,
    )

    return replace(spec, files=spec.files if spec.files else default_files)


def _portfolio_scenario(
    *,
    key: str,
    batch: BatchName,
    family: str,
    workflow_code: str,
    name: str,
    client: str,
    industry: str,
    country: str,
    owner: str,
    priority: str,
    status: str,
    deadline_offset_days: int,
    created_days_ago: int,
    updated_days_ago: int,
    summary: str,
    current_stage_name: str | None,
    current_stage_progress: int = 0,
    completed_stage_names: tuple[str, ...] = (),
    blocker_reason_code: str | None = None,
    outcome_reason: str | None = None,
    intelligence_profile: str = "none",
    tags: tuple[str, ...] = (),
    notes: tuple[NoteSeed, ...] | None = None,
    subtasks: tuple[SubtaskSeed, ...] | None = None,
    reminders: tuple[ReminderSeed, ...] | None = None,
    files: tuple[FileSeed, ...] | None = None,
    skip_stage_names: tuple[str, ...] = (),
    captured_data_by_stage: dict[str, dict] | None = None,
    code_prefix: Literal["IF", "IB"] = "IF",
) -> ManagerScenarioSpec:
    default_note_stage = current_stage_name or (completed_stage_names[-1] if completed_stage_names else "RFQ received")
    scenario_notes = notes if notes is not None else (
        NoteSeed(
            stage_name=default_note_stage,
            user_name=owner,
            text=_default_note_text(family, default_note_stage, summary),
            days_before_updated=0,
        ),
    )

    return ManagerScenarioSpec(
        key=key,
        batch=batch,
        workflow_code=workflow_code,
        name=name,
        client=client,
        industry=industry,
        country=country,
        owner=owner,
        priority=priority,
        status=status,
        deadline_offset_days=deadline_offset_days,
        created_days_ago=created_days_ago,
        updated_days_ago=updated_days_ago,
        summary=summary,
        current_stage_name=current_stage_name,
        family=family,
        current_stage_progress=current_stage_progress,
        completed_stage_names=completed_stage_names,
        blocker_reason_code=blocker_reason_code,
        outcome_reason=outcome_reason,
        code_prefix=code_prefix,
        intelligence_profile=intelligence_profile,
        tags=tags,
        notes=scenario_notes,
        subtasks=subtasks if subtasks is not None else _default_subtasks(
            family=family,
            current_stage_name=current_stage_name,
            owner=owner,
        ),
        reminders=reminders if reminders is not None else _default_reminders(
            family=family,
            current_stage_name=current_stage_name,
            owner=owner,
        ),
        files=files if files is not None else _default_files(
            family=family,
            current_stage_name=current_stage_name,
            completed_stage_names=completed_stage_names,
            intelligence_profile=intelligence_profile,
            status=status,
            owner=owner,
        ),
        skip_stage_names=skip_stage_names,
        captured_data_by_stage=_build_captured_data(
            scenario_key=key,
            completed_stage_names=completed_stage_names,
            status=status,
            tags=tags,
            outcome_reason=outcome_reason,
            extra=captured_data_by_stage,
        ),
    )


def _build_must_have_extension_scenarios() -> tuple[ManagerScenarioSpec, ...]:
    return (
        _portfolio_scenario(
            key="RFQ-14",
            batch="must-have",
            family="fresh_intake",
            workflow_code="GHI-LONG",
            name="QAFCO Utilities Chemical Injection Pack",
            client="QAFCO",
            industry="Fertilizers",
            country="Qatar",
            owner="Karim Ben Ali",
            priority="critical",
            status="In preparation",
            deadline_offset_days=26,
            created_days_ago=3,
            updated_days_ago=0,
            summary="Freshly logged long-workflow RFQ still in intake posture with minimal reminder noise.",
            current_stage_name="RFQ received",
            current_stage_progress=12,
            intelligence_profile="none",
            tags=("fresh", "on_track"),
        ),
        _portfolio_scenario(
            key="RFQ-15",
            batch="must-have",
            family="healthy_mid_pipeline",
            workflow_code="GHI-SHORT",
            name="SEC Neutralization Module Refresh",
            client="Saudi Electricity Company",
            industry="Power",
            country="Saudi Arabia",
            owner="Omar Rahman",
            priority="normal",
            status="In preparation",
            deadline_offset_days=15,
            created_days_ago=13,
            updated_days_ago=1,
            summary="Short-workflow RFQ moving cleanly through cost estimation with no blocker pressure.",
            current_stage_name="Cost estimation",
            current_stage_progress=72,
            completed_stage_names=("RFQ received", "Go / No-Go"),
            intelligence_profile="early_partial",
            tags=("healthy", "on_track"),
        ),
        _portfolio_scenario(
            key="RFQ-16",
            batch="must-have",
            family="healthy_mid_pipeline",
            workflow_code="GHI-LONG",
            name="Jubail Firewater Pump House Upgrade",
            client="Royal Commission Jubail",
            industry="Infrastructure",
            country="Saudi Arabia",
            owner="Youssef Nasser",
            priority="critical",
            status="In preparation",
            deadline_offset_days=19,
            created_days_ago=21,
            updated_days_ago=1,
            summary="Healthy mid-pipeline RFQ with design work moving on plan and supporting artifacts present.",
            current_stage_name="Preliminary design",
            current_stage_progress=74,
            completed_stage_names=("RFQ received", "Go / No-Go", "Pre-bid clarifications"),
            intelligence_profile="mature_partial",
            tags=("healthy", "on_track"),
        ),
        _portfolio_scenario(
            key="RFQ-17",
            batch="must-have",
            family="healthy_mid_pipeline",
            workflow_code="GHI-CUSTOM",
            name="ADNOC Utility Dosing Skid Revamp",
            client="ADNOC",
            industry="Oil & Gas",
            country="UAE",
            owner="Maya Fares",
            priority="normal",
            status="In preparation",
            deadline_offset_days=17,
            created_days_ago=25,
            updated_days_ago=1,
            summary="Vendor inquiry is active with healthy follow-through and no blocker or overdue posture.",
            current_stage_name="Vendor inquiry",
            current_stage_progress=61,
            completed_stage_names=("RFQ received", "Go / No-Go", "Preliminary design"),
            intelligence_profile="mature_partial",
            tags=("healthy", "on_track", "custom_workflow"),
            skip_stage_names=("Pre-bid clarifications", "BOQ / BOM preparation", "Post-bid clarifications"),
        ),
        _portfolio_scenario(
            key="RFQ-18",
            batch="must-have",
            family="healthy_mid_pipeline",
            workflow_code="GHI-SHORT",
            name="SWCC Chlorination Booster Skid",
            client="SWCC",
            industry="Water",
            country="Saudi Arabia",
            owner="Ahmed Proposal Ops",
            priority="normal",
            status="In preparation",
            deadline_offset_days=10,
            created_days_ago=12,
            updated_days_ago=0,
            summary="Compact short-workflow RFQ staying active and readable in the mid-pipeline queue.",
            current_stage_name="Cost estimation",
            current_stage_progress=84,
            completed_stage_names=("RFQ received", "Go / No-Go"),
            intelligence_profile="early_partial",
            tags=("healthy", "active"),
        ),
        _portfolio_scenario(
            key="RFQ-19",
            batch="must-have",
            family="deadline_watch",
            workflow_code="GHI-SHORT",
            name="Tasnee Caustic Dosing Retrofit",
            client="Tasnee",
            industry="Chemicals",
            country="Saudi Arabia",
            owner="Sara Ben Ali",
            priority="critical",
            status="In preparation",
            deadline_offset_days=2,
            created_days_ago=16,
            updated_days_ago=0,
            summary="Near-deadline short workflow still under control but clearly in watch mode.",
            current_stage_name="Internal approval",
            current_stage_progress=88,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation"),
            intelligence_profile="mature_partial",
            tags=("deadline_near", "watchlist"),
        ),
        _portfolio_scenario(
            key="RFQ-20",
            batch="must-have",
            family="stale_execution",
            workflow_code="GHI-LONG",
            name="QatarEnergy Produced Water Dosing Train",
            client="QatarEnergy",
            industry="Oil & Gas",
            country="Qatar",
            owner="Dina Engineering",
            priority="critical",
            status="In preparation",
            deadline_offset_days=-2,
            created_days_ago=33,
            updated_days_ago=0,
            summary="Late-stage cost estimation has gone stale and is now visibly overdue.",
            current_stage_name="Cost estimation",
            current_stage_progress=48,
            completed_stage_names=(
                "RFQ received",
                "Go / No-Go",
                "Pre-bid clarifications",
                "Preliminary design",
                "BOQ / BOM preparation",
                "Vendor inquiry",
            ),
            intelligence_profile="stale_partial",
            tags=("stale", "overdue"),
        ),
        _portfolio_scenario(
            key="RFQ-21",
            batch="must-have",
            family="blocked_internal_hold",
            workflow_code="GHI-LONG",
            name="KNPC Chemical Dosing Header Upgrade",
            client="KNPC",
            industry="Oil & Gas",
            country="Kuwait",
            owner="Youssef Nasser",
            priority="critical",
            status="In preparation",
            deadline_offset_days=9,
            created_days_ago=18,
            updated_days_ago=0,
            summary="Internal design decision is holding the stage until the revised technical basis is accepted.",
            current_stage_name="Preliminary design",
            current_stage_progress=18,
            completed_stage_names=("RFQ received", "Go / No-Go", "Pre-bid clarifications"),
            blocker_reason_code="technical_review_hold",
            intelligence_profile="early_partial",
            tags=("blocked", "internal_hold"),
            captured_data_by_stage={"Preliminary design": {"design_approved": False}},
        ),
        _portfolio_scenario(
            key="RFQ-22",
            batch="must-have",
            family="blocked_client_hold",
            workflow_code="GHI-LONG",
            name="SEC Boiler Feed Conditioning Module",
            client="Saudi Electricity Company",
            industry="Power",
            country="Saudi Arabia",
            owner="Maya Fares",
            priority="critical",
            status="In preparation",
            deadline_offset_days=4,
            created_days_ago=19,
            updated_days_ago=0,
            summary="Client clarification backlog is still holding the pre-bid stage open.",
            current_stage_name="Pre-bid clarifications",
            current_stage_progress=36,
            completed_stage_names=("RFQ received", "Go / No-Go"),
            blocker_reason_code="waiting_client_docs",
            intelligence_profile="none",
            tags=("blocked", "client_hold"),
        ),
        _portfolio_scenario(
            key="RFQ-23",
            batch="must-have",
            family="blocked_client_hold",
            workflow_code="GHI-LONG",
            name="Maaden Process Water Dosing Line",
            client="Maaden",
            industry="Mining",
            country="Saudi Arabia",
            owner="Karim Ben Ali",
            priority="normal",
            status="In preparation",
            deadline_offset_days=6,
            created_days_ago=23,
            updated_days_ago=0,
            summary="Vendor inquiry cannot advance until the client confirms final approved vendor list.",
            current_stage_name="Vendor inquiry",
            current_stage_progress=28,
            completed_stage_names=(
                "RFQ received",
                "Go / No-Go",
                "Pre-bid clarifications",
                "Preliminary design",
                "BOQ / BOM preparation",
            ),
            blocker_reason_code="waiting_client_docs",
            intelligence_profile="early_partial",
            tags=("blocked", "client_hold"),
        ),
        _portfolio_scenario(
            key="RFQ-24",
            batch="must-have",
            family="blocked_client_hold",
            workflow_code="GHI-SHORT",
            name="BAPCO Neutralization Package Refresh",
            client="BAPCO",
            industry="Oil & Gas",
            country="Bahrain",
            owner="Omar Rahman",
            priority="normal",
            status="In preparation",
            deadline_offset_days=3,
            created_days_ago=14,
            updated_days_ago=0,
            summary="Short-workflow RFQ is blocked in cost estimation pending missing client scope confirmation.",
            current_stage_name="Cost estimation",
            current_stage_progress=34,
            completed_stage_names=("RFQ received", "Go / No-Go"),
            blocker_reason_code="waiting_client_docs",
            intelligence_profile="none",
            tags=("blocked", "client_hold"),
        ),
        _portfolio_scenario(
            key="RFQ-25",
            batch="must-have",
            family="blocked_internal_hold",
            workflow_code="GHI-LONG",
            name="SATORP Chemical Injection Panel Refresh",
            client="SATORP",
            industry="Oil & Gas",
            country="Saudi Arabia",
            owner="Dina Engineering",
            priority="critical",
            status="In preparation",
            deadline_offset_days=11,
            created_days_ago=20,
            updated_days_ago=0,
            summary="BOQ cannot advance until the design-approved decision is closed internally.",
            current_stage_name="Preliminary design",
            current_stage_progress=22,
            completed_stage_names=("RFQ received", "Go / No-Go", "Pre-bid clarifications"),
            blocker_reason_code="design_review_hold",
            intelligence_profile="early_partial",
            tags=("blocked", "internal_hold"),
            captured_data_by_stage={"Preliminary design": {"design_approved": False}},
        ),
        _portfolio_scenario(
            key="RFQ-26",
            batch="must-have",
            family="blocked_internal_hold",
            workflow_code="GHI-LONG",
            name="Q-Chem Package Transfer Module",
            client="Q-Chem",
            industry="Petrochemicals",
            country="Qatar",
            owner="Ahmed Proposal Ops",
            priority="normal",
            status="In preparation",
            deadline_offset_days=12,
            created_days_ago=22,
            updated_days_ago=0,
            summary="Internal BOQ completion decision is holding the RFQ before commercial work can proceed.",
            current_stage_name="BOQ / BOM preparation",
            current_stage_progress=18,
            completed_stage_names=("RFQ received", "Go / No-Go", "Pre-bid clarifications", "Preliminary design"),
            blocker_reason_code="boq_review_hold",
            intelligence_profile="thin_partial_stale",
            tags=("blocked", "internal_hold"),
            captured_data_by_stage={"BOQ / BOM preparation": {"boq_completed": False}},
        ),
        _portfolio_scenario(
            key="RFQ-27",
            batch="must-have",
            family="decision_wait_followup",
            workflow_code="GHI-LONG",
            name="SWCC Demineralized Water Recovery Package",
            client="SWCC",
            industry="Water",
            country="Saudi Arabia",
            owner="Maya Fares",
            priority="critical",
            status="In preparation",
            deadline_offset_days=-5,
            created_days_ago=34,
            updated_days_ago=2,
            summary="Offer already delivered; long-workflow RFQ is waiting in the final decision stage with follow-up reminders and slightly stale post-offer posture.",
            current_stage_name="Award / Lost",
            current_stage_progress=30,
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
            ),
            intelligence_profile="thin_partial_stale",
            tags=("decision_wait", "stale_followup"),
        ),
        _portfolio_scenario(
            key="RFQ-28",
            batch="must-have",
            family="decision_wait_followup",
            workflow_code="GHI-SHORT",
            name="Marafiq Cooling Tower Dosing Retrofit",
            client="Marafiq",
            industry="Utilities",
            country="Saudi Arabia",
            owner="Sara Ben Ali",
            priority="normal",
            status="In preparation",
            deadline_offset_days=-1,
            created_days_ago=19,
            updated_days_ago=1,
            summary="Offer already delivered; short-workflow RFQ is waiting in the final decision stage with healthy follow-up posture and no active blocker.",
            current_stage_name="Award / Lost",
            current_stage_progress=22,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission"),
            intelligence_profile="mature_partial",
            tags=("decision_wait", "healthy_followup"),
        ),
        _portfolio_scenario(
            key="RFQ-29",
            batch="must-have",
            family="decision_wait_followup",
            workflow_code="GHI-CUSTOM",
            name="ADCO Chemical Feed Pump Renewal",
            client="ADCO",
            industry="Oil & Gas",
            country="UAE",
            owner="Karim Ben Ali",
            priority="normal",
            status="In preparation",
            deadline_offset_days=-3,
            created_days_ago=31,
            updated_days_ago=1,
            summary="Offer already delivered; RFQ is waiting in the final decision stage while client follow-up remains active and the package itself is complete.",
            current_stage_name="Award / Lost",
            current_stage_progress=26,
            completed_stage_names=(
                "RFQ received",
                "Go / No-Go",
                "Preliminary design",
                "Vendor inquiry",
                "Cost estimation",
                "Internal approval",
                "Offer submission",
            ),
            intelligence_profile="mature_partial",
            tags=("decision_wait", "client_followup", "custom_workflow"),
            skip_stage_names=("Pre-bid clarifications", "BOQ / BOM preparation", "Post-bid clarifications"),
        ),
        _portfolio_scenario(
            key="RFQ-30",
            batch="must-have",
            family="decision_wait_followup",
            workflow_code="GHI-LONG",
            name="SABIC Effluent Neutralization Rack",
            client="SABIC",
            industry="Petrochemicals",
            country="Saudi Arabia",
            owner="Omar Rahman",
            priority="critical",
            status="In preparation",
            deadline_offset_days=-4,
            created_days_ago=37,
            updated_days_ago=1,
            summary="Critical post-offer RFQ waiting in the final decision stage to validate follow-up pressure in the queue and reminder center.",
            current_stage_name="Award / Lost",
            current_stage_progress=34,
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
            ),
            intelligence_profile="mature_partial",
            tags=("decision_wait", "critical_watch"),
        ),
    )


def _build_later_extension_scenarios() -> tuple[ManagerScenarioSpec, ...]:
    return (
        _portfolio_scenario(
            key="RFQ-31",
            batch="later",
            family="decision_wait_followup",
            workflow_code="GHI-SHORT",
            name="SEC Sodium Hypochlorite Skid Replacement",
            client="Saudi Electricity Company",
            industry="Power",
            country="Saudi Arabia",
            owner="Ahmed Proposal Ops",
            priority="critical",
            status="In preparation",
            deadline_offset_days=-2,
            created_days_ago=23,
            updated_days_ago=0,
            summary="Short-workflow post-offer RFQ waiting in a compressed outcome window and worth watching closely.",
            current_stage_name="Award / Lost",
            current_stage_progress=28,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission"),
            intelligence_profile="mature_partial",
            tags=("decision_wait", "deadline_near"),
        ),
        _portfolio_scenario(
            key="RFQ-32",
            batch="later",
            family="awarded_terminal",
            workflow_code="GHI-LONG",
            name="Sadara Utility Dosing Package",
            client="Sadara",
            industry="Petrochemicals",
            country="Saudi Arabia",
            owner="Youssef Nasser",
            priority="critical",
            status="Awarded",
            deadline_offset_days=-14,
            created_days_ago=58,
            updated_days_ago=4,
            summary="Awarded long-workflow package with complete lifecycle trail and clean closeout.",
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
            outcome_reason="Award confirmed after final technical and commercial alignment.",
            intelligence_profile="mature_partial",
            tags=("terminal", "awarded"),
        ),
        _portfolio_scenario(
            key="RFQ-33",
            batch="later",
            family="awarded_terminal",
            workflow_code="GHI-LONG",
            name="Bahrain Water Distribution Rack",
            client="Bahrain Water Authority",
            industry="Water",
            country="Bahrain",
            owner="Maya Fares",
            priority="normal",
            status="Awarded",
            deadline_offset_days=-11,
            created_days_ago=53,
            updated_days_ago=5,
            summary="Awarded RFQ kept as a clean reference for successful long-workflow closeout.",
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
            outcome_reason="Client confirmed award following final compliance review.",
            intelligence_profile="mature_partial",
            tags=("terminal", "awarded"),
        ),
        _portfolio_scenario(
            key="RFQ-34",
            batch="later",
            family="awarded_terminal",
            workflow_code="GHI-SHORT",
            name="SEC Dosing Panel Standard Package",
            client="Saudi Electricity Company",
            industry="Power",
            country="Saudi Arabia",
            owner="Omar Rahman",
            priority="normal",
            status="Awarded",
            deadline_offset_days=-9,
            created_days_ago=36,
            updated_days_ago=3,
            summary="Awarded short-workflow RFQ for a compact but complete terminal reference.",
            current_stage_name=None,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission", "Award / Lost"),
            outcome_reason="Award confirmed within the original offer window.",
            intelligence_profile="mature_partial",
            tags=("terminal", "awarded"),
        ),
        _portfolio_scenario(
            key="RFQ-35",
            batch="later",
            family="lost_terminal",
            workflow_code="GHI-LONG",
            name="QAFAC Chemical Injection Shelter",
            client="QAFAC",
            industry="Chemicals",
            country="Qatar",
            owner="Karim Ben Ali",
            priority="critical",
            status="Lost",
            deadline_offset_days=-12,
            created_days_ago=56,
            updated_days_ago=5,
            summary="Lost RFQ intentionally using the Other reason path so closeout detail stays visible.",
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
            outcome_reason="Client shifted the package into a wider framework scope after submission.",
            intelligence_profile="thin_partial_stale",
            tags=("terminal", "lost", "loss_other"),
        ),
        _portfolio_scenario(
            key="RFQ-36",
            batch="later",
            family="lost_terminal",
            workflow_code="GHI-LONG",
            name="PetroRabigh Neutralization Upgrade",
            client="PetroRabigh",
            industry="Petrochemicals",
            country="Saudi Arabia",
            owner="Ahmed Proposal Ops",
            priority="normal",
            status="Lost",
            deadline_offset_days=-10,
            created_days_ago=49,
            updated_days_ago=4,
            summary="Lost RFQ where the commercial gap was recorded after final ranking feedback.",
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
            outcome_reason="Lost on commercial ranking after final bid normalization.",
            intelligence_profile="thin_partial_stale",
            tags=("terminal", "lost"),
        ),
        _portfolio_scenario(
            key="RFQ-37",
            batch="later",
            family="lost_terminal",
            workflow_code="GHI-SHORT",
            name="Marafiq Dosing Skid Fast-Track Package",
            client="Marafiq",
            industry="Utilities",
            country="Saudi Arabia",
            owner="Sara Ben Ali",
            priority="normal",
            status="Lost",
            deadline_offset_days=-7,
            created_days_ago=34,
            updated_days_ago=3,
            summary="Short-workflow loss used to keep terminal closeout visible in simpler pursuits too.",
            current_stage_name=None,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval", "Offer submission", "Award / Lost"),
            outcome_reason="Client strategy changed before award recommendation.",
            intelligence_profile="thin_partial_stale",
            tags=("terminal", "lost"),
        ),
    )


def _build_optional_extension_scenarios() -> tuple[ManagerScenarioSpec, ...]:
    return (
        _portfolio_scenario(
            key="RFQ-38",
            batch="optional",
            family="cancelled_terminal",
            workflow_code="GHI-LONG",
            name="SWCC Intake Neutralization Extension",
            client="SWCC",
            industry="Water",
            country="Saudi Arabia",
            owner="Maya Fares",
            priority="normal",
            status="Cancelled",
            deadline_offset_days=20,
            created_days_ago=9,
            updated_days_ago=2,
            summary="Early cancellation captured after intake review, leaving downstream stages unexecuted.",
            current_stage_name=None,
            completed_stage_names=("RFQ received",),
            outcome_reason="Client withdrew the package before qualification closed.",
            intelligence_profile="none",
            tags=("terminal", "cancelled", "early_cancel"),
        ),
        _portfolio_scenario(
            key="RFQ-39",
            batch="optional",
            family="cancelled_terminal",
            workflow_code="GHI-LONG",
            name="Aramco Corrosion Inhibitor Package",
            client="Saudi Aramco",
            industry="Oil & Gas",
            country="Saudi Arabia",
            owner="Karim Ben Ali",
            priority="critical",
            status="Cancelled",
            deadline_offset_days=9,
            created_days_ago=27,
            updated_days_ago=3,
            summary="Mid-lifecycle cancellation used to validate skipped downstream path visuals and closeout reasoning.",
            current_stage_name=None,
            completed_stage_names=(
                "RFQ received",
                "Go / No-Go",
                "Pre-bid clarifications",
                "Preliminary design",
            ),
            outcome_reason="Client funding hold cancelled the opportunity after design review.",
            intelligence_profile="early_partial",
            tags=("terminal", "cancelled", "mid_cancel"),
        ),
        _portfolio_scenario(
            key="RFQ-40",
            batch="optional",
            family="cancelled_terminal",
            workflow_code="GHI-LONG",
            name="QAFCO Caustic Recovery Skid",
            client="QAFCO",
            industry="Fertilizers",
            country="Qatar",
            owner="Youssef Nasser",
            priority="normal",
            status="Cancelled",
            deadline_offset_days=4,
            created_days_ago=38,
            updated_days_ago=2,
            summary="Late cancellation after submission keeps a visible trail without pretending the downstream path completed successfully.",
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
            ),
            outcome_reason="Client cancelled the procurement after scope consolidation.",
            intelligence_profile="mature_partial",
            tags=("terminal", "cancelled", "late_cancel"),
        ),
        _portfolio_scenario(
            key="RFQ-41",
            batch="optional",
            family="cancelled_terminal",
            workflow_code="GHI-SHORT",
            name="BAPCO Neutralization Skid Renewal",
            client="BAPCO",
            industry="Oil & Gas",
            country="Bahrain",
            owner="Omar Rahman",
            priority="normal",
            status="Cancelled",
            deadline_offset_days=7,
            created_days_ago=22,
            updated_days_ago=1,
            summary="Short-workflow cancellation reserved to keep terminal variety realistic beyond long-form pursuits.",
            current_stage_name=None,
            completed_stage_names=("RFQ received", "Go / No-Go", "Cost estimation", "Internal approval"),
            outcome_reason="Client cancelled before commercial submission window reopened.",
            intelligence_profile="early_partial",
            tags=("terminal", "cancelled", "short_cancel"),
        ),
    )


SCENARIOS = (
    SCENARIOS
    + _build_must_have_extension_scenarios()
    + _build_later_extension_scenarios()
    + _build_optional_extension_scenarios()
)


def scenario_registry() -> dict[str, ManagerScenarioSpec]:
    return {
        scenario.key: _materialize_scenario_defaults(scenario)
        for scenario in SCENARIOS
    }


def seeded_scenarios_for_batch(batch: Literal["must-have", "later", "optional", "all"]) -> list[ManagerScenarioSpec]:
    scenarios = [
        _materialize_scenario_defaults(scenario)
        for scenario in SCENARIOS
        if not scenario.manual_only
    ]
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


VERIFICATION_ROLE_EXPECTATIONS: dict[str, dict] = {
    "intelligence_snapshot_anchor": {
        "expected_snapshot_artifact_type": "rfq_intelligence_snapshot",
    },
    "stale_snapshot_anchor": {
        "expected_snapshot_stale_relative_to_manager": True,
    },
    "decision_wait_anchor": {
        "expected_status": "In preparation",
        "expected_current_stage_name": "Award / Lost",
    },
    "workbook_artifact_anchor": {
        "expected_profile_artifact_type": "workbook_profile",
        "expected_review_artifact_type": "workbook_review_report",
        "requires_artifacts": True,
    },
    "failed_workbook_anchor": {
        "expected_workbook_review_http_status": 404,
    },
}


def _build_verification_targets(entries: list[dict]) -> dict[str, dict]:
    entry_by_key = {entry["scenario_key"]: entry for entry in entries}
    targets: dict[str, dict] = {}

    for scenario in SCENARIOS:
        if scenario.manual_only or not scenario.verification_roles:
            continue
        entry = entry_by_key.get(scenario.key)
        if entry is None:
            continue
        for role in scenario.verification_roles:
            targets[role] = {
                "scenario_key": scenario.key,
                "rfq_id": entry["rfq_id"],
                "status": entry["status"],
                "current_stage_name": entry["current_stage_name"],
                **VERIFICATION_ROLE_EXPECTATIONS.get(role, {}),
            }

    return targets


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


def _calculate_rfq_progress(stages: list[RFQStage], rfq_status: str) -> int:
    return calculate_rfq_lifecycle_progress(stages, rfq_status)


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


def _seed_files(session, stage_map: dict[str, RFQStage], spec: ManagerScenarioSpec, updated_at: datetime) -> None:
    for index, file_seed in enumerate(spec.files):
        stage = stage_map[file_seed.stage_name]
        file_record = RFQFile(
            rfq_stage_id=stage.id,
            filename=file_seed.filename,
            file_path=f"./scenario_uploads/{spec.key.lower()}/{file_seed.filename}",
            type=file_seed.file_type,
            uploaded_by=file_seed.uploaded_by,
            size_bytes=file_seed.size_bytes,
        )
        session.add(file_record)
        session.flush()
        file_record.uploaded_at = updated_at - timedelta(days=file_seed.days_before_updated, hours=index)


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
    _seed_files(session, stage_map, spec, updated_at)

    for stage in stages:
        _apply_stage_progress_from_subtasks(session, stage)

    rfq.status = spec.status
    rfq.outcome_reason = spec.outcome_reason
    rfq.current_stage_id = current_stage.id if current_stage and spec.status not in {"Awarded", "Lost", "Cancelled"} else None
    rfq.progress = _calculate_rfq_progress(stages, rfq.status)

    _seed_reminders(session, rfq, stage_map, spec, updated_at)

    for index, stage in enumerate(stages):
        stage_created_at = created_at + timedelta(days=index)
        stage_updated_at = updated_at if (stage.status != "Not Started" or stage.blocker_status) else stage_created_at
        _set_model_timestamps(stage, created_at=stage_created_at, updated_at=stage_updated_at)

    _set_model_timestamps(rfq, created_at=created_at, updated_at=updated_at)


def _build_manifest_entry(session, scenario: ManagerScenarioSpec, rfq: RFQ) -> dict:
    current_stage_name = None
    blocker_reason_code = None
    if rfq.current_stage_id:
        current_stage = session.query(RFQStage).filter(RFQStage.id == rfq.current_stage_id).first()
        current_stage_name = current_stage.name if current_stage else None
        blocker_reason_code = current_stage.blocker_reason_code if current_stage else None
    reminder_count = session.query(Reminder).filter(Reminder.rfq_id == rfq.id).count()
    note_count = (
        session.query(RFQNote)
        .join(RFQStage, RFQStage.id == RFQNote.rfq_stage_id)
        .filter(RFQStage.rfq_id == rfq.id)
        .count()
    )
    subtask_count = (
        session.query(Subtask)
        .join(RFQStage, RFQStage.id == Subtask.rfq_stage_id)
        .filter(RFQStage.rfq_id == rfq.id, Subtask.deleted_at.is_(None))
        .count()
    )
    file_count = (
        session.query(RFQFile)
        .join(RFQStage, RFQStage.id == RFQFile.rfq_stage_id)
        .filter(RFQStage.rfq_id == rfq.id, RFQFile.deleted_at.is_(None))
        .count()
    )
    return {
        "scenario_key": scenario.key,
        "batch": scenario.batch,
        "family": scenario.family,
        "tags": list(scenario.tags),
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
        "blocked": blocker_reason_code is not None,
        "blocker_reason_code": blocker_reason_code,
        "reminder_count": reminder_count,
        "note_count": note_count,
        "subtask_count": subtask_count,
        "file_count": file_count,
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
    scenario_deadline = date.today() + timedelta(days=scenario.deadline_offset_days)
    effective_stages = controller._resolve_effective_workflow_stages(workflow)
    stage_template_lookup = {stage.name: stage.id for stage in effective_stages}
    minimum_feasible_deadline = (
        controller._calculate_minimum_feasible_deadline(effective_stages)
        if effective_stages
        else date.today()
    )
    create_deadline = max(scenario_deadline, minimum_feasible_deadline)
    request = RfqCreateRequest(
        name=scenario.name,
        client=scenario.client,
        deadline=create_deadline,
        owner=scenario.owner,
        workflow_id=workflow.id,
        industry=scenario.industry,
        country=scenario.country,
        priority=scenario.priority,
        description=scenario.description,
        code_prefix=scenario.code_prefix,
        skip_stages=[
            stage_template_lookup[stage_name]
            for stage_name in scenario.skip_stage_names
        ] if scenario.skip_stage_names else None,
    )
    detail = controller.create(request)
    rfq = session.query(RFQ).filter(RFQ.id == detail.id).first()
    if rfq is None:
        raise RuntimeError(f"Failed to create scenario RFQ '{scenario.key}'")
    if scenario_deadline != create_deadline:
        controller._recalculate_stage_dates(rfq, scenario_deadline, workflow=workflow)
        rfq.deadline = scenario_deadline
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

    manifest_entries = _load_existing_seeded_entries(session)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": _utc_now().isoformat(),
        "requested_batch": batch,
        "golden_reserved_scenario": GOLDEN_SCENARIO_KEY,
        "manual_reserved": _manual_reserved_entries(),
        "verification_targets": _build_verification_targets(manifest_entries),
        "scenarios": manifest_entries,
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

    run_migrations(reset=args.reset)
    _, session_factory = make_engine_and_session()
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

from __future__ import annotations

from datetime import date, timedelta

from scripts.seed_rfqmgmt_scenarios import (
    GOLDEN_SCENARIO_KEY,
    SCENARIO_TAG_PREFIX,
    seeded_scenarios_for_batch,
    seed_manager_scenarios,
)
from src.models.reminder import Reminder
from src.models.rfq import RFQ
from src.models.rfq_file import RFQFile
from src.models.rfq_stage import RFQStage


def _rfq_by_scenario(db_session, scenario_key: str) -> RFQ:
    rfq = (
        db_session.query(RFQ)
        .filter(RFQ.description.like(f"{SCENARIO_TAG_PREFIX}{scenario_key}]%"))
        .first()
    )
    assert rfq is not None
    return rfq


def _stage_by_name(db_session, rfq_id, stage_name: str) -> RFQStage:
    stage = (
        db_session.query(RFQStage)
        .filter(RFQStage.rfq_id == rfq_id, RFQStage.name == stage_name)
        .first()
    )
    assert stage is not None
    return stage


def _files_for_rfq(db_session, rfq_id) -> list[RFQFile]:
    return (
        db_session.query(RFQFile)
        .join(RFQStage, RFQStage.id == RFQFile.rfq_stage_id)
        .filter(RFQStage.rfq_id == rfq_id, RFQFile.deleted_at.is_(None))
        .all()
    )


def test_must_have_batch_seeds_expected_scenarios_and_keeps_golden_manual(db_session):
    result = seed_manager_scenarios(db_session, batch="must-have")

    seeded_keys = {item["scenario_key"] for item in result["manifest"]["scenarios"]}
    assert {
        "RFQ-01",
        "RFQ-02",
        "RFQ-03",
        "RFQ-04",
        "RFQ-14",
        "RFQ-20",
        "RFQ-24",
        "RFQ-30",
        "RFQ-09",
        "RFQ-10",
        "RFQ-11",
    }.issubset(seeded_keys)
    assert len(seeded_keys) == 24
    assert GOLDEN_SCENARIO_KEY not in seeded_keys
    assert len(result["created_scenarios"]) == 24
    assert result["manifest"]["golden_reserved_scenario"] == GOLDEN_SCENARIO_KEY
    assert result["manifest"]["manual_reserved"] == [
        {
            "scenario_key": "RFQ-06",
            "name": "SWCC Pretreatment Dosing Package",
            "workflow_code": "GHI-LONG",
            "priority": "critical",
            "status": "In preparation",
            "summary": "Reserved manual-only golden journey. Never pre-seeded.",
            "manual_only": True,
        }
    ]
    verification_targets = result["manifest"]["verification_targets"]
    assert verification_targets["intelligence_snapshot_anchor"]["scenario_key"] == "RFQ-02"
    assert verification_targets["stale_snapshot_anchor"]["scenario_key"] == "RFQ-04"
    assert verification_targets["decision_wait_anchor"] == {
        "scenario_key": "RFQ-09",
        "rfq_id": verification_targets["decision_wait_anchor"]["rfq_id"],
        "status": "In preparation",
        "current_stage_name": "Award / Lost",
        "expected_status": "In preparation",
        "expected_current_stage_name": "Award / Lost",
    }
    assert verification_targets["workbook_artifact_anchor"]["scenario_key"] == "RFQ-09"
    assert "failed_workbook_anchor" not in verification_targets
    manifest_entry = next(item for item in result["manifest"]["scenarios"] if item["scenario_key"] == "RFQ-20")
    assert manifest_entry["family"] == "stale_execution"
    assert manifest_entry["file_count"] >= 1
    assert manifest_entry["subtask_count"] >= 1


def test_scenario_seed_rerun_is_idempotent_for_existing_batch(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    second = seed_manager_scenarios(db_session, batch="must-have")

    assert second["created_scenarios"] == []
    assert set(second["existing_scenarios"]) == {
        scenario.key for scenario in seeded_scenarios_for_batch("must-have")
    }
    assert len(second["manifest"]["scenarios"]) == 24


def test_later_and_optional_batches_only_seed_their_own_scenarios(db_session):
    later = seed_manager_scenarios(db_session, batch="later")
    later_keys = {item["scenario_key"] for item in later["manifest"]["scenarios"]}
    assert later_keys == {scenario.key for scenario in seeded_scenarios_for_batch("later")}
    assert len(later_keys) == 10
    assert later["manifest"]["verification_targets"]["failed_workbook_anchor"]["scenario_key"] == "RFQ-07"

    optional = seed_manager_scenarios(db_session, batch="optional")
    optional_keys = {item["scenario_key"] for item in optional["manifest"]["scenarios"]}
    assert optional_keys == {
        *(scenario.key for scenario in seeded_scenarios_for_batch("later")),
        *(scenario.key for scenario in seeded_scenarios_for_batch("optional")),
    }
    assert len(optional_keys) == 16


def test_all_batch_contains_full_portfolio_plus_manual_reservation(db_session):
    result = seed_manager_scenarios(db_session, batch="all")

    seeded_keys = {item["scenario_key"] for item in result["manifest"]["scenarios"]}
    workflow_codes = {item["workflow_code"] for item in result["manifest"]["scenarios"]}

    assert len(seeded_keys) == 40
    assert "RFQ-41" in seeded_keys
    assert GOLDEN_SCENARIO_KEY not in seeded_keys
    assert "GHI-CUSTOM" in workflow_codes


def test_blocked_overdue_scenario_has_expected_operational_pressure(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfq = _rfq_by_scenario(db_session, "RFQ-03")
    stage = _stage_by_name(db_session, rfq.id, "Pre-bid clarifications")
    reminders = db_session.query(Reminder).filter(Reminder.rfq_id == rfq.id).all()

    assert rfq.status == "In preparation"
    assert rfq.priority == "critical"
    assert rfq.deadline < date.today()
    assert rfq.current_stage_id == stage.id

    assert stage.status == "In Progress"
    assert stage.blocker_status == "Blocked"
    assert stage.blocker_reason_code == "waiting_client_docs"

    assert len(reminders) == 3
    assert {reminder.status for reminder in reminders} == {"open", "overdue"}
    assert any(reminder.send_count == 1 for reminder in reminders)


def test_tight_future_scenario_keeps_its_intended_deadline_after_safe_seed_create(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfq = _rfq_by_scenario(db_session, "RFQ-04")

    assert rfq.deadline == date.today() + timedelta(days=14)


def test_seeded_active_rfq_progress_reflects_lifecycle_completion_not_stage_workload(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfq = _rfq_by_scenario(db_session, "RFQ-04")

    assert rfq.progress == 27


def test_early_intelligence_anchor_has_source_package_file(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfq = _rfq_by_scenario(db_session, "RFQ-02")
    files = _files_for_rfq(db_session, rfq.id)

    assert any(file.type == "Client RFQ" for file in files)
    assert any(file.filename == "client-rfq-source-package.zip" for file in files)


def test_decision_wait_anchor_has_package_and_workbook_files(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    rfq = _rfq_by_scenario(db_session, "RFQ-09")
    files = _files_for_rfq(db_session, rfq.id)
    file_types = {file.type for file in files}

    assert "Client RFQ" in file_types
    assert "Estimation Workbook" in file_types


def test_cost_estimation_in_progress_scenario_keeps_package_without_workbook(db_session):
    seed_manager_scenarios(db_session, batch="later")

    rfq = _rfq_by_scenario(db_session, "RFQ-05")
    files = _files_for_rfq(db_session, rfq.id)
    file_types = {file.type for file in files}

    assert "Client RFQ" in file_types
    assert "Estimation Workbook" not in file_types

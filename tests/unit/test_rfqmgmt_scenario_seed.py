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

from __future__ import annotations

from datetime import date

from scripts.seed_rfqmgmt_scenarios import (
    GOLDEN_SCENARIO_KEY,
    SCENARIO_TAG_PREFIX,
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
    assert seeded_keys == {
        "RFQ-01",
        "RFQ-02",
        "RFQ-03",
        "RFQ-04",
        "RFQ-09",
        "RFQ-10",
        "RFQ-11",
    }
    assert GOLDEN_SCENARIO_KEY not in seeded_keys
    assert result["created_scenarios"] == [
        "RFQ-01",
        "RFQ-02",
        "RFQ-03",
        "RFQ-04",
        "RFQ-09",
        "RFQ-10",
        "RFQ-11",
    ]
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


def test_scenario_seed_rerun_is_idempotent_for_existing_batch(db_session):
    seed_manager_scenarios(db_session, batch="must-have")

    second = seed_manager_scenarios(db_session, batch="must-have")

    assert second["created_scenarios"] == []
    assert set(second["existing_scenarios"]) == {
        "RFQ-01",
        "RFQ-02",
        "RFQ-03",
        "RFQ-04",
        "RFQ-09",
        "RFQ-10",
        "RFQ-11",
    }
    assert len(second["manifest"]["scenarios"]) == 7


def test_later_and_optional_batches_only_seed_their_own_scenarios(db_session):
    later = seed_manager_scenarios(db_session, batch="later")
    later_keys = {item["scenario_key"] for item in later["manifest"]["scenarios"]}
    assert later_keys == {"RFQ-05", "RFQ-07", "RFQ-08"}

    optional = seed_manager_scenarios(db_session, batch="optional")
    optional_keys = {item["scenario_key"] for item in optional["manifest"]["scenarios"]}
    assert optional_keys == {"RFQ-05", "RFQ-07", "RFQ-08", "RFQ-12", "RFQ-13"}


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
    assert {reminder.status for reminder in reminders} == {"open", "sent"}
    assert any(reminder.send_count == 1 for reminder in reminders)

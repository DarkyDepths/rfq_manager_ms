from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from src.models.rfq_stage import RFQStage
from src.utils.errors import ConflictError
from src.utils.rfq_status import RFQ_TERMINAL_STATUSES, RFQ_VALID_STATUS_TRANSITIONS


def validate_rfq_status_transition(current_status: str, new_status: str) -> None:
    if new_status == current_status:
        return

    allowed_next = RFQ_VALID_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed_next:
        raise ConflictError(
            f"Invalid RFQ status transition from '{current_status}' to '{new_status}'."
        )


def calculate_rfq_lifecycle_progress(stages, rfq_status: str | None = None) -> int:
    if rfq_status in RFQ_TERMINAL_STATUSES:
        return 100

    effective_stages = [stage for stage in stages if stage.status != "Skipped"]
    if not effective_stages:
        return 100

    completed_stages = [
        stage for stage in effective_stages if stage.status == "Completed"
    ]
    if len(completed_stages) == len(effective_stages):
        return 100

    return (len(completed_stages) * 100) // len(effective_stages)


def calculate_progress_excluding_skipped(stages) -> int:
    return calculate_rfq_lifecycle_progress(stages)


def apply_terminal_stage_freeze(session: Session, rfq, update_data: dict[str, Any]) -> None:
    stages = (
        session.query(RFQStage)
        .filter_by(rfq_id=rfq.id)
        .order_by(RFQStage.order.asc())
        .all()
    )

    current_stage_order = 0
    for stage in stages:
        if stage.id == rfq.current_stage_id:
            current_stage_order = stage.order
            if stage.status == "In Progress":
                stage.status = "Skipped"
                stage.actual_end = date.today()
            elif stage.status == "Not Started":
                stage.status = "Skipped"
            break

    for stage in stages:
        if stage.order > current_stage_order and stage.status != "Completed":
            stage.status = "Skipped"

    update_data["current_stage_id"] = None
    update_data["progress"] = calculate_rfq_lifecycle_progress(
        stages,
        update_data.get("status"),
    )

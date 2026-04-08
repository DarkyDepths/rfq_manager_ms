from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from src.models.rfq_stage import RFQStage
from src.utils.errors import ConflictError
from src.utils.rfq_status import RFQ_VALID_STATUS_TRANSITIONS


def validate_rfq_status_transition(current_status: str, new_status: str) -> None:
    if new_status == current_status:
        return

    allowed_next = RFQ_VALID_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed_next:
        raise ConflictError(
            f"Invalid RFQ status transition from '{current_status}' to '{new_status}'."
        )


def calculate_progress_excluding_skipped(stages) -> int:
    non_skipped = [stage for stage in stages if stage.status != "Skipped"]
    if not non_skipped:
        return 100

    if all(stage.status == "Completed" for stage in non_skipped):
        return 100

    total_progress = sum(stage.progress for stage in non_skipped)
    return total_progress // len(non_skipped)


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
    update_data["progress"] = calculate_progress_excluding_skipped(stages)

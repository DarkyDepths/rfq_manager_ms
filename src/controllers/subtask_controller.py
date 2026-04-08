"""
Subtask controller — business logic for the Subtask resource.

Orchestrates:
- Create subtask (auto-set progress=0, status=Open)
- List active subtasks (WHERE deleted_at IS NULL)
- Update subtask (progress, status changes)
- Soft-delete subtask
- Auto-update parent stage progress from active subtasks

Dependencies: SubtaskDatasource, RfqStageDatasource
"""

from datetime import date
from sqlalchemy.orm import Session

from src.datasources.subtask_datasource import SubtaskDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.translators import subtask_translator
from src.utils.errors import ConflictError, NotFoundError, UnprocessableEntityError


SUBTASK_DUE_DATE_WINDOW_MESSAGE = (
    "Subtask due date must fall within the current stage window."
)
SUBTASK_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE = (
    "Subtask due date cannot be set because the current stage schedule is incomplete."
)
SUBTASK_PROGRESS_DECREASE_MESSAGE = (
    "Subtask progress cannot move backward once saved."
)
SUBTASK_STATUS_OPEN = "Open"
SUBTASK_STATUS_IN_PROGRESS = "In progress"
SUBTASK_STATUS_DONE = "Done"


class SubtaskController:

    def __init__(self, datasource: SubtaskDatasource, stage_datasource: RfqStageDatasource, session: Session):
        self.ds = datasource
        self.stage_ds = stage_datasource
        self.session = session

    def create(self, rfq_id, stage_id, request: subtask_translator.SubtaskCreateRequest):
        # Verify stage exists
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id:
            raise NotFoundError(f"Stage '{stage_id}' not found in RFQ '{rfq_id}'")

        data = request.model_dump()
        self._validate_due_date(stage, data.get("due_date"))
        data["rfq_stage_id"] = stage_id

        subtask = self.ds.create(data)
        self._update_stage_progress(stage_id)
        self.session.commit()
        return subtask_translator.to_response(subtask)

    def list(self, rfq_id, stage_id) -> dict:
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id:
            raise NotFoundError(f"Stage '{stage_id}' not found in RFQ '{rfq_id}'")

        subtasks = self.ds.list_by_stage(stage_id)
        return {"data": [subtask_translator.to_response(s) for s in subtasks]}

    def update(self, rfq_id, stage_id, subtask_id, request: subtask_translator.SubtaskUpdateRequest):
        subtask = self._get_or_404(rfq_id, stage_id, subtask_id)
        update_data = request.model_dump(exclude_unset=True)
        stage = self.stage_ds.get_by_id(stage_id)

        if "due_date" in update_data:
            self._validate_due_date(stage, update_data.get("due_date"))

        update_data = self._normalize_subtask_update(subtask, update_data)

        subtask = self.ds.update(subtask, update_data)

        # Rollup: recalculate parent stage progress
        self._update_stage_progress(stage_id)

        self.session.commit()
        return subtask_translator.to_response(subtask)

    def delete(self, rfq_id, stage_id, subtask_id):
        subtask = self._get_or_404(rfq_id, stage_id, subtask_id)
        self.ds.soft_delete(subtask)

        # Recalculate after removing a subtask from the count
        self._update_stage_progress(stage_id)

        self.session.commit()

    def _get_or_404(self, rfq_id, stage_id, subtask_id):
        subtask = self.ds.get_by_id(subtask_id)
        if not subtask:
            raise NotFoundError(f"Subtask '{subtask_id}' not found")
        # Verify the chain: subtask belongs to stage, stage belongs to rfq
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id or subtask.rfq_stage_id != stage_id:
            raise NotFoundError(f"Subtask '{subtask_id}' not found in stage '{stage_id}'")
        return subtask

    def _derive_status_from_progress(self, progress: int) -> str:
        if progress <= 0:
            return SUBTASK_STATUS_OPEN
        if progress >= 100:
            return SUBTASK_STATUS_DONE
        return SUBTASK_STATUS_IN_PROGRESS

    def _update_stage_progress(self, stage_id):
        """Recalculate parent stage progress from average of active subtask progresses."""
        subtasks = self.ds.list_by_stage(stage_id)
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage:
            return
        if not subtasks:
            stage.progress = 0  # no active subtasks → reset
        else:
            stage.progress = sum(s.progress for s in subtasks) // len(subtasks)
        self.session.flush()

    def _validate_due_date(self, stage, due_date: date | None):
        if due_date is None:
            return

        window_start, window_end = self._resolve_due_date_window(stage)

        if window_start is None or window_end is None:
            raise UnprocessableEntityError(SUBTASK_DUE_DATE_SCHEDULE_INCOMPLETE_MESSAGE)

        if due_date < window_start or due_date > window_end:
            raise UnprocessableEntityError(SUBTASK_DUE_DATE_WINDOW_MESSAGE)

    @staticmethod
    def _resolve_due_date_window(stage) -> tuple[date | None, date | None]:
        if not stage:
            return None, None

        planned_start = getattr(stage, "planned_start", None)
        planned_end = getattr(stage, "planned_end", None)
        actual_start = getattr(stage, "actual_start", None)
        actual_end = getattr(stage, "actual_end", None)

        if actual_start and actual_end:
            return actual_start, actual_end

        if actual_start:
            if planned_start is None or planned_end is None:
                return None, None

            planned_duration_days = max((planned_end - planned_start).days, 0)
            shifted_end = date.fromordinal(actual_start.toordinal() + planned_duration_days)
            return actual_start, shifted_end if shifted_end > planned_end else planned_end

        if planned_start is None or planned_end is None:
            return None, None

        return planned_start, planned_end

    def _normalize_subtask_update(self, subtask, update_data: dict):
        if "progress" in update_data and update_data["progress"] is None:
            update_data.pop("progress")

        if "status" in update_data and update_data["status"] is None:
            update_data.pop("status")

        merged_progress = subtask.progress
        if "progress" in update_data:
            merged_progress = update_data["progress"]

        if merged_progress < subtask.progress:
            raise ConflictError(SUBTASK_PROGRESS_DECREASE_MESSAGE)

        merged_status = self._derive_status_from_progress(merged_progress)

        normalized = dict(update_data)

        if merged_progress != subtask.progress or "progress" in update_data:
            normalized["progress"] = merged_progress

        if merged_status != subtask.status or "status" in update_data or "progress" in update_data:
            normalized["status"] = merged_status

        return normalized

"""
Subtask controller — business logic for the Subtask resource.

Orchestrates:
- Create subtask (auto-set progress=0, status=Open)
- List active subtasks (WHERE deleted_at IS NULL)
- Update subtask (progress, status changes)
- Soft-delete subtask
- Auto-update parent stage progress when all subtasks reach 100%

Dependencies: SubtaskDatasource, RfqStageDatasource
"""

from sqlalchemy.orm import Session

from src.datasources.subtask_datasource import SubtaskDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.translators import subtask_translator
from src.utils.errors import NotFoundError


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
        data["rfq_stage_id"] = stage_id

        subtask = self.ds.create(data)
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

    def _update_stage_progress(self, stage_id):
        """Recalculate parent stage progress from average of active subtask progresses."""
        subtasks = self.ds.list_by_stage(stage_id)
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage:
            return
        if not subtasks:
            stage.progress = 0  # no active subtasks → reset
        else:
            avg = sum(s.progress for s in subtasks) // len(subtasks)
            if avg == 100 and stage.status != "Completed":
                avg = 99
            stage.progress = avg
        self.session.flush()

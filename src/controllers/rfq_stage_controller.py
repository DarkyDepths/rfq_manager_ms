"""
RFQ Stage controller — business logic for the RFQ_Stage resource.

Orchestrates:
- List / get stages for an RFQ
- Update stage (progress, captured_data, blocker management)
- Add notes and upload files to a stage
- Stage advancement with blocker/mandatory field validation
- File upload with size limit

Dependencies: RfqStageDatasource, RfqDatasource
"""

import os
from pathlib import Path
import uuid
from datetime import date

from sqlalchemy.orm import Session

from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.datasources.rfq_datasource import RfqDatasource
from src.translators import rfq_stage_translator
from src.models.rfq_stage import RFQStage
from src.models.subtask import Subtask
from src.utils.errors import NotFoundError, ConflictError, UnprocessableEntityError, BadRequestError
from src.config.settings import settings


class RfqStageController:

    def __init__(
        self,
        stage_datasource: RfqStageDatasource,
        rfq_datasource: RfqDatasource,
        session: Session,
    ):
        self.stage_ds = stage_datasource
        self.rfq_ds = rfq_datasource
        self.session = session

    # ══════════════════════════════════════════════════
    # #10 — LIST STAGES
    # ══════════════════════════════════════════════════
    def list(self, rfq_id) -> dict:
        rfq = self.rfq_ds.get_by_id(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{rfq_id}' not found")

        stages = self.stage_ds.list_by_rfq(rfq_id)
        return {"data": [rfq_stage_translator.to_response(s) for s in stages]}

    # ══════════════════════════════════════════════════
    # #11 — GET STAGE DETAIL
    # ══════════════════════════════════════════════════
    def get(self, rfq_id, stage_id) -> rfq_stage_translator.RfqStageDetailResponse:
        stage = self._get_stage_or_404(rfq_id, stage_id)
        return self._load_detail(stage)

    # ══════════════════════════════════════════════════
    # #12 — UPDATE STAGE
    # ══════════════════════════════════════════════════
    def update(self, rfq_id, stage_id, request: rfq_stage_translator.RfqStageUpdateRequest):
        stage = self._get_stage_or_404(rfq_id, stage_id)
        update_data = request.model_dump(exclude_unset=True)

        # PR4: Enforce subtask ownership of stage progress
        if "progress" in update_data:
            has_subtasks = (
                self.session.query(Subtask)
                .filter(Subtask.rfq_stage_id == stage.id, Subtask.deleted_at.is_(None))
                .count() > 0
            )
            if has_subtasks:
                raise ConflictError("Cannot manually update progress when active subtasks exist. Progress is determined by subtask rollup.")

        stage = self.stage_ds.update(stage, update_data)
        self.session.commit()
        self.session.refresh(stage)
        return self._load_detail(stage)

    # ══════════════════════════════════════════════════
    # #13 — ADD NOTE (append-only)
    # ══════════════════════════════════════════════════
    def add_note(self, rfq_id, stage_id, request: rfq_stage_translator.NoteCreateRequest, user_name: str = "System"):
        self._get_stage_or_404(rfq_id, stage_id)

        note = self.stage_ds.add_note({
            "rfq_stage_id": stage_id,
            "user_name": user_name,
            "text": request.text,
        })
        self.session.commit()
        return rfq_stage_translator.StageNoteResponse.model_validate(note)

    # ══════════════════════════════════════════════════
    # #14 — UPLOAD FILE
    # ══════════════════════════════════════════════════
    def upload_file(self, rfq_id, stage_id, filename: str, file_type: str, file_content: bytes, uploaded_by: str = "System"):
        self._get_stage_or_404(rfq_id, stage_id)

        # Size limit check
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(file_content) > max_bytes:
            raise BadRequestError(f"File too large. Max allowed is {settings.MAX_FILE_SIZE_MB} MB.")

        # Save file to disk
        # Save file to disk using pathlib
        upload_dir = Path(settings.FILE_STORAGE_PATH) / str(rfq_id) / str(stage_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid.uuid4()
        safe_filename = f"{file_id}_{filename}"
        
        # Absolute path for OS writing
        absolute_path = upload_dir / safe_filename
        
        # Relative POSIX path for database storage (no hardcoded "uploads")
        relative_posix_path = (Path(str(rfq_id)) / str(stage_id) / safe_filename).as_posix()

        with open(absolute_path, "wb") as f:
            f.write(file_content)

        file_record = self.stage_ds.add_file({
            "id": file_id,
            "rfq_stage_id": stage_id,
            "filename": filename,
            "file_path": relative_posix_path,
            "type": file_type,
            "uploaded_by": uploaded_by,
            "size_bytes": len(file_content),
        })
        self.session.commit()
        return rfq_stage_translator.StageFileResponse.model_validate(file_record)

    # ══════════════════════════════════════════════════
    # #15 — ADVANCE TO NEXT STAGE
    # ══════════════════════════════════════════════════
    def advance(self, rfq_id, stage_id):
        """
        The core workflow engine:
        1. Validate stage exists and belongs to this RFQ
        2. Check blockers (409 if blocked)
        3. Check mandatory fields (422 if missing)
        4. Mark current stage as Completed
        5. Mark next stage as In Progress
        6. Update RFQ.current_stage_id + progress
        7. Commit
        """
        stage = self._get_stage_or_404(rfq_id, stage_id)
        rfq = self.rfq_ds.get_by_id(rfq_id)

        # Step 1.5 — Validate stage is the current active stage
        if str(stage.id) != str(rfq.current_stage_id):
            raise ConflictError(f"Only the current active stage can be advanced. (Requested: {stage.id}, Current: {rfq.current_stage_id})")

        # Step 2 — Check blockers
        self._check_blockers(stage)

        # Step 3 — Check mandatory fields
        self._validate_mandatory_fields(stage)

        # Step 4 — Complete current stage
        stage.status = "Completed"
        stage.progress = 100
        stage.actual_end = date.today()
        self.session.flush()

        # Step 5 — Start next stage (if exists)
        next_stage = self.stage_ds.get_next_stage(rfq_id, stage.order)
        if next_stage:
            next_stage.status = "In Progress"
            next_stage.actual_start = date.today()
            rfq.current_stage_id = next_stage.id
            self.session.flush()
        else:
            # Last stage completed — keep RFQ status explicit (no hardcoded auto-transition)
            rfq.progress = 100
            self.session.flush()

        # Step 6 — Recalculate RFQ progress (skip if already set to 100)
        if next_stage:
            self._update_rfq_progress(rfq)

        # Step 7 — Commit
        self.session.commit()
        self.session.refresh(stage)

        return self._load_detail(stage)

    # ══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════

    def _load_detail(self, stage) -> rfq_stage_translator.RfqStageDetailResponse:
        """Load stage with all children for a complete detail response."""
        notes = self.stage_ds.get_notes(stage.id)
        files = self.stage_ds.list_files(stage.id)
        subtasks = (
            self.session.query(Subtask)
            .filter(Subtask.rfq_stage_id == stage.id, Subtask.deleted_at.is_(None))
            .order_by(Subtask.created_at)
            .all()
        )
        return rfq_stage_translator.to_detail(stage, notes=notes, files=files, subtasks=subtasks)

    def _get_stage_or_404(self, rfq_id, stage_id) -> RFQStage:
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id:
            raise NotFoundError(f"Stage '{stage_id}' not found in RFQ '{rfq_id}'")
        return stage

    def _check_blockers(self, stage: RFQStage):
        """409 if stage is currently blocked."""
        if stage.blocker_status == "Blocked":
            raise ConflictError(
                f"Stage '{stage.name}' is blocked ({stage.blocker_reason_code}). "
                "Resolve the blocker before advancing."
            )

    def _validate_mandatory_fields(self, stage: RFQStage):
        """422 if mandatory fields are missing from captured_data."""
        if not stage.mandatory_fields:
            return

        required = [f.strip() for f in stage.mandatory_fields.split(",") if f.strip()]
        captured = stage.captured_data or {}
        missing = [f for f in required if f not in captured or captured[f] is None]

        if missing:
            raise UnprocessableEntityError(
                f"Missing mandatory fields for stage '{stage.name}': {', '.join(missing)}"
            )

    def _update_rfq_progress(self, rfq):
        """Recalculate RFQ progress from non-skipped stages only."""
        stages = self.stage_ds.list_by_rfq(rfq.id)
        if not stages:
            return

        non_skipped = [stage for stage in stages if stage.status != "Skipped"]
        if not non_skipped:
            rfq.progress = 100
            self.session.flush()
            return

        if all(stage.status == "Completed" for stage in non_skipped):
            rfq.progress = 100
        else:
            total_progress = sum(stage.progress for stage in non_skipped)
            rfq.progress = total_progress // len(non_skipped)

        self.session.flush()

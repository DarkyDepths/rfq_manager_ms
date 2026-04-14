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

from pathlib import Path
import uuid
from datetime import date, datetime, timezone
import logging
from typing import Any, List, Sequence

from sqlalchemy.orm import Session

from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.datasources.rfq_datasource import RfqDatasource
from src.connectors.event_bus import EventBusConnector
from src.translators import rfq_stage_translator
from src.models.rfq_stage import RFQStage
from src.models.subtask import Subtask
from src.utils.errors import NotFoundError, ConflictError, UnprocessableEntityError, BadRequestError, ForbiddenError
from src.utils.rfq_lifecycle import (
    apply_terminal_stage_freeze,
    calculate_rfq_lifecycle_progress,
    validate_rfq_status_transition,
)
from src.utils.rfq_status import (
    RFQ_STATUS_AWARDED,
    RFQ_STATUS_CANCELLED,
    RFQ_STATUS_LOST,
)
from src.config.settings import settings
from src.utils.file_storage import (
    ensure_storage_containment,
    get_storage_root,
    sanitize_uploaded_filename,
)
from src.utils.observability import get_request_id


logger = logging.getLogger(__name__)

INCOMPLETE_SUBTASKS_ADVANCE_MESSAGE = (
    "All active subtasks must be completed before advancing this stage."
)


class RfqStageController:

    def __init__(
        self,
        stage_datasource: RfqStageDatasource,
        rfq_datasource: RfqDatasource,
        session: Session,
        event_bus_connector: EventBusConnector | None = None,
    ):
        self.stage_ds = stage_datasource
        self.rfq_ds = rfq_datasource
        self.session = session
        self.event_bus = event_bus_connector

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
    def update(
        self,
        rfq_id,
        stage_id,
        request: rfq_stage_translator.RfqStageUpdateRequest,
        *,
        actor_name: str | None = None,
    ):
        stage = self._get_stage_or_404(rfq_id, stage_id)
        update_data = request.model_dump(exclude_unset=True, exclude_none=True)
        if "blocker_status" in request.model_fields_set and request.blocker_status is None:
            update_data["blocker_status"] = None
        update_data = self._normalize_stage_update(stage, update_data)
        update_data = self._record_stage_history_events(
            stage,
            update_data,
            actor_name=actor_name,
        )

        stage = self.stage_ds.update(stage, update_data)
        self.session.commit()
        self.session.refresh(stage)
        return self._load_detail(stage)

    # ══════════════════════════════════════════════════
    # #13 — ADD NOTE (append-only)
    # ══════════════════════════════════════════════════
    def add_note(self, rfq_id, stage_id, request: rfq_stage_translator.NoteCreateRequest, user_name: str):
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
    def upload_file(self, rfq_id, stage_id, filename: str, file_type: str, file_content: bytes, uploaded_by: str):
        self._get_stage_or_404(rfq_id, stage_id)

        # Size limit check
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(file_content) > max_bytes:
            raise BadRequestError(f"File too large. Max allowed is {settings.MAX_FILE_SIZE_MB} MB.")

        # Save file to disk
        # Save file to disk using pathlib
        upload_dir = ensure_storage_containment(
            get_storage_root() / str(rfq_id) / str(stage_id)
        )
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid.uuid4()
        sanitized_filename = sanitize_uploaded_filename(filename)
        safe_filename = f"{file_id}_{sanitized_filename}"
        
        # Absolute path for OS writing
        absolute_path = ensure_storage_containment(upload_dir / safe_filename)
        
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
        return rfq_stage_translator.file_to_schema(file_record)

    # ══════════════════════════════════════════════════
    # #15 — ADVANCE TO NEXT STAGE
    # ══════════════════════════════════════════════════
    def advance(
        self,
        rfq_id,
        stage_id,
        actor_team: str,
        request: rfq_stage_translator.RfqStageAdvanceRequest | None = None,
        actor_user_id: str | None = None,
        actor_name: str | None = None,
        actor_permissions: Sequence[str] | None = None,
    ):
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
        request = request or rfq_stage_translator.RfqStageAdvanceRequest()
        previous_stage_status = stage.status
        previous_rfq_status = rfq.status

        self._validate_stage_team_access(
            stage,
            actor_team,
            actor_permissions=actor_permissions,
        )

        # Step 1.5 — Validate stage is the current active stage
        if str(stage.id) != str(rfq.current_stage_id):
            raise ConflictError(f"Only the current active stage can be advanced. (Requested: {stage.id}, Current: {rfq.current_stage_id})")

        # Step 2 — Check blockers
        self._check_blockers(stage)

        # Step 3 — Check mandatory fields
        self._validate_mandatory_fields(stage)
        self._check_incomplete_subtasks(stage)
        no_go_result = self._handle_no_go_cancellation(
            stage,
            rfq,
            request,
            actor_team=actor_team,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            previous_rfq_status=previous_rfq_status,
        )
        if no_go_result is not None:
            return no_go_result

        next_stage = self.stage_ds.get_next_stage(rfq_id, stage.order)
        terminal_outcome_result = self._handle_terminal_outcome_completion(
            stage,
            rfq,
            next_stage,
            request,
            actor_team=actor_team,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            previous_stage_status=previous_stage_status,
            previous_rfq_status=previous_rfq_status,
        )
        if terminal_outcome_result is not None:
            return terminal_outcome_result

        # Step 4 — Complete current stage
        stage.status = "Completed"
        stage.progress = 100
        stage.actual_end = date.today()
        self.session.flush()

        # Step 5 — Start next stage (if exists)
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

        payload: dict[str, Any] = {
            "rfq_id": str(rfq.id),
            "stage_id": str(stage.id),
            "stage_name": stage.name,
            "previous_stage_status": previous_stage_status,
            "new_stage_status": stage.status,
            "advanced_at": self._utc_now_iso(),
            "assigned_team": stage.assigned_team,
        }
        if getattr(rfq, "rfq_code", None):
            payload["rfq_code"] = rfq.rfq_code
        if previous_rfq_status != rfq.status:
            payload["previous_rfq_status"] = previous_rfq_status
            payload["new_rfq_status"] = rfq.status

        self._publish_event_best_effort(
            "stage.advanced",
            payload=payload,
            metadata=self._build_event_metadata(
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_team=actor_team,
            ),
        )

        return self._load_detail(stage)

    def _validate_stage_team_access(
        self,
        stage: RFQStage,
        actor_team: str,
        *,
        actor_permissions: Sequence[str] | None = None,
    ):
        stage_team = (stage.assigned_team or "").strip().lower()
        user_team = (actor_team or "").strip().lower()

        if not stage_team:
            raise ForbiddenError("Stage advance denied: stage has no assigned team")

        if user_team and user_team == stage_team:
            return

        if self._has_cross_team_advance_override(actor_permissions):
            return

        if not user_team or user_team != stage_team:
            raise ForbiddenError(
                f"Stage advance denied: actor team '{actor_team or 'unknown'}' does not match assigned team '{stage.assigned_team}'"
            )

    @staticmethod
    def _has_cross_team_advance_override(actor_permissions: Sequence[str] | None) -> bool:
        permissions = {
            permission.strip()
            for permission in (actor_permissions or [])
            if permission and permission.strip()
        }
        return (
            "*" in permissions
            or "rfq_stage:advance" in permissions
            or "rfq_stage:*" in permissions
        )

    # ══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════

    def _load_detail(self, stage) -> rfq_stage_translator.RfqStageDetailResponse:
        """Load stage with all children for a complete detail response."""
        notes = self.stage_ds.get_notes(stage.id)
        files = self.stage_ds.list_files(stage.id)
        subtasks = self._list_active_subtasks(stage.id)
        return rfq_stage_translator.to_detail(stage, notes=notes, files=files, subtasks=subtasks)

    def _get_stage_or_404(self, rfq_id, stage_id) -> RFQStage:
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id:
            raise NotFoundError(f"Stage '{stage_id}' not found in RFQ '{rfq_id}'")
        return stage

    def _check_blockers(self, stage: RFQStage):
        """409 if stage is currently blocked."""
        if stage.blocker_status == "Blocked":
            if stage.blocker_reason_code:
                reason_fragment = f" ({stage.blocker_reason_code})"
            else:
                reason_fragment = ""
            raise ConflictError(
                f"Stage '{stage.name}' is blocked{reason_fragment}. "
                "Resolve the blocker before advancing."
            )

    def _check_incomplete_subtasks(self, stage: RFQStage):
        subtasks = self._list_active_subtasks(stage.id)
        if any(subtask.progress < 100 or subtask.status != "Done" for subtask in subtasks):
            raise ConflictError(INCOMPLETE_SUBTASKS_ADVANCE_MESSAGE)

    def _normalize_stage_update(self, stage: RFQStage, update_data: dict[str, Any]) -> dict[str, Any]:
        next_update = dict(update_data)

        if "blocker_status" in next_update and next_update["blocker_status"] is None:
            next_update["blocker_reason_code"] = None

        captured_data = dict(stage.captured_data or {})
        if isinstance(next_update.get("captured_data"), dict):
            captured_data.update(next_update["captured_data"])
            captured_data = rfq_stage_translator.normalize_stage_captured_data(captured_data)
            next_update["captured_data"] = captured_data

        negative_decision_field = rfq_stage_translator.find_negative_blocking_decision(
            stage.mandatory_fields,
            captured_data,
        )
        auto_blocker_source = rfq_stage_translator.get_auto_blocker_source_field(captured_data)

        existing_reason = (
            stage.blocker_reason_code.strip()
            if isinstance(stage.blocker_reason_code, str) and stage.blocker_reason_code.strip()
            else None
        )
        incoming_reason = next_update.get("blocker_reason_code")
        effective_reason = (
            incoming_reason.strip()
            if isinstance(incoming_reason, str) and incoming_reason.strip()
            else existing_reason
        )

        if negative_decision_field:
            if not effective_reason:
                raise UnprocessableEntityError(
                    rfq_stage_translator.get_negative_decision_blocker_reason_message(
                        negative_decision_field
                    )
                )

            next_update["blocker_status"] = "Blocked"
            next_update["blocker_reason_code"] = effective_reason
            captured_data[rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD] = negative_decision_field
        elif (
            auto_blocker_source
            and stage.blocker_status == "Blocked"
            and self._get_captured_stage_decision(captured_data, auto_blocker_source)
            == rfq_stage_translator.YES_NO_VALUE_YES
            and next_update.get("blocker_status") != "Blocked"
        ):
            next_update["blocker_status"] = "Resolved"
            next_update["blocker_reason_code"] = None
            captured_data.pop(rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD, None)

        resulting_blocker_status = next_update.get("blocker_status", stage.blocker_status)
        if resulting_blocker_status != "Blocked":
            captured_data.pop(rfq_stage_translator.AUTO_BLOCKER_SOURCE_FIELD, None)

        if "captured_data" in next_update:
            next_update["captured_data"] = captured_data

        return next_update

    def _record_stage_history_events(
        self,
        stage: RFQStage,
        update_data: dict[str, Any],
        *,
        actor_name: str | None = None,
    ) -> dict[str, Any]:
        next_update = dict(update_data)
        previous_captured = dict(stage.captured_data or {})
        next_captured = dict(next_update.get("captured_data") or previous_captured)
        existing_events = rfq_stage_translator.get_lifecycle_history_events_from_captured_data(
            previous_captured
        )
        next_events = list(existing_events)

        self._append_decision_history_events(
            previous_captured,
            next_captured,
            next_events,
            actor_name=actor_name,
        )
        self._append_blocker_history_events(
            stage,
            next_update,
            previous_captured,
            next_captured,
            next_events,
            actor_name=actor_name,
        )

        if next_events != existing_events or "captured_data" in next_update:
            if next_events:
                next_captured[rfq_stage_translator.LIFECYCLE_HISTORY_EVENTS_FIELD] = next_events[-100:]
            next_update["captured_data"] = next_captured

        return next_update

    def _append_decision_history_events(
        self,
        previous_captured: dict[str, Any],
        next_captured: dict[str, Any],
        events: List[dict[str, Any]],
        *,
        actor_name: str | None = None,
    ) -> None:
        for field_key in rfq_stage_translator.TRACKED_STAGE_HISTORY_FIELDS:
            previous_value = rfq_stage_translator.get_tracked_stage_history_field_value(
                previous_captured, field_key
            )
            next_value = rfq_stage_translator.get_tracked_stage_history_field_value(
                next_captured, field_key
            )
            if previous_value == next_value or next_value in {None, ""}:
                continue

            event_type = (
                "terminal_outcome_recorded"
                if field_key == rfq_stage_translator.TERMINAL_OUTCOME_FIELD
                else "decision_recorded"
            )
            event = rfq_stage_translator.build_stage_history_event(
                event_type,
                actor_name=actor_name,
                field_key=field_key,
                value=next_value,
            )

            if (
                field_key == rfq_stage_translator.LOST_REASON_CODE_FIELD
                and next_value == "other"
            ):
                other_detail = rfq_stage_translator.get_lost_reason_other_detail_from_captured_data(
                    next_captured
                )
                if other_detail:
                    event["detail"] = other_detail

            events.append(event)

    def _append_blocker_history_events(
        self,
        stage: RFQStage,
        update_data: dict[str, Any],
        previous_captured: dict[str, Any],
        next_captured: dict[str, Any],
        events: List[dict[str, Any]],
        *,
        actor_name: str | None = None,
    ) -> None:
        previous_status = rfq_stage_translator.normalize_stage_history_blocker_status(stage.blocker_status)
        next_status = rfq_stage_translator.normalize_stage_history_blocker_status(
            update_data.get("blocker_status", stage.blocker_status)
        )
        previous_reason = rfq_stage_translator.normalize_stage_history_text_value(stage.blocker_reason_code)
        next_reason = rfq_stage_translator.normalize_stage_history_text_value(
            update_data.get("blocker_reason_code", stage.blocker_reason_code)
        )
        blocker_source = (
            rfq_stage_translator.get_auto_blocker_source_field(next_captured)
            or rfq_stage_translator.get_auto_blocker_source_field(previous_captured)
        )
        source = "automatic" if blocker_source else "manual"

        if next_status == "Blocked":
            if previous_status != "Blocked":
                events.append(
                    rfq_stage_translator.build_stage_history_event(
                        "blocker_created",
                        actor_name=actor_name,
                        field_key=blocker_source,
                        reason=next_reason,
                        source=source,
                    )
                )
            elif next_reason and next_reason != previous_reason:
                events.append(
                    rfq_stage_translator.build_stage_history_event(
                        "blocker_updated",
                        actor_name=actor_name,
                        field_key=blocker_source,
                        reason=next_reason,
                        source=source,
                    )
                )
            return

        if previous_status == "Blocked" and next_status != "Blocked":
            events.append(
                rfq_stage_translator.build_stage_history_event(
                    "blocker_resolved",
                    actor_name=actor_name,
                    field_key=blocker_source,
                    reason=previous_reason,
                    source=source,
                )
            )

    def _validate_mandatory_fields(self, stage: RFQStage):
        """422 if mandatory fields are missing from captured_data."""
        if not stage.mandatory_fields:
            return

        required = [f.strip() for f in stage.mandatory_fields.split(",") if f.strip()]
        captured = stage.captured_data or {}
        missing = []

        for field in required:
            if (
                field == rfq_stage_translator.GO_NO_GO_DECISION_FIELD
                or rfq_stage_translator.is_controlled_yes_no_decision_field(field)
            ):
                decision = self._get_controlled_stage_decision(stage, field)
                if decision is None:
                    missing.append(field)
                continue

            if rfq_stage_translator.is_commercial_stage_field(field):
                if rfq_stage_translator.get_commercial_amount_value(captured, field) is None:
                    missing.append(field)
                continue

            if field == rfq_stage_translator.APPROVAL_SIGNATURE_FIELD:
                try:
                    signature = rfq_stage_translator.normalize_approval_signature_value(
                        captured.get(field)
                    )
                except ValueError as exc:
                    raise UnprocessableEntityError(str(exc)) from exc

                if signature is None:
                    missing.append(field)
                continue

            if (
                field not in captured
                or captured[field] is None
                or (isinstance(captured[field], str) and not captured[field].strip())
            ):
                missing.append(field)

        if missing:
            if len(missing) == 1:
                field_message = rfq_stage_translator.get_stage_field_validation_message(
                    missing[0]
                )
                if field_message:
                    raise UnprocessableEntityError(field_message)
            raise UnprocessableEntityError(
                f"Missing mandatory fields for stage '{stage.name}': {', '.join(missing)}"
            )

    def _handle_no_go_cancellation(
        self,
        stage: RFQStage,
        rfq,
        request: rfq_stage_translator.RfqStageAdvanceRequest,
        *,
        actor_team: str,
        actor_user_id: str | None,
        actor_name: str | None,
        previous_rfq_status: str,
    ):
        decision = self._get_go_no_go_decision(stage)
        if decision != rfq_stage_translator.GO_NO_GO_VALUE_NO_GO:
            return None

        if not request.confirm_no_go_cancel:
            raise ConflictError(rfq_stage_translator.GO_NO_GO_CONFIRM_CANCEL_MESSAGE)

        if not request.outcome_reason:
            raise UnprocessableEntityError(
                rfq_stage_translator.GO_NO_GO_REASON_REQUIRED_MESSAGE
            )

        validate_rfq_status_transition(previous_rfq_status, RFQ_STATUS_CANCELLED)

        update_data = {
            "status": RFQ_STATUS_CANCELLED,
            "outcome_reason": request.outcome_reason,
        }
        apply_terminal_stage_freeze(self.session, rfq, update_data)
        rfq = self.rfq_ds.update(rfq, update_data)
        self.session.commit()
        self.session.refresh(rfq)
        self.session.refresh(stage)

        self._publish_event_best_effort(
            "rfq.status_changed",
            payload={
                "rfq_id": str(rfq.id),
                "rfq_code": getattr(rfq, "rfq_code", None),
                "previous_status": previous_rfq_status,
                "new_status": rfq.status,
                "changed_at": self._utc_now_iso(),
            },
            metadata=self._build_event_metadata(
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_team=actor_team,
            ),
        )

        return self._load_detail(stage)

    def _handle_terminal_outcome_completion(
        self,
        stage: RFQStage,
        rfq,
        next_stage: RFQStage | None,
        request: rfq_stage_translator.RfqStageAdvanceRequest,
        *,
        actor_team: str,
        actor_user_id: str | None,
        actor_name: str | None,
        previous_stage_status: str,
        previous_rfq_status: str,
    ):
        if next_stage is not None:
            return None

        outcome = request.terminal_outcome or rfq_stage_translator.get_terminal_outcome_from_captured_data(
            stage.captured_data
        )
        if outcome is None:
            raise UnprocessableEntityError(
                rfq_stage_translator.TERMINAL_OUTCOME_VALIDATION_MESSAGE
            )

        lost_reason_code = request.lost_reason_code or rfq_stage_translator.get_lost_reason_code_from_captured_data(
            stage.captured_data
        )
        if outcome == rfq_stage_translator.TERMINAL_OUTCOME_LOST and not lost_reason_code:
            raise UnprocessableEntityError(
                rfq_stage_translator.LOST_REASON_REQUIRED_MESSAGE
            )
        lost_reason_other_detail = rfq_stage_translator.get_lost_reason_other_detail_from_captured_data(
            stage.captured_data
        )
        if (
            outcome == rfq_stage_translator.TERMINAL_OUTCOME_LOST
            and lost_reason_code == "other"
            and not lost_reason_other_detail
        ):
            raise UnprocessableEntityError(
                rfq_stage_translator.LOST_REASON_OTHER_REQUIRED_MESSAGE
            )

        terminal_status = (
            RFQ_STATUS_AWARDED
            if outcome == rfq_stage_translator.TERMINAL_OUTCOME_AWARDED
            else RFQ_STATUS_LOST
        )
        self._validate_terminal_outcome_transition(previous_rfq_status, terminal_status)

        updated_captured_data = rfq_stage_translator.normalize_stage_captured_data(
            {
                **(stage.captured_data or {}),
                rfq_stage_translator.TERMINAL_OUTCOME_FIELD: outcome,
                rfq_stage_translator.LOST_REASON_CODE_FIELD: lost_reason_code,
            }
        )
        lifecycle_events = rfq_stage_translator.get_lifecycle_history_events_from_captured_data(
            stage.captured_data
        )
        terminal_reason = rfq_stage_translator.build_terminal_outcome_reason(
            outcome,
            lost_reason_code=lost_reason_code,
            lost_reason_other_detail=lost_reason_other_detail,
            outcome_detail=request.outcome_reason,
        )
        rfq_stage_translator.append_terminal_outcome_history_event(
            lifecycle_events,
            actor_name=actor_name,
            value=outcome,
            reason=terminal_reason,
        )
        updated_captured_data[rfq_stage_translator.LIFECYCLE_HISTORY_EVENTS_FIELD] = lifecycle_events[-100:]
        stage.captured_data = updated_captured_data
        stage.status = "Completed"
        stage.progress = 100
        stage.actual_end = date.today()

        rfq.status = terminal_status
        rfq.current_stage_id = None
        rfq.progress = 100
        rfq.outcome_reason = terminal_reason

        self.session.commit()
        self.session.refresh(stage)
        self.session.refresh(rfq)

        self._publish_event_best_effort(
            "rfq.status_changed",
            payload={
                "rfq_id": str(rfq.id),
                "rfq_code": getattr(rfq, "rfq_code", None),
                "previous_status": previous_rfq_status,
                "new_status": rfq.status,
                "changed_at": self._utc_now_iso(),
            },
            metadata=self._build_event_metadata(
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_team=actor_team,
            ),
        )

        stage_event_payload: dict[str, Any] = {
            "rfq_id": str(rfq.id),
            "stage_id": str(stage.id),
            "stage_name": stage.name,
            "previous_stage_status": previous_stage_status,
            "new_stage_status": stage.status,
            "advanced_at": self._utc_now_iso(),
            "assigned_team": stage.assigned_team,
        }
        if getattr(rfq, "rfq_code", None):
            stage_event_payload["rfq_code"] = rfq.rfq_code
        if previous_rfq_status != rfq.status:
            stage_event_payload["previous_rfq_status"] = previous_rfq_status
            stage_event_payload["new_rfq_status"] = rfq.status

        self._publish_event_best_effort(
            "stage.advanced",
            payload=stage_event_payload,
            metadata=self._build_event_metadata(
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_team=actor_team,
            ),
        )

        return self._load_detail(stage)

    @staticmethod
    def _validate_terminal_outcome_transition(current_status: str, new_status: str) -> None:
        validate_rfq_status_transition(current_status, new_status)

    def _get_go_no_go_decision(self, stage: RFQStage) -> str | None:
        return self._get_controlled_stage_decision(
            stage,
            rfq_stage_translator.GO_NO_GO_DECISION_FIELD,
        )

    def _get_controlled_stage_decision(self, stage: RFQStage, field_key: str) -> str | None:
        if not stage.mandatory_fields:
            return None

        required = [field.strip() for field in stage.mandatory_fields.split(",") if field.strip()]
        if field_key not in required:
            return None

        captured = stage.captured_data or {}
        raw_value = captured.get(field_key)

        try:
            return rfq_stage_translator.normalize_controlled_stage_decision_value(
                field_key,
                raw_value,
                allow_legacy_text=True,
            )
        except ValueError as exc:
            raise UnprocessableEntityError(str(exc)) from exc

    @staticmethod
    def _get_captured_stage_decision(captured_data: dict | None, field_key: str) -> str | None:
        if not isinstance(captured_data, dict):
            return None

        try:
            return rfq_stage_translator.normalize_controlled_stage_decision_value(
                field_key,
                captured_data.get(field_key),
                allow_legacy_text=True,
            )
        except ValueError:
            return None

    def _update_rfq_progress(self, rfq):
        """Recalculate RFQ progress from lifecycle-completed stages only."""
        stages = self.stage_ds.list_by_rfq(rfq.id)
        if not stages:
            return

        rfq.progress = calculate_rfq_lifecycle_progress(stages, rfq.status)
        self.session.flush()

    def _list_active_subtasks(self, stage_id):
        return (
            self.session.query(Subtask)
            .filter(Subtask.rfq_stage_id == stage_id, Subtask.deleted_at.is_(None))
            .order_by(Subtask.created_at)
            .all()
        )

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_event_metadata(
        self,
        actor_user_id: str | None,
        actor_name: str | None,
        actor_team: str | None,
    ) -> dict[str, Any]:
        request_id = get_request_id()
        metadata: dict[str, Any] = {
            "service_version": "v1",
        }

        if request_id and request_id != "-":
            metadata["request_id"] = request_id
        if actor_user_id:
            metadata["actor_user_id"] = actor_user_id
        if actor_name:
            metadata["actor_name"] = actor_name
        if actor_team:
            metadata["actor_team"] = actor_team

        return metadata

    def _publish_event_best_effort(self, event_type: str, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
        if not self.event_bus:
            return

        try:
            self.event_bus.publish(event_type=event_type, payload=payload, metadata=metadata)
        except Exception as exc:
            logger.warning(
                "event_publish_failed event_type=%s request_id=%s entity_ids=%s error=%s",
                event_type,
                metadata.get("request_id", "-"),
                {k: v for k, v in payload.items() if k.endswith("_id")},
                str(exc),
            )

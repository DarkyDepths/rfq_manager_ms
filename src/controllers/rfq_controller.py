"""
RFQ controller — business logic for the RFQ resource.

Orchestrates:
- RFQ creation: validates workflow_id, auto-generates rfq_stage instances,
  back-calculates planned dates from deadline, sets initial status,
  generates human-readable rfq_code (IF-XXXX / IB-XXXX),
  supports skip_stages for custom workflows
- RFQ update: deadline change triggers recalculation of all stage planned dates
- Stats & analytics aggregation

Dependencies: RfqDatasource, RfqStageDatasource, WorkflowDatasource
"""

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session

from src.datasources.rfq_datasource import RfqDatasource
from src.datasources.workflow_datasource import WorkflowDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.connectors.event_bus import EventBusConnector
from src.models.rfq_stage import RFQStage
from src.models.rfq_file import RFQFile
from src.translators import rfq_translator
from src.utils.errors import NotFoundError, BadRequestError, ConflictError
from src.utils.rfq_lifecycle import (
    apply_terminal_stage_freeze,
    calculate_progress_excluding_skipped,
    validate_rfq_status_transition,
)
from src.utils.rfq_status import (
    RFQ_STATUS_CANCELLED,
    RFQ_TERMINAL_STATUSES,
)
import csv
import io
from typing import List
from src.utils.pagination import PaginationParams, paginate, paginated_response
from src.utils.observability import get_request_id


logger = logging.getLogger(__name__)


class RfqController:

    def __init__(
        self,
        rfq_datasource: RfqDatasource,
        workflow_datasource: WorkflowDatasource,
        rfq_stage_datasource: RfqStageDatasource,
        session: Session,
        event_bus_connector: EventBusConnector | None = None,
    ):
        self.rfq_ds = rfq_datasource
        self.workflow_ds = workflow_datasource
        self.stage_ds = rfq_stage_datasource
        self.event_bus = event_bus_connector
        self.session = session

    # ══════════════════════════════════════════════════
    # CREATE — the most complex method
    # ══════════════════════════════════════════════════
    def create(
        self,
        request: rfq_translator.RfqCreateRequest,
        actor_user_id: str | None = None,
        actor_name: str | None = None,
        actor_team: str | None = None,
    ) -> rfq_translator.RfqDetail:
        """Create an RFQ with auto-generated stages."""

        # ── 1. Validate workflow exists ───────────────
        workflow = self.workflow_ds.get_by_id(request.workflow_id)
        if not workflow:
            raise NotFoundError(f"Workflow '{request.workflow_id}' not found")

        effective_templates = self._resolve_effective_workflow_stages(workflow)
        if not effective_templates:
            raise BadRequestError(f"Workflow '{workflow.name}' has no stage templates")

        # ── 2. Filter stages for custom workflows ─────
        # skip_stages allows cherry-picking: only create stages NOT in the skip list
        active_templates = self._build_active_stage_templates(
            workflow,
            effective_templates,
            request.skip_stages,
        )

        if not active_templates:
            raise BadRequestError("Cannot create RFQ with zero stages. At least one stage must remain.")

        self._validate_workflow_feasible_deadline(
            request.deadline,
            active_templates,
        )

        # ── 3. Generate rfq_code ──────────────────────
        rfq_code = self.rfq_ds.get_next_code(request.code_prefix)

        # ── 4. Create the RFQ row ─────────────────────
        rfq_data = rfq_translator.from_create_request(request)
        rfq_data["rfq_code"] = rfq_code
        rfq_data["status"] = "In preparation"
        rfq = self.rfq_ds.create(rfq_data)

        # ── 5. Calculate planned dates ────────────────
        stage_dates = self._calculate_stage_dates(
            deadline=request.deadline,
            stages=active_templates,
        )

        # ── 6. Create rfq_stage rows ─────────────────
        overrides = {}
        if request.stage_overrides:
            for override in request.stage_overrides:
                overrides[override.stage_template_id] = override.assigned_team

        first_stage = None
        for new_order, template in enumerate(sorted(active_templates, key=lambda s: s.order), start=1):
            dates = stage_dates[new_order]
            assigned_team = overrides.get(template.id, template.default_team)

            stage_data = {
                "rfq_id": rfq.id,
                "stage_template_id": template.id,
                "name": template.name,
                "order": new_order,  # re-numbered sequentially
                "assigned_team": assigned_team,
                "status": "Not Started",
                "progress": 0,
                "planned_start": dates["start"],
                "planned_end": dates["end"],
                "mandatory_fields": template.mandatory_fields,  # snapshot from template
            }

            if new_order == 1:
                stage_data["status"] = "In Progress"
                stage_data["actual_start"] = date.today()

            stage = self.stage_ds.create(stage_data)

            if new_order == 1:
                first_stage = stage

        # ── 7. Set current_stage_id ───────────────────
        if first_stage:
            rfq.current_stage_id = first_stage.id
            self.session.flush()

        # ── 8. Commit — everything or nothing ─────────
        self.session.commit()
        self.session.refresh(rfq)

        self._publish_event_best_effort(
            "rfq.created",
            payload={
                "rfq_id": str(rfq.id),
                "rfq_code": rfq.rfq_code,
                "name": rfq.name,
                "client": rfq.client,
                "status": rfq.status,
                "priority": rfq.priority,
                "workflow_id": str(rfq.workflow_id),
                "deadline": rfq.deadline.isoformat() if rfq.deadline else None,
                "owner": rfq.owner,
                "created_at": (
                    rfq.created_at.isoformat()
                    if isinstance(rfq.created_at, datetime)
                    else None
                ),
            },
            metadata=self._build_event_metadata(actor_user_id, actor_name, actor_team),
        )

        return self._to_detail_response(
            rfq,
            current_stage_name=first_stage.name if first_stage else None,
            workflow_name=workflow.name,
        )

    # ══════════════════════════════════════════════════
    # GET
    # ══════════════════════════════════════════════════
    def get(self, rfq_id) -> rfq_translator.RfqDetail:
        """Fetch one RFQ by ID. Raises 404 if not found."""
        rfq = self.rfq_ds.get_by_id(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{rfq_id}' not found")

        return self._to_detail_response(rfq)

    # ══════════════════════════════════════════════════
    # LIST
    # ══════════════════════════════════════════════════
    def list(
        self,
        search: str = None,
        status: List[str] = None,
        priority: str = None,
        owner: str = None,
        created_after = None,
        created_before = None,
        sort: str = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """List RFQs with filters, sort, and pagination."""
        query = self._build_filtered_rfq_query(
            search=search,
            status=status,
            priority=priority,
            owner=owner,
            created_after=created_after,
            created_before=created_before,
            sort=sort,
        )

        params = PaginationParams(page=page, size=size)
        items, total = paginate(query, params)

        # ── Pre-load names to avoid N+1 queries ──
        summary_items = self._enrich_summaries(items)
        return paginated_response(summary_items, total, params)

    def export_csv(
        self,
        search: str = None,
        status: List[str] = None,
        priority: str = None,
        owner: str = None,
        created_after = None,
        created_before = None,
        sort: str = None,
    ) -> str:
        """Export filtered RFQs as a CSV string."""
        query = self._build_filtered_rfq_query(
            search=search,
            status=status,
            priority=priority,
            owner=owner,
            created_after=created_after,
            created_before=created_before,
            sort=sort,
        )
        rfqs = query.all()

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["RFQ Code", "Name", "Client", "Priority", "Status", "Progress (%)", "Deadline", "Owner", "Created At"])
        
        for rfq in rfqs:
            writer.writerow([
                rfq.rfq_code or "",
                rfq.name,
                rfq.client,
                rfq.priority,
                rfq.status,
                rfq.progress,
                rfq.deadline.isoformat() if rfq.deadline else "",
                rfq.owner,
                rfq.created_at.isoformat() if rfq.created_at else ""
            ])

        return output.getvalue()

    def _build_filtered_rfq_query(
        self,
        *,
        search: str = None,
        status: List[str] = None,
        priority: str = None,
        owner: str = None,
        created_after=None,
        created_before=None,
        sort: str = None,
    ):
        return self.rfq_ds.list(
            search=search,
            status=status,
            priority=priority,
            owner=owner,
            created_after=created_after,
            created_before=created_before,
            sort=sort,
        )
            

    # ══════════════════════════════════════════════════
    # STATS (#5)
    # ══════════════════════════════════════════════════
    def get_stats(self) -> dict:
        """Dashboard KPIs: total, open, critical, avg cycle."""
        return self.rfq_ds.get_stats()

    # ══════════════════════════════════════════════════
    # ANALYTICS (#6)
    # ══════════════════════════════════════════════════
    def get_analytics(self) -> dict:
        """Business analytics: win rate, margins, by-client breakdown."""
        return self.rfq_ds.get_analytics()

    # ══════════════════════════════════════════════════
    # UPDATE
    # ══════════════════════════════════════════════════
    def update(
        self,
        rfq_id,
        request: rfq_translator.RfqUpdateRequest,
        actor_user_id: str | None = None,
        actor_name: str | None = None,
        actor_team: str | None = None,
    ) -> rfq_translator.RfqDetail:
        """Partial update. Deadline change triggers stage date recalculation."""
        rfq = self.rfq_ds.get_by_id(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{rfq_id}' not found")

        update_data = request.model_dump(exclude_unset=True)
        previous_deadline = rfq.deadline

        if update_data and rfq.status in RFQ_TERMINAL_STATUSES:
            raise ConflictError(
                "Terminal RFQs are read-only through standard lifecycle controls."
            )

        workflow = None
        if "deadline" in update_data:
            workflow = self.workflow_ds.get_by_id(rfq.workflow_id)
            effective_stages = (
                self._resolve_effective_workflow_stages(workflow)
                if workflow
                else []
            )
            if effective_stages:
                self._validate_workflow_feasible_deadline(
                    update_data["deadline"],
                    effective_stages,
                )
            self._recalculate_stage_dates(
                rfq,
                update_data["deadline"],
                workflow=workflow,
            )

        if (
            "outcome_reason" in update_data
            and rfq.status not in RFQ_TERMINAL_STATUSES
        ):
            raise BadRequestError(
                "outcome_reason can only be set when the RFQ is in a terminal state."
            )

        rfq = self.rfq_ds.update(rfq, update_data)
        self.session.commit()
        self.session.refresh(rfq)

        metadata = self._build_event_metadata(actor_user_id, actor_name, actor_team)

        if previous_deadline != rfq.deadline:
            self._publish_event_best_effort(
                "rfq.deadline_changed",
                payload={
                    "rfq_id": str(rfq.id),
                    "rfq_code": rfq.rfq_code,
                    "previous_deadline": previous_deadline.isoformat() if previous_deadline else None,
                    "new_deadline": rfq.deadline.isoformat() if rfq.deadline else None,
                    "changed_at": self._utc_now_iso(),
                },
                metadata=metadata,
            )

        return self._to_detail_response(rfq)

    def cancel(
        self,
        rfq_id,
        request: rfq_translator.RfqCancelRequest,
        actor_user_id: str | None = None,
        actor_name: str | None = None,
        actor_team: str | None = None,
    ) -> rfq_translator.RfqDetail:
        """Explicit safe-cancel path. Preserves history and freezes workflow progression."""
        rfq = self.rfq_ds.get_by_id(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{rfq_id}' not found")

        update_data = request.model_dump(exclude_unset=True)
        previous_status = rfq.status

        if rfq.status != RFQ_STATUS_CANCELLED:
            self._validate_status_transition(rfq.status, RFQ_STATUS_CANCELLED)
            update_data["status"] = RFQ_STATUS_CANCELLED
            self._apply_terminal_stage_freeze(rfq, update_data)
        elif not update_data:
            return self._to_detail_response(rfq)

        rfq = self.rfq_ds.update(rfq, update_data)
        self.session.commit()
        self.session.refresh(rfq)

        if previous_status != rfq.status:
            self._publish_event_best_effort(
                "rfq.status_changed",
                payload={
                    "rfq_id": str(rfq.id),
                    "rfq_code": rfq.rfq_code,
                    "previous_status": previous_status,
                    "new_status": rfq.status,
                    "changed_at": self._utc_now_iso(),
                },
                metadata=self._build_event_metadata(
                    actor_user_id,
                    actor_name,
                    actor_team,
                ),
            )

        return self._to_detail_response(rfq)

    # ══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════

    def _enrich_summaries(self, rfqs) -> list:
        """Pre-load workflow and stage names in bulk to avoid N+1 queries."""
        if not rfqs:
            return []

        workflow_ids = {r.workflow_id for r in rfqs if r.workflow_id}
        stage_ids = {r.current_stage_id for r in rfqs if r.current_stage_id}

        from src.models.workflow import Workflow

        workflows = self.session.query(Workflow).filter(Workflow.id.in_(workflow_ids)).all()
        wf_map = {w.id: w.name for w in workflows}

        stages = self.session.query(RFQStage).filter(RFQStage.id.in_(stage_ids)).all()
        st_map = {s.id: s for s in stages}

        results = []
        for rfq in rfqs:
            wf_name = wf_map.get(rfq.workflow_id)
            current_stage = st_map.get(rfq.current_stage_id)
            st_name = current_stage.name if current_stage else None
            rfq.current_stage_order = current_stage.order if current_stage else None
            rfq.current_stage_status = current_stage.status if current_stage else None
            rfq.current_stage_blocker_status = (
                current_stage.blocker_status
                if current_stage and current_stage.blocker_status == "Blocked"
                else None
            )
            rfq.current_stage_blocker_reason_code = (
                current_stage.blocker_reason_code
                if current_stage
                and current_stage.blocker_status == "Blocked"
                and isinstance(current_stage.blocker_reason_code, str)
                and current_stage.blocker_reason_code.strip()
                else None
            )
            results.append(rfq_translator.to_summary(rfq, current_stage_name=st_name, workflow_name=wf_name))
            
        return results

    @staticmethod
    def _get_stage_planned_duration_days(stage) -> int:
        duration = getattr(stage, "planned_duration_days", None)
        if isinstance(duration, int):
            return max(duration, 0)
        return 5

    def _calculate_total_planned_duration_days(self, stages) -> int:
        return sum(self._get_stage_planned_duration_days(stage) for stage in stages)

    def _calculate_minimum_feasible_deadline(
        self,
        stages,
        reference_date: date | None = None,
    ) -> date:
        return (reference_date or date.today()) + timedelta(
            days=self._calculate_total_planned_duration_days(stages),
        )

    def _validate_workflow_feasible_deadline(self, deadline: date, stages) -> None:
        if not stages:
            return

        minimum_deadline = self._calculate_minimum_feasible_deadline(stages)
        if deadline < minimum_deadline:
            raise BadRequestError(
                f"This deadline is too narrow for the selected workflow. Choose {minimum_deadline.isoformat()} or later."
            )

    def _calculate_stage_dates(self, deadline: date, stages) -> dict:
        """Back-calculate planned_start/planned_end from the deadline.
        Uses sequential order (1, 2, 3...) after any skip filtering.
        """
        result = {}
        # Sort by original order, then assign dates backwards
        sorted_stages = sorted(stages, key=lambda s: s.order if hasattr(s, 'order') else 0, reverse=True)
        current_end = deadline

        for i, stage in enumerate(sorted_stages):
            duration = self._get_stage_planned_duration_days(stage)
            stage_start = current_end - timedelta(days=duration)

            # new_order is the sequential position from the end
            new_order = len(sorted_stages) - i
            result[new_order] = {
                "start": stage_start,
                "end": current_end,
            }
            current_end = stage_start

        return result

    def _recalculate_stage_dates(self, rfq, new_deadline: date, workflow=None):
        """When the deadline changes, recalculate all uncompleted stage planned dates."""
        workflow = workflow or self.workflow_ds.get_by_id(rfq.workflow_id)
        if not workflow:
            return

        effective_stages = self._resolve_effective_workflow_stages(workflow)

        stages = (
            self.session.query(RFQStage)
            .filter_by(rfq_id=rfq.id)
            .order_by(RFQStage.order.asc())
            .all()
        )

        if not stages:
            return

        # Back-calculate from new deadline using actual stage durations
        current_end = new_deadline
        for stage in reversed(stages):
            # Find the template duration by stable template ID (LG-05).
            duration = 5  # default
            template = None

            if getattr(stage, "stage_template_id", None):
                template = next(
                    (t for t in effective_stages if t.id == stage.stage_template_id),
                    None,
                )
            else:
                # Legacy fallback: old rows may not yet have stage_template_id populated.
                template = next(
                    (t for t in effective_stages if t.name == stage.name),
                    None,
                )

            if template:
                duration = self._get_stage_planned_duration_days(template)

            stage_start = current_end - timedelta(days=duration)

            if stage.status not in ("Completed", "Skipped"):
                stage.planned_start = stage_start
                stage.planned_end = current_end

            current_end = stage_start

        self.session.flush()

    def _get_current_stage_name(self, rfq) -> str | None:
        """Get the name of the current stage for response formatting."""
        if not rfq.current_stage_id:
            return None

        stage = self.session.query(RFQStage).filter(RFQStage.id == rfq.current_stage_id).first()
        return stage.name if stage else None

    def _get_workflow_name(self, workflow_id) -> str | None:
        """Get the workflow name for response formatting."""
        if not workflow_id:
            return None
        workflow = self.workflow_ds.get_by_id(workflow_id)
        return workflow.name if workflow else None

    def _get_intelligence_milestones(self, rfq_id) -> dict[str, Any]:
        query = self.session.query(RFQFile)
        if not hasattr(query, "join"):
            return {
                "source_package_available": False,
                "source_package_updated_at": None,
                "workbook_available": False,
                "workbook_updated_at": None,
            }

        files = (
            query.join(RFQStage, RFQStage.id == RFQFile.rfq_stage_id)
            .filter(
                RFQStage.rfq_id == rfq_id,
                RFQFile.deleted_at.is_(None),
            )
            .order_by(RFQFile.uploaded_at.desc())
            .all()
        )

        source_package = next((file for file in files if file.type == "Client RFQ"), None)
        workbook = next((file for file in files if file.type == "Estimation Workbook"), None)

        return {
            "source_package_available": source_package is not None,
            "source_package_updated_at": (
                source_package.uploaded_at if source_package is not None else None
            ),
            "workbook_available": workbook is not None,
            "workbook_updated_at": workbook.uploaded_at if workbook is not None else None,
        }

    def _to_detail_response(
        self,
        rfq,
        *,
        current_stage_name: str | None = None,
        workflow_name: str | None = None,
    ) -> rfq_translator.RfqDetail:
        milestones = self._get_intelligence_milestones(rfq.id)
        return rfq_translator.to_detail(
            rfq,
            current_stage_name=(
                current_stage_name
                if current_stage_name is not None
                else self._get_current_stage_name(rfq)
            ),
            workflow_name=(
                workflow_name
                if workflow_name is not None
                else self._get_workflow_name(rfq.workflow_id)
            ),
            source_package_available=milestones["source_package_available"],
            source_package_updated_at=milestones["source_package_updated_at"],
            workbook_available=milestones["workbook_available"],
            workbook_updated_at=milestones["workbook_updated_at"],
        )

    def _apply_terminal_stage_freeze(self, rfq, update_data: dict[str, Any]) -> None:
        apply_terminal_stage_freeze(self.session, rfq, update_data)

    def _validate_status_transition(self, current_status: str, new_status: str):
        """Raise 409 when a status transition violates lifecycle FSM."""
        validate_rfq_status_transition(current_status, new_status)

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

    def _calculate_progress_excluding_skipped(self, stages) -> int:
        """Compute RFQ progress from non-skipped stages to avoid progress deflation."""
        return calculate_progress_excluding_skipped(stages)

    def _resolve_effective_workflow_stages(self, workflow):
        selection_mode = getattr(workflow, "selection_mode", "fixed") or "fixed"
        if selection_mode != "customizable":
            return list(workflow.stages or [])

        if getattr(workflow, "base_workflow", None):
            return list(workflow.base_workflow.stages or [])

        base_workflow_id = getattr(workflow, "base_workflow_id", None)
        if not base_workflow_id:
            raise BadRequestError(
                f"Workflow '{workflow.name}' is customizable but has no base workflow configured."
            )

        base_workflow = self.workflow_ds.get_by_id(base_workflow_id)
        if not base_workflow:
            raise BadRequestError(
                f"Workflow '{workflow.name}' references a missing base workflow."
            )

        return list(base_workflow.stages or [])

    def _build_active_stage_templates(self, workflow, effective_templates, skip_stages):
        selection_mode = getattr(workflow, "selection_mode", "fixed") or "fixed"
        if not skip_stages:
            return list(effective_templates)

        if selection_mode != "customizable":
            raise BadRequestError(
                "Stage selection is only allowed for customizable workflows."
            )

        skip_set = set(skip_stages)
        effective_template_ids = {template.id for template in effective_templates}
        invalid_skip_ids = skip_set - effective_template_ids
        if invalid_skip_ids:
            raise BadRequestError(
                "One or more selected workflow stages do not belong to this customizable workflow."
            )

        required_stage_ids = {
            template.id
            for template in effective_templates
            if getattr(template, "is_required", False)
        }
        if skip_set & required_stage_ids:
            raise BadRequestError(
                "Required workflow stages cannot be removed."
            )

        return [template for template in effective_templates if template.id not in skip_set]

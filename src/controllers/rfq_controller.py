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

from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.datasources.rfq_datasource import RfqDatasource
from src.datasources.workflow_datasource import WorkflowDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.models.rfq_stage import RFQStage
from src.translators import rfq_translator
from src.utils.errors import NotFoundError, BadRequestError, ConflictError
import csv
import io
from typing import List
from src.utils.pagination import PaginationParams, paginate, paginated_response


class RfqController:

    VALID_STATUS_TRANSITIONS = {
        "Draft": {"In preparation", "Cancelled"},
        "In preparation": {"Submitted", "Cancelled"},
        "Submitted": {"Awarded", "Lost", "Cancelled"},
        "Awarded": set(),
        "Lost": set(),
        "Cancelled": set(),
    }

    TERMINAL_STATUSES = {"Awarded", "Lost", "Cancelled"}

    def __init__(
        self,
        rfq_datasource: RfqDatasource,
        workflow_datasource: WorkflowDatasource,
        rfq_stage_datasource: RfqStageDatasource,
        session: Session,
    ):
        self.rfq_ds = rfq_datasource
        self.workflow_ds = workflow_datasource
        self.stage_ds = rfq_stage_datasource
        self.session = session

    # ══════════════════════════════════════════════════
    # CREATE — the most complex method
    # ══════════════════════════════════════════════════
    def create(self, request: rfq_translator.RfqCreateRequest) -> rfq_translator.RfqDetail:
        """Create an RFQ with auto-generated stages."""

        # ── 1. Validate workflow exists ───────────────
        workflow = self.workflow_ds.get_by_id(request.workflow_id)
        if not workflow:
            raise NotFoundError(f"Workflow '{request.workflow_id}' not found")

        if not workflow.stages:
            raise BadRequestError(f"Workflow '{workflow.name}' has no stage templates")

        # ── 2. Generate rfq_code ──────────────────────
        rfq_code = self.rfq_ds.get_next_code(request.code_prefix)

        # ── 3. Create the RFQ row ─────────────────────
        rfq_data = rfq_translator.from_create_request(request)
        rfq_data["rfq_code"] = rfq_code
        rfq = self.rfq_ds.create(rfq_data)

        # ── 4. Filter stages for custom workflows ─────
        # skip_stages allows cherry-picking: only create stages NOT in the skip list
        active_templates = list(workflow.stages)
        if request.skip_stages:
            skip_set = set(request.skip_stages)
            active_templates = [t for t in active_templates if t.id not in skip_set]

        if not active_templates:
            raise BadRequestError("Cannot create RFQ with zero stages. At least one stage must remain.")

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

        return rfq_translator.to_detail(
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

        current_stage_name = self._get_current_stage_name(rfq)
        workflow_name = self._get_workflow_name(rfq.workflow_id)
        return rfq_translator.to_detail(rfq, current_stage_name=current_stage_name, workflow_name=workflow_name)

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
        query = self.rfq_ds.list(
            search=search, status=status, priority=priority, 
            owner=owner, created_after=created_after, created_before=created_before, 
            sort=sort
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
        query = self.rfq_ds.list(
            search=search, status=status, priority=priority, 
            owner=owner, created_after=created_after, created_before=created_before, 
            sort=sort
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
    def update(self, rfq_id, request: rfq_translator.RfqUpdateRequest) -> rfq_translator.RfqDetail:
        """Partial update. Deadline change triggers stage date recalculation."""
        rfq = self.rfq_ds.get_by_id(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ '{rfq_id}' not found")

        update_data = request.model_dump(exclude_unset=True)
        new_status = update_data.get("status")

        # ── LG-01: Enforce RFQ lifecycle FSM transitions ─────────────
        if new_status:
            self._validate_status_transition(rfq.status, new_status)

        if "deadline" in update_data:
            self._recalculate_stage_dates(rfq, update_data["deadline"])

        # ── GAP-1 & 3: Handle terminal state stage freezing ─────────────
        if new_status in self.TERMINAL_STATUSES and rfq.status != new_status:
            # 1. Skip current stage if not completed
            stages = (
                self.session.query(RFQStage)
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

            # 2. Skip all subsequent uncompleted stages
            for stage in stages:
                if stage.order > current_stage_order and stage.status != "Completed":
                    stage.status = "Skipped"

            # 3. Clear current_stage_id & freeze progress at current value
            update_data["current_stage_id"] = None
            # Do NOT update progress to 100, let the terminal status carry the business meaning

        rfq = self.rfq_ds.update(rfq, update_data)
        self.session.commit()
        self.session.refresh(rfq)

        current_stage_name = self._get_current_stage_name(rfq)
        workflow_name = self._get_workflow_name(rfq.workflow_id)
        return rfq_translator.to_detail(rfq, current_stage_name=current_stage_name, workflow_name=workflow_name)

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
        from src.models.rfq_stage import RFQStage

        workflows = self.session.query(Workflow).filter(Workflow.id.in_(workflow_ids)).all()
        wf_map = {w.id: w.name for w in workflows}

        stages = self.session.query(RFQStage).filter(RFQStage.id.in_(stage_ids)).all()
        st_map = {s.id: s.name for s in stages}

        results = []
        for rfq in rfqs:
            wf_name = wf_map.get(rfq.workflow_id)
            st_name = st_map.get(rfq.current_stage_id)
            results.append(rfq_translator.to_summary(rfq, current_stage_name=st_name, workflow_name=wf_name))
            
        return results

    def _calculate_stage_dates(self, deadline: date, stages) -> dict:
        """Back-calculate planned_start/planned_end from the deadline.
        Uses sequential order (1, 2, 3...) after any skip filtering.
        """
        result = {}
        # Sort by original order, then assign dates backwards
        sorted_stages = sorted(stages, key=lambda s: s.order if hasattr(s, 'order') else 0, reverse=True)
        current_end = deadline

        for i, stage in enumerate(sorted_stages):
            duration = stage.planned_duration_days if hasattr(stage, 'planned_duration_days') else 5
            stage_start = current_end - timedelta(days=duration)

            # new_order is the sequential position from the end
            new_order = len(sorted_stages) - i
            result[new_order] = {
                "start": stage_start,
                "end": current_end,
            }
            current_end = stage_start

        return result

    def _recalculate_stage_dates(self, rfq, new_deadline: date):
        """When the deadline changes, recalculate all uncompleted stage planned dates."""
        workflow = self.workflow_ds.get_by_id(rfq.workflow_id)
        if not workflow:
            return

        from src.models.rfq_stage import RFQStage
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
            # Find the template duration for this stage
            duration = 5  # default
            for t in workflow.stages:
                if t.name == stage.name:
                    duration = t.planned_duration_days
                    break

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

        from src.models.rfq_stage import RFQStage
        stage = self.session.query(RFQStage).filter(RFQStage.id == rfq.current_stage_id).first()
        return stage.name if stage else None

    def _get_workflow_name(self, workflow_id) -> str | None:
        """Get the workflow name for response formatting."""
        if not workflow_id:
            return None
        workflow = self.workflow_ds.get_by_id(workflow_id)
        return workflow.name if workflow else None

    def _validate_status_transition(self, current_status: str, new_status: str):
        """Raise 409 when a status transition violates lifecycle FSM."""
        if new_status == current_status:
            return

        allowed_next = self.VALID_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise ConflictError(
                f"Invalid RFQ status transition from '{current_status}' to '{new_status}'."
            )

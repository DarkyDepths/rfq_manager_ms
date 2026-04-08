"""
Workflow controller — business logic for the Workflow resource.

Orchestrates:
- List workflows (pass-through to datasource)
- Get workflow detail with embedded stage templates
- Update workflow metadata (is_active toggle, is_default uniqueness check)

Dependencies: WorkflowDatasource
"""

from sqlalchemy.orm import Session

from src.datasources.workflow_datasource import WorkflowDatasource
from src.translators import workflow_translator
from src.utils.errors import BadRequestError, NotFoundError


class WorkflowController:

    def __init__(self, datasource: WorkflowDatasource, session: Session):
        self.ds = datasource
        self.session = session

    def list(self) -> dict:
        workflows = self.ds.list_all()
        return {
            "data": [
                workflow_translator.to_summary(
                    workflow,
                    stages=self._resolve_effective_stages(workflow),
                )
                for workflow in workflows
            ]
        }

    def get(self, workflow_id) -> workflow_translator.WorkflowDetail:
        workflow = self.ds.get_by_id(workflow_id)
        if not workflow:
            raise NotFoundError(f"Workflow '{workflow_id}' not found")
        return workflow_translator.to_detail(
            workflow,
            stages=self._resolve_effective_stages(workflow),
        )

    def update(self, workflow_id, request: workflow_translator.WorkflowUpdateRequest) -> workflow_translator.WorkflowDetail:
        workflow = self.ds.get_by_id(workflow_id)
        if not workflow:
            raise NotFoundError(f"Workflow '{workflow_id}' not found")

        update_data = request.model_dump(exclude_unset=True)

        # Uniqueness guard: only one workflow can be default
        if update_data.get("is_default") is True:
            self.ds.clear_default()

        workflow = self.ds.update(workflow, update_data)
        self.session.commit()
        self.session.refresh(workflow)
        return workflow_translator.to_detail(
            workflow,
            stages=self._resolve_effective_stages(workflow),
        )

    def _resolve_effective_stages(self, workflow):
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

        base_workflow = self.ds.get_by_id(base_workflow_id)
        if not base_workflow:
            raise BadRequestError(
                f"Workflow '{workflow.name}' references a missing base workflow."
            )

        return list(base_workflow.stages or [])

"""
Dependency injection / application context.

Wires together all layers so that each request gets:
- A SQLAlchemy session (from database.py)
- Datasource instances (bound to the session)
- Connector instances (event_bus, iam_service)
- Controller instances (receiving datasources + connectors)

Exposes FastAPI `Depends(...)` callables that routes import directly.
This file is the single place where the object graph is assembled.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.config.settings import settings

# ── Datasources ───────────────────────────────────────
from src.datasources.rfq_datasource import RfqDatasource
from src.datasources.workflow_datasource import WorkflowDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.datasources.subtask_datasource import SubtaskDatasource
from src.datasources.file_datasource import FileDatasource
from src.datasources.reminder_datasource import ReminderDatasource

# ── Connectors ───────────────────────────────────────
from src.connectors.iam_service import IAMServiceConnector
from src.connectors.event_bus import EventBusConnector

# ── Controllers ───────────────────────────────────────
from src.controllers.rfq_controller import RfqController
from src.controllers.workflow_controller import WorkflowController
from src.controllers.rfq_stage_controller import RfqStageController
from src.controllers.subtask_controller import SubtaskController
from src.controllers.file_controller import FileController
from src.controllers.reminder_controller import ReminderController


# ═══════════════════════════════════════════════════════
# DATASOURCE PROVIDERS
# ═══════════════════════════════════════════════════════

def get_rfq_datasource(db: Session = Depends(get_db)) -> RfqDatasource:
    return RfqDatasource(db)

def get_workflow_datasource(db: Session = Depends(get_db)) -> WorkflowDatasource:
    return WorkflowDatasource(db)

def get_rfq_stage_datasource(db: Session = Depends(get_db)) -> RfqStageDatasource:
    return RfqStageDatasource(db)

def get_subtask_datasource(db: Session = Depends(get_db)) -> SubtaskDatasource:
    return SubtaskDatasource(db)

def get_file_datasource(db: Session = Depends(get_db)) -> FileDatasource:
    return FileDatasource(db)

def get_reminder_datasource(db: Session = Depends(get_db)) -> ReminderDatasource:
    return ReminderDatasource(db)


def get_iam_service_connector() -> IAMServiceConnector:
    return IAMServiceConnector(
        base_url=settings.IAM_SERVICE_URL,
        timeout_seconds=settings.IAM_REQUEST_TIMEOUT_SECONDS,
    )


def get_event_bus_connector() -> EventBusConnector:
    return EventBusConnector(
        base_url=settings.EVENT_BUS_URL,
        timeout_seconds=settings.EVENT_BUS_REQUEST_TIMEOUT_SECONDS,
    )


# ═══════════════════════════════════════════════════════
# CONTROLLER PROVIDERS
# ═══════════════════════════════════════════════════════

def get_rfq_controller(
    rfq_ds: RfqDatasource = Depends(get_rfq_datasource),
    workflow_ds: WorkflowDatasource = Depends(get_workflow_datasource),
    stage_ds: RfqStageDatasource = Depends(get_rfq_stage_datasource),
    event_bus: EventBusConnector = Depends(get_event_bus_connector),
    db: Session = Depends(get_db),
) -> RfqController:
    return RfqController(
        rfq_datasource=rfq_ds,
        workflow_datasource=workflow_ds,
        rfq_stage_datasource=stage_ds,
        event_bus_connector=event_bus,
        session=db,
    )

def get_workflow_controller(
    ds: WorkflowDatasource = Depends(get_workflow_datasource),
    db: Session = Depends(get_db),
) -> WorkflowController:
    return WorkflowController(datasource=ds, session=db)

def get_rfq_stage_controller(
    stage_ds: RfqStageDatasource = Depends(get_rfq_stage_datasource),
    rfq_ds: RfqDatasource = Depends(get_rfq_datasource),
    event_bus: EventBusConnector = Depends(get_event_bus_connector),
    db: Session = Depends(get_db),
) -> RfqStageController:
    return RfqStageController(
        stage_datasource=stage_ds,
        rfq_datasource=rfq_ds,
        event_bus_connector=event_bus,
        session=db,
    )

def get_subtask_controller(
    ds: SubtaskDatasource = Depends(get_subtask_datasource),
    stage_ds: RfqStageDatasource = Depends(get_rfq_stage_datasource),
    db: Session = Depends(get_db),
) -> SubtaskController:
    return SubtaskController(datasource=ds, stage_datasource=stage_ds, session=db)

def get_file_controller(
    ds: FileDatasource = Depends(get_file_datasource),
    stage_ds: RfqStageDatasource = Depends(get_rfq_stage_datasource),
    db: Session = Depends(get_db),
) -> FileController:
    return FileController(datasource=ds, stage_datasource=stage_ds, session=db)

def get_reminder_controller(
    ds: ReminderDatasource = Depends(get_reminder_datasource),
    db: Session = Depends(get_db),
) -> ReminderController:
    return ReminderController(datasource=ds, session=db)

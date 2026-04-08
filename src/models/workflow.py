import uuid

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base


class Workflow(Base):
    __tablename__ = "workflow"

    # ── Primary key ───────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Fields ────────────────────────────────────────
    name = Column(String(200), nullable=False)          # "GHI Long Workflow"
    code = Column(String(50), nullable=False, unique=True)  # "GHI-LONG"
    description = Column(String(1000), nullable=True)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)         # only one can be True
    selection_mode = Column(String(20), nullable=False, default="fixed")
    base_workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow.id"),
        nullable=True,
        index=True,
    )

    # ── Timestamps ────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────
    # relationship() doesn't create a column — it tells SQLAlchemy
    # "when I load a Workflow, also load its stage templates."
    # back_populates creates a two-way link: workflow.stages ↔ stage.workflow
    stages = relationship(
        "StageTemplate",
        back_populates="workflow",
        order_by="StageTemplate.order",  # always return stages in order
    )
    base_workflow = relationship(
        "Workflow",
        remote_side=[id],
        backref="derived_workflows",
    )


class StageTemplate(Base):
    """
    A template stage within a workflow.
    When an RFQ selects this workflow, each StageTemplate
    becomes an rfq_stage row with live dates and progress.
    """
    __tablename__ = "stage_template"

    # ── Primary key ───────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Foreign key ───────────────────────────────────
    # Points to the workflow this stage belongs to.
    # ondelete="CASCADE" means: if the workflow is deleted, delete its stages too.
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # we'll filter by workflow_id often
    )

    # ── Fields ────────────────────────────────────────
    name = Column(String(200), nullable=False)           # "BOQ / BOM Preparation"
    order = Column(Integer, nullable=False)              # 1, 2, 3...
    default_team = Column(String(100), nullable=True)    # "Engineering"
    planned_duration_days = Column(Integer, nullable=False, default=5)
    mandatory_fields = Column(String(500), nullable=True)  # comma-separated: "margin,final_price"
    is_required = Column(Boolean, nullable=False, default=False)

    # ── Relationships ─────────────────────────────────
    workflow = relationship("Workflow", back_populates="stages")

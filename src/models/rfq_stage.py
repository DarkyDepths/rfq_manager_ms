"""
SQLAlchemy model for the `rfq_stage` table.

Represents a live stage instance for a specific RFQ, cloned from
the workflow's stage template at RFQ creation time.

Columns:
- id                  UUID PK
- rfq_id              UUID FK → rfq.id
- stage_template_id   UUID FK → stage_template.id (nullable for legacy rows)
- name                VARCHAR  — stage name (copied from template)
- order               INTEGER  — execution order within the RFQ
- assigned_team       VARCHAR  — team responsible for this stage
- status              VARCHAR  — Not started | In Progress | Completed | Skipped
- progress            INTEGER  — 0-100
- planned_start       DATE
- planned_end         DATE
- actual_start        DATE     (nullable)
- actual_end          DATE     (nullable)
- blocker_status      VARCHAR  — Blocked | Resolved (nullable, NULL = never blocked)
- blocker_reason_code VARCHAR  (nullable)
- captured_data       JSONB    — free-form stage-specific form fields
- mandatory_fields    TEXT     — snapshot from template for /advance guard
- created_at          TIMESTAMP WITH TZ
- updated_at          TIMESTAMP WITH TZ

Relationships:
- subtasks → one-to-many with subtask table
- notes    → one-to-many with rfq_note table
- files    → one-to-many with rfq_file table
- field_values → one-to-many with rfq_stage_field_value table (schema-present, intentionally dormant in V1)
"""

import uuid

from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class RFQStage(Base):
    __tablename__ = "rfq_stage"

    # ── Primary key ───────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Foreign key to RFQ ────────────────────────────
    rfq_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # every query filters by rfq_id
    )

    # Optional for legacy compatibility; newly created stages should always set it.
    stage_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stage_template.id"),
        nullable=True,
    )

    # ── Copied from StageTemplate ─────────────────────
    name = Column(String(200), nullable=False)            # "BOQ / BOM Preparation"
    order = Column(Integer, nullable=False, index=True)   # 1, 2, 3...
    assigned_team = Column(String(100), nullable=True)    # can be overridden per RFQ

    # ── Live tracking ─────────────────────────────────
    status = Column(
        String(50),
        nullable=False,
        default="Not Started",  # Not Started | In Progress | Completed | Skipped
    )
    progress = Column(Integer, nullable=False, default=0)  # 0–100

    # ── Planned dates (back-calculated from deadline) ─
    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)

    # ── Actual dates (set during execution) ───────────
    actual_start = Column(Date, nullable=True)    # set when stage transitions to "In Progress"
    actual_end = Column(Date, nullable=True)      # set when stage transitions to "Completed"

    # ── Blocker tracking (orthogonal to status) ───────
    # NULL = never blocked.
    # "Blocked" = something is preventing progress.
    # "Resolved" = was blocked, now unblocked.
    blocker_status = Column(String(20), nullable=True)     # Blocked | Resolved
    blocker_reason_code = Column(String(100), nullable=True)  # supplier_delay, missing_client_docs, etc.

    # ── Stage-specific data ───────────────────────────
    # V1 source of truth for stage-form data is this JSON field.
    # `rfq_stage_field_value` remains intentionally dormant in V1 to avoid
    # duplicate persistence models for the same payload.
    # Example for "Commercial Review": {"margin": 18.5, "discount": 2.0}
    captured_data = Column(JSON, nullable=True, default=dict)

    # Snapshot of which fields are mandatory for /advance validation.
    # Comes from the stage template config. Example: "margin,final_price"
    mandatory_fields = Column(String(500), nullable=True)

    # ── Timestamps ────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

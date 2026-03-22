"""
SQLAlchemy model for the `rfq_stage_field_value` table.

Stores per-field stage payload snapshots as JSON values.

In current V1 this table is intentionally dormant by H5 decision, while active
stage input is represented via `rfq_stage.captured_data`.
This model docstring is aligned to the actual persisted columns.

Columns:
- id              UUID PK
- rfq_stage_id    UUID FK → rfq_stage.id
- field_name      VARCHAR  — key name (e.g. "vessel_count", "material_grade")
- value           JSON      — JSON payload for the field
- updated_by      VARCHAR   (nullable)
- updated_at      TIMESTAMP WITH TZ
"""

import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class RFQStageFieldValue(Base):
    __tablename__ = "rfq_stage_field_value"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Parent stage ──────────────────────────────────
    rfq_stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq_stage.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Key-value pair ────────────────────────────────
    field_name = Column(String(200), nullable=False)     # "margin", "final_price"
    value = Column(JSON, nullable=True)                  # any JSON-serializable value

    # ── Metadata ──────────────────────────────────────
    updated_by = Column(String(200), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

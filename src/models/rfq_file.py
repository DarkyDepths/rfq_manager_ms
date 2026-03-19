"""
SQLAlchemy model for the `rfq_file` table.

Files uploaded to an RFQ stage (multipart upload).

Columns:
- id              UUID PK
- rfq_stage_id    UUID FK → rfq_stage.id
- filename        VARCHAR  — original filename
- file_path       VARCHAR  — storage path (local or Azure Blob)
- type            VARCHAR  — Client RFQ | Design report | BOQ / BOM | Estimation Workbook | Other
- uploaded_by     VARCHAR  — user who uploaded the file
- size_bytes      BIGINT   — file size in bytes
- uploaded_at     TIMESTAMP WITH TZ
- deleted_at      TIMESTAMP WITH TZ (nullable) — soft delete
"""

import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class RFQFile(Base):
    __tablename__ = "rfq_file"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Parent stage ──────────────────────────────────
    rfq_stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq_stage.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Fields ────────────────────────────────────────
    filename = Column(String(500), nullable=False)       # "HP_Separator_BOQ_v2.xlsx"
    file_path = Column(String(1000), nullable=False)     # "./uploads/abc123.xlsx" or blob URL
    type = Column(String(100), nullable=False)           # Client RFQ | Design report | BOQ / BOM | Estimation Workbook | Other
    uploaded_by = Column(String(200), nullable=False)    # user who uploaded
    size_bytes = Column(BigInteger, nullable=True)       # file size in bytes

    # ── Soft delete ───────────────────────────────────
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # ── Timestamp ─────────────────────────────────────
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

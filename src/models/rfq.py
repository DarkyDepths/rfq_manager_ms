"""
SQLAlchemy model for the `rfq` table.

Columns:
- id              UUID PK
- name            VARCHAR  — RFQ display name
- client          VARCHAR  — client / company name
- industry        VARCHAR  — industry sector (nullable)
- country         VARCHAR  — country (nullable)
- priority        VARCHAR  — 'normal' | 'critical'
- status          VARCHAR  — In preparation | Awarded | Lost | Cancelled
- progress        INTEGER  — 0-100, auto-calculated from stages
- deadline        DATE     — submission / response deadline
- owner           VARCHAR  — responsible team or person
- description     TEXT     — free-text description (nullable)
- workflow_id     UUID FK  → workflow.id
- current_stage_id UUID FK → rfq_stage.id (nullable)
- outcome_reason  TEXT     — why awarded / lost / cancelled (nullable)
- created_at      TIMESTAMP WITH TZ
- updated_at      TIMESTAMP WITH TZ
"""

import uuid

from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class RFQ(Base):
    __tablename__ = "rfq"

    # ── Primary key ───────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Core fields (from RfqCreateRequest) ───────────
    name = Column(String(300), nullable=False)           # "HP Separator Package – Offshore"
    client = Column(String(200), nullable=False, index=True)  # "Saudi Aramco"
    industry = Column(String(200), nullable=True)        # "Oil & Gas – Upstream"
    country = Column(String(100), nullable=True)         # "Saudi Arabia"
    priority = Column(String(20), nullable=False, default="normal", index=True)  # normal | critical
    deadline = Column(Date, nullable=False, index=True)  # submission deadline
    owner = Column(String(200), nullable=False, index=True)          # "Proposals Team A"
    description = Column(String(2000), nullable=True)    # free text
    rfq_code = Column(String(20), unique=True, nullable=True, index=True)  # IF-0001 or IB-0001

    # ── Workflow link ─────────────────────────────────
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow.id"),
        nullable=False,
    )

    # ── State fields (set by the system, not the user) ─
    status = Column(
        String(50),
        nullable=False,
        default="In preparation",
        index=True,  # filtered in list endpoint for operational statuses
    )
    progress = Column(Integer, nullable=False, default=0)  # 0–100

    # Points to the currently active rfq_stage.
    # NULL when no current live stage is active.
    current_stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq_stage.id"),
        nullable=True,
        index=True,
    )

    # ── Outcome fields ────────────────────────────────
    # Set when status transitions to Awarded / Lost / Cancelled
    outcome_reason = Column(String(1000), nullable=True)  # "Best technical score"

    # ── Timestamps ────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

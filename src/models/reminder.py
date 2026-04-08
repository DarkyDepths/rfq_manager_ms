"""
SQLAlchemy model for the `reminder` table.

Tracks manual and auto-created reminders for RFQs and stages.

Columns:
- id              UUID PK
- rfq_id          UUID FK → rfq.id
- rfq_stage_id    UUID FK → rfq_stage.id (nullable)
- reminder_rule_id UUID FK → reminder_rule.id (nullable for automatic reminders)
- type            VARCHAR  — internal | external
- message         TEXT
- due_date        DATE
- assigned_to     VARCHAR  (nullable)
- status          VARCHAR  — open | overdue | resolved
- source          VARCHAR  — manual | automatic
- created_by      VARCHAR
- created_at      TIMESTAMP WITH TZ
- updated_at      TIMESTAMP WITH TZ
- last_sent_at    TIMESTAMP WITH TZ (nullable) — used by batch to rate-limit re-sends
- send_count      INTEGER  — number of times notification was sent, default 0

Note: `delay_days` is computed at query time (MAX(0, NOW()::date - due_date)), NOT stored.
"""

import uuid

from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class Reminder(Base):
    __tablename__ = "reminder"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Links to RFQ (required) and stage (optional) ──
    rfq_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rfq_stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rfq_stage.id", ondelete="SET NULL"),
        nullable=True,
    )
    reminder_rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reminder_rule.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Fields ────────────────────────────────────────
    type = Column(String(20), nullable=False)            # internal | external
    message = Column(String(1000), nullable=False)       # "Follow up on nozzle material"
    due_date = Column(Date, nullable=False, index=True)
    assigned_to = Column(String(200), nullable=True)     # "Engineering"
    status = Column(String(20), nullable=False, default="open", index=True)  # open | overdue | resolved
    source = Column(String(20), nullable=False, default="manual", index=True)  # manual | automatic
    created_by = Column(String(200), nullable=True)      # user who created it

    # ── Notification tracking ─────────────────────────
    send_count = Column(Integer, nullable=False, default=0)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)  # for rate-limiting re-sends

    # ── Timestamps ────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # NOTE: delay_days is NOT a column. It's computed at query time:
    #   MAX(0, today - due_date)
    # The translator calculates it when building the response.


class ReminderRule(Base):
    """
    Pre-seeded rules for auto-generating reminders.
    Admins toggle is_active on/off. The batch process reads active rules.
    """
    __tablename__ = "reminder_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Fields ────────────────────────────────────────
    name = Column(String(200), nullable=False)           # "Stage overdue alert"
    description = Column(String(1000), nullable=True)
    scope = Column(String(100), nullable=False)          # all_rfqs | critical_only | stage_overdue | etc.
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Timestamp ─────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())

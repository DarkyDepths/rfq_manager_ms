"""
RFQ datasource — database queries for the `rfq` table.
"""

from sqlalchemy import or_, func, text
from sqlalchemy.orm import Session
from typing import List

from src.models.rfq import RFQ
from src.utils.errors import BadRequestError
from src.utils.rfq_status import (
    RFQ_ACTIVE_STATUSES,
    RFQ_DECIDED_STATUSES,
    RFQ_STATUS_DRAFT,
    RFQ_STATUS_AWARDED,
    RFQ_STATUS_LOST,
)


class RfqDatasource:

    SORT_WHITELIST = {"name", "client", "deadline", "created_at", "priority", "status", "progress", "owner"}

    def __init__(self, session: Session):
        self.session = session

    def create(self, data: dict) -> RFQ:
        """Insert a new RFQ row. Uses flush() — controller commits."""
        rfq = RFQ(**data)
        self.session.add(rfq)
        self.session.flush()
        self.session.refresh(rfq)
        return rfq

    def get_by_id(self, rfq_id) -> RFQ | None:
        """Fetch one RFQ by primary key."""
        return self.session.query(RFQ).filter(RFQ.id == rfq_id).first()

    def list(
        self,
        search: str = None,
        status: List[str] = None,
        priority: str = None,
        owner: str = None,
        created_after = None,
        created_before = None,
        sort: str = None,
    ):
        """Build a filtered, sorted query. Returns the query object for pagination."""
        query = self.session.query(RFQ)

        # ── Filters ───────────────────────────────────
        if status:
            query = query.filter(RFQ.status.in_(status))
        else:
            query = query.filter(RFQ.status != RFQ_STATUS_DRAFT)

        if priority:
            query = query.filter(RFQ.priority == priority)

        if owner:
            query = query.filter(RFQ.owner == owner)

        if created_after:
            query = query.filter(RFQ.created_at >= created_after)

        if created_before:
            from datetime import date as _date, datetime as _datetime, timedelta
            if isinstance(created_before, (_datetime, _date)):
                next_day = created_before + timedelta(days=1)
                query = query.filter(RFQ.created_at < next_day)
            else:
                query = query.filter(RFQ.created_at <= created_before)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    RFQ.name.ilike(search_term),
                    RFQ.client.ilike(search_term),
                )
            )

        # ── Sort ──────────────────────────────────────
        if sort:
            descending = sort.startswith("-")
            column_name = sort[1:] if descending else sort

            if column_name not in self.SORT_WHITELIST:
                allowed = ", ".join(sorted(self.SORT_WHITELIST))
                raise BadRequestError(
                    f"Invalid sort field '{column_name}'. Allowed fields: {allowed}."
                )

            column = getattr(RFQ, column_name)
            query = query.order_by(column.desc() if descending else column.asc())
        else:
            query = query.order_by(RFQ.created_at.desc())

        return query

    def update(self, rfq: RFQ, data: dict) -> RFQ:
        """Partial update. Uses flush() — controller commits."""
        for key, value in data.items():
            if hasattr(rfq, key):
                setattr(rfq, key, value)

        self.session.flush()
        self.session.refresh(rfq)
        return rfq

    def get_next_code(self, prefix: str) -> str:
        """Generate the next RFQ code atomically for the given prefix (e.g. IF-0001)."""
        normalized_prefix = (prefix or "").strip().upper()
        if not normalized_prefix:
            raise BadRequestError("RFQ code prefix is required")

        self._ensure_counter_row_exists(normalized_prefix)

        next_value = self.session.execute(
            text(
                """
                UPDATE rfq_code_counter
                SET last_value = last_value + 1
                WHERE prefix = :prefix
                RETURNING last_value
                """
            ),
            {"prefix": normalized_prefix},
        ).scalar_one_or_none()

        if next_value is None:
            raise BadRequestError(f"Failed to allocate RFQ code for prefix '{normalized_prefix}'")

        return f"{normalized_prefix}-{next_value:04d}"

    def _ensure_counter_row_exists(self, prefix: str) -> None:
        """Create counter row lazily if absent, seeded from existing RFQ data."""
        dialect = self.session.bind.dialect.name if self.session.bind else None

        if dialect == "postgresql":
            self.session.execute(
                text(
                    """
                    INSERT INTO rfq_code_counter (prefix, last_value)
                    SELECT
                        :prefix,
                        COALESCE(MAX(CAST(split_part(rfq_code, '-', 2) AS INTEGER)), 0)
                    FROM rfq
                    WHERE split_part(rfq_code, '-', 1) = :prefix
                      AND rfq_code ~ :pattern
                    ON CONFLICT (prefix) DO NOTHING
                    """
                ),
                {
                    "prefix": prefix,
                    "pattern": rf"^{prefix}-[0-9]+$",
                },
            )
            return

        # SQLite-compatible fallback used by tests and local quality gate DB.
        self.session.execute(
            text(
                """
                INSERT INTO rfq_code_counter (prefix, last_value)
                SELECT
                    :prefix,
                    COALESCE(
                        MAX(
                            CAST(
                                SUBSTR(rfq_code, INSTR(rfq_code, '-') + 1)
                                AS INTEGER
                            )
                        ),
                        0
                    )
                FROM rfq
                WHERE rfq_code GLOB :glob_pattern
                ON CONFLICT(prefix) DO NOTHING
                """
            ),
            {
                "prefix": prefix,
                "glob_pattern": f"{prefix}-[0-9]*",
            },
        )

    def get_stats(self) -> dict:
        """Dashboard KPIs (#5): total_rfqs_12m, open_rfqs, critical_rfqs, avg_cycle_days."""
        from datetime import date, timedelta

        twelve_months_ago = date.today() - timedelta(days=365)

        total = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.created_at >= twelve_months_ago)
            .scalar() or 0
        )

        open_rfqs = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.status.in_(RFQ_ACTIVE_STATUSES))
            .scalar() or 0
        )

        critical = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.priority == "critical")
            .filter(RFQ.status.in_(RFQ_ACTIVE_STATUSES))
            .scalar() or 0
        )

        avg_cycle = (
            self.session.query(
                func.avg(
                    func.extract("epoch", RFQ.updated_at) - func.extract("epoch", RFQ.created_at)
                ) / 86400
            )
            .filter(RFQ.status.in_(RFQ_DECIDED_STATUSES))
            .scalar()
        )

        return {
            "total_rfqs_12m": total,
            "open_rfqs": open_rfqs,
            "critical_rfqs": critical,
            "avg_cycle_days": int(round(avg_cycle)) if avg_cycle else 0,
        }

    def get_analytics(self) -> dict:
        """
        Business analytics (#6): win_rate, margins, by-client breakdown.
        V1: margins return 0.0 — no reliable data yet.
        """
        awarded = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.status == RFQ_STATUS_AWARDED)
            .scalar() or 0
        )
        lost = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.status == RFQ_STATUS_LOST)
            .scalar() or 0
        )
        total_decided = awarded + lost
        win_rate = round((awarded / total_decided * 100), 1) if total_decided > 0 else 0.0

        from sqlalchemy import desc
        client_rows = (
            self.session.query(
                RFQ.client,
                func.count(RFQ.id).label("rfq_count"),
            )
            .group_by(RFQ.client)
            .order_by(desc("rfq_count"))
            .limit(20)
            .all()
        )

        by_client = [
            {"client": row.client, "rfq_count": row.rfq_count, "avg_margin": 0.0}
            for row in client_rows
        ]

        return {
            "avg_margin_submitted": 0.0,
            "avg_margin_awarded": 0.0,
            "estimation_accuracy": 0.0,
            "win_rate": win_rate,
            "by_client": by_client,
        }

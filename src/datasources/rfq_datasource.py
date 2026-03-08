"""
RFQ datasource — database queries for the `rfq` table.
"""

from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from typing import List

from src.models.rfq import RFQ


class RfqDatasource:

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
            query = query.filter(RFQ.status != "Draft")

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
            if sort.startswith("-"):
                column_name = sort[1:]
                descending = True
            else:
                column_name = sort
                descending = False

            column = getattr(RFQ, column_name, None)
            if column is not None:
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
        """Generate the next sequential RFQ code for the given prefix (e.g. IF-0001)."""
        import re
        # Find the max existing code with this prefix
        latest = (
            self.session.query(RFQ.rfq_code)
            .filter(RFQ.rfq_code.like(f"{prefix}-%"))
            .order_by(RFQ.rfq_code.desc())
            .first()
        )
        if latest and latest[0]:
            match = re.search(r'-(\d+)$', latest[0])
            next_num = int(match.group(1)) + 1 if match else 1
        else:
            next_num = 1
        return f"{prefix}-{next_num:04d}"

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
            .filter(RFQ.status.in_(["In preparation", "Submitted"]))
            .scalar() or 0
        )

        critical = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.priority == "critical")
            .filter(RFQ.status.in_(["In preparation", "Submitted"]))
            .scalar() or 0
        )

        avg_cycle = (
            self.session.query(
                func.avg(
                    func.extract("epoch", RFQ.updated_at) - func.extract("epoch", RFQ.created_at)
                ) / 86400
            )
            .filter(RFQ.status.in_(["Awarded", "Lost"]))
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
            .filter(RFQ.status == "Awarded")
            .scalar() or 0
        )
        lost = (
            self.session.query(func.count(RFQ.id))
            .filter(RFQ.status == "Lost")
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

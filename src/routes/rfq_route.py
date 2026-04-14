"""
RFQ routes — FastAPI router for RFQ endpoints.

Endpoints:
- POST   /rfqs              — #1 Create RFQ
- GET    /rfqs              — #2 List RFQs (paginated, with search/filter/sort)
- GET    /rfqs/export       — #3 Export RFQs as CSV
- GET    /rfqs/{rfqId}      — #4 Get RFQ detail
- PATCH  /rfqs/{rfqId}      — #5 Update RFQ
- POST   /rfqs/{rfqId}/cancel — #5b Safe cancel RFQ
- GET    /rfqs/stats        — #6 Dashboard KPIs
- GET    /rfqs/analytics    — #7 Business analytics
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from typing import Optional, Literal, List
from datetime import date

from src.translators.rfq_translator import (
    RfqCancelRequest,
    RfqCreateRequest,
    RfqUpdateRequest,
    RfqDetail,
    RfqListResponse,
    RfqStats,
    RfqAnalytics,
)
from src.utils.rfq_status import RfqStatusLiteral

from src.app_context import get_rfq_controller
from src.controllers.rfq_controller import RfqController
from src.utils.auth import AuthContext, Permissions, require_permission


router = APIRouter(prefix="/rfqs", tags=["RFQ"])


# ── #1 — Create RFQ ──────────────────────────────────
@router.post("", status_code=201, response_model=RfqDetail)
def create_rfq(
    body: RfqCreateRequest,
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_CREATE)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Create a new RFQ with auto-generated stages."""
    return ctrl.create(
        body,
        actor_user_id=auth.user_id,
        actor_name=auth.user_name,
        actor_team=auth.team,
    )


# ── #2 — List RFQs ───────────────────────────────────
@router.get("", response_model=RfqListResponse)
def list_rfqs(
    search: Optional[str] = Query(None, description="Search in name and client"),
    status: Optional[List[RfqStatusLiteral]] = Query(
        None,
        description="Filter by multiple operational statuses",
    ),
    priority: Optional[Literal["normal", "critical"]] = Query(None, description="Filter by priority"),
    owner: Optional[str] = Query(None, description="Filter by exact owner"),
    created_after: Optional[date] = Query(None, description="Filter RFQs created on or after this date"),
    created_before: Optional[date] = Query(None, description="Filter RFQs created on or before this date"),
    sort: Optional[str] = Query(None, description="Sort field, prefix - for desc"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    _auth=Depends(require_permission(Permissions.RFQ_READ)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Paginated list with search, filters, and sort."""
    return ctrl.list(search=search, status=status, priority=priority, owner=owner, created_after=created_after, created_before=created_before, sort=sort, page=page, size=size)


# ── #3 — Export RFQs ─────────────────────────────────
@router.get("/export", response_class=Response)
def export_rfqs(
    search: Optional[str] = Query(None, description="Search in name and client"),
    status: Optional[List[RfqStatusLiteral]] = Query(
        None,
        description="Filter by multiple operational statuses",
    ),
    priority: Optional[Literal["normal", "critical"]] = Query(None, description="Filter by priority"),
    owner: Optional[str] = Query(None, description="Filter by exact owner"),
    created_after: Optional[date] = Query(None, description="Filter RFQs created on or after this date"),
    created_before: Optional[date] = Query(None, description="Filter RFQs created on or before this date"),
    sort: Optional[str] = Query(None, description="Sort field, prefix - for desc"),
    _auth=Depends(require_permission(Permissions.RFQ_EXPORT)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Export filtered RFQs as a CSV file."""
    csv_content = ctrl.export_csv(
        search=search, status=status, priority=priority, 
        owner=owner, created_after=created_after, created_before=created_before, 
        sort=sort
    )
    return Response(
        content=csv_content, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=rfqs_export.csv"}
    )


# ── #6 — RFQ Stats ───────────────────────────────────
# IMPORTANT: /stats and /analytics must be BEFORE /{rfq_id}
@router.get("/stats", response_model=RfqStats)
def rfq_stats(
    _auth=Depends(require_permission(Permissions.RFQ_STATS)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Dashboard KPIs: total, open, critical, avg cycle."""
    return ctrl.get_stats()


# ── #7 — RFQ Analytics ───────────────────────────────
@router.get("/analytics", response_model=RfqAnalytics)
def rfq_analytics(
    _auth=Depends(require_permission(Permissions.RFQ_ANALYTICS)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Business analytics: win rate, margins, by-client breakdown."""
    return ctrl.get_analytics()


# ── #4 — Get RFQ Detail ──────────────────────────────
@router.get("/{rfq_id}", response_model=RfqDetail)
def get_rfq(
    rfq_id: UUID,
    _auth=Depends(require_permission(Permissions.RFQ_READ)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Full RFQ detail by ID."""
    return ctrl.get(rfq_id)


# ── #5 — Update RFQ ──────────────────────────────────
@router.patch("/{rfq_id}", response_model=RfqDetail)
def update_rfq(
    rfq_id: UUID,
    body: RfqUpdateRequest,
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_UPDATE)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Partial update — only send fields you want to change."""
    return ctrl.update(
        rfq_id,
        body,
        actor_user_id=auth.user_id,
        actor_name=auth.user_name,
        actor_team=auth.team,
    )


@router.post("/{rfq_id}/cancel", response_model=RfqDetail)
def cancel_rfq(
    rfq_id: UUID,
    body: RfqCancelRequest,
    auth: AuthContext = Depends(require_permission(Permissions.RFQ_UPDATE)),
    ctrl: RfqController = Depends(get_rfq_controller),
):
    """Explicit safe cancel path. Preserves RFQ history and generated stages."""
    return ctrl.cancel(
        rfq_id,
        body,
        actor_user_id=auth.user_id,
        actor_name=auth.user_name,
        actor_team=auth.team,
    )

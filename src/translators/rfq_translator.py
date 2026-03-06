"""
RFQ translator — converts between Pydantic schemas and the RFQ SQLAlchemy model.
"""

from datetime import date, datetime
from uuid import UUID
from typing import Optional, List, Literal

from pydantic import BaseModel


# ═══════════════════════════════════════════════════
# REQUEST SCHEMAS (what comes IN)
# ═══════════════════════════════════════════════════

class StageOverride(BaseModel):
    """Optional override for a specific stage's assigned team during RFQ creation."""
    stage_template_id: UUID
    assigned_team: str


class RfqCreateRequest(BaseModel):
    """POST /rfqs body."""
    name: str
    client: str
    deadline: date
    owner: str
    workflow_id: UUID
    industry: Optional[str] = None
    country: Optional[str] = None
    priority: Literal["normal", "critical"] = "normal"
    description: Optional[str] = None
    code_prefix: Literal["IF", "IB"] = "IF"
    stage_overrides: Optional[List[StageOverride]] = None
    skip_stages: Optional[List[UUID]] = None  # stage template IDs to exclude (custom workflow)


class RfqUpdateRequest(BaseModel):
    """PATCH /rfqs/{id} body. ALL fields optional."""
    name: Optional[str] = None
    client: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    priority: Optional[Literal["normal", "critical"]] = None
    deadline: Optional[date] = None
    owner: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["Draft", "In preparation", "Submitted", "Awarded", "Lost", "Cancelled"]] = None
    outcome_reason: Optional[str] = None


# ═══════════════════════════════════════════════════
# RESPONSE SCHEMAS (what goes OUT)
# ═══════════════════════════════════════════════════

class RfqSummary(BaseModel):
    """Short version for list rows — includes UI-required fields."""
    id: UUID
    rfq_code: Optional[str] = None
    name: str
    client: str
    country: Optional[str] = None
    owner: str
    priority: str
    status: str
    progress: int
    deadline: date
    current_stage_name: Optional[str] = None
    workflow_name: Optional[str] = None

    class Config:
        from_attributes = True


class RfqDetail(BaseModel):
    """Full detail — returned by GET /rfqs/{id}, POST /rfqs, PATCH /rfqs/{id}."""
    id: UUID
    rfq_code: Optional[str] = None
    name: str
    client: str
    status: str
    progress: int
    deadline: date
    current_stage_name: Optional[str] = None
    workflow_name: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    priority: str
    owner: str
    description: Optional[str] = None
    workflow_id: UUID
    current_stage_id: Optional[UUID] = None
    outcome_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RfqListResponse(BaseModel):
    """Paginated wrapper for GET /rfqs."""
    data: List[RfqSummary]
    total: int
    page: int
    size: int


class RfqStats(BaseModel):
    """GET /rfqs/stats response — dashboard KPIs."""
    total_rfqs_12m: int
    open_rfqs: int
    critical_rfqs: int
    avg_cycle_days: int


class RfqAnalyticsByClient(BaseModel):
    client: str
    rfq_count: int
    avg_margin: float


class RfqAnalytics(BaseModel):
    """GET /rfqs/analytics response — business analytics."""
    avg_margin_submitted: float
    avg_margin_awarded: float
    estimation_accuracy: float
    win_rate: float
    by_client: List[RfqAnalyticsByClient]


# ═══════════════════════════════════════════════════
# CONVERSION FUNCTIONS
# ═══════════════════════════════════════════════════

def to_summary(rfq, current_stage_name: str = None, workflow_name: str = None) -> RfqSummary:
    """SQLAlchemy RFQ model → RfqSummary (for list responses)."""
    return RfqSummary(
        id=rfq.id,
        rfq_code=rfq.rfq_code,
        name=rfq.name,
        client=rfq.client,
        country=rfq.country,
        owner=rfq.owner,
        priority=rfq.priority,
        status=rfq.status,
        progress=rfq.progress,
        deadline=rfq.deadline,
        current_stage_name=current_stage_name,
        workflow_name=workflow_name,
    )


def to_detail(rfq, current_stage_name: str = None, workflow_name: str = None) -> RfqDetail:
    """SQLAlchemy RFQ model → RfqDetail (for detail responses)."""
    return RfqDetail(
        id=rfq.id,
        rfq_code=rfq.rfq_code,
        name=rfq.name,
        client=rfq.client,
        status=rfq.status,
        progress=rfq.progress,
        deadline=rfq.deadline,
        current_stage_name=current_stage_name,
        workflow_name=workflow_name,
        industry=rfq.industry,
        country=rfq.country,
        priority=rfq.priority,
        owner=rfq.owner,
        description=rfq.description,
        workflow_id=rfq.workflow_id,
        current_stage_id=rfq.current_stage_id,
        outcome_reason=rfq.outcome_reason,
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def from_create_request(req: RfqCreateRequest) -> dict:
    """Pydantic request → dict for the datasource."""
    data = req.model_dump(exclude={"stage_overrides", "skip_stages", "code_prefix"})
    return data

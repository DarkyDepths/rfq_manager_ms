"""
RFQ translator — converts between Pydantic schemas and the RFQ SQLAlchemy model.
"""

from datetime import date, datetime
from uuid import UUID
from typing import Optional, List, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

# ═══════════════════════════════════════════════════
# REQUEST SCHEMAS (what comes IN)
# ═══════════════════════════════════════════════════

class StageOverride(BaseModel):
    """Optional override for a specific stage's assigned team during RFQ creation."""
    stage_template_id: UUID
    assigned_team: str


def _validate_deadline_not_in_past(value: date | None) -> date | None:
    if value is not None and value < date.today():
        raise ValueError("deadline cannot be in the past")
    return value


class RfqCreateRequest(BaseModel):
    """POST /rfqs body."""
    name: str
    client: str
    deadline: date
    owner: str
    workflow_id: UUID
    industry: str
    country: str
    priority: Literal["normal", "critical"]
    description: Optional[str] = None
    code_prefix: Literal["IF", "IB"] = "IF"
    stage_overrides: Optional[List[StageOverride]] = None
    skip_stages: Optional[List[UUID]] = None  # stage template IDs to exclude (custom workflow)

    @field_validator("name", "client", "owner", "industry", "country")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} is required")
        return normalized

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_in_past(cls, value: date) -> date:
        validated = _validate_deadline_not_in_past(value)
        return validated if validated is not None else value


class RfqUpdateRequest(BaseModel):
    """PATCH /rfqs/{id} body. ALL fields optional."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    client: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    priority: Optional[Literal["normal", "critical"]] = None
    deadline: Optional[date] = None
    owner: Optional[str] = None
    description: Optional[str] = None
    outcome_reason: Optional[str] = None

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_in_past(cls, value: date | None) -> date | None:
        return _validate_deadline_not_in_past(value)


class RfqCancelRequest(BaseModel):
    """POST /rfqs/{id}/cancel body."""
    model_config = ConfigDict(extra="forbid")

    outcome_reason: str

    @field_validator("outcome_reason")
    @classmethod
    def validate_outcome_reason_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Please provide a cancellation reason before cancelling this RFQ.")
        return normalized


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
    current_stage_id: Optional[UUID] = None
    current_stage_name: Optional[str] = None
    current_stage_order: Optional[int] = None
    current_stage_status: Optional[str] = None
    current_stage_blocker_status: Optional[str] = None
    current_stage_blocker_reason_code: Optional[str] = None
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
    source_package_available: bool = False
    source_package_updated_at: Optional[datetime] = None
    workbook_available: bool = False
    workbook_updated_at: Optional[datetime] = None
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
    avg_margin: Optional[float] = None


class RfqAnalytics(BaseModel):
    """GET /rfqs/analytics response — business analytics."""
    avg_margin_submitted: Optional[float] = None
    avg_margin_awarded: Optional[float] = None
    estimation_accuracy: Optional[float] = None
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
        current_stage_id=rfq.current_stage_id,
        current_stage_name=current_stage_name,
        current_stage_order=getattr(rfq, "current_stage_order", None),
        current_stage_status=getattr(rfq, "current_stage_status", None),
        current_stage_blocker_status=getattr(rfq, "current_stage_blocker_status", None),
        current_stage_blocker_reason_code=getattr(rfq, "current_stage_blocker_reason_code", None),
        workflow_name=workflow_name,
    )


def to_detail(
    rfq,
    current_stage_name: str = None,
    workflow_name: str = None,
    *,
    source_package_available: bool = False,
    source_package_updated_at: Optional[datetime] = None,
    workbook_available: bool = False,
    workbook_updated_at: Optional[datetime] = None,
) -> RfqDetail:
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
        source_package_available=source_package_available,
        source_package_updated_at=source_package_updated_at,
        workbook_available=workbook_available,
        workbook_updated_at=workbook_updated_at,
        outcome_reason=rfq.outcome_reason,
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def from_create_request(req: RfqCreateRequest) -> dict:
    """Pydantic request → dict for the datasource."""
    data = req.model_dump(exclude={"stage_overrides", "skip_stages", "code_prefix"})
    return data

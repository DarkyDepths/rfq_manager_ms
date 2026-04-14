"""
RFQ Stage translator — converts between Pydantic schemas and the RfqStage SQLAlchemy model.

Functions:
- to_model(schema)     — RfqStageUpdateRequest → RfqStage model instance
- to_schema(model)     — RfqStage model → RfqStage response schema
- to_detail(model)     — RfqStage model → RfqStageDetail response (with subtasks, notes, files)
- note_to_schema(model) — RfqNote model → StageNote response schema
- file_to_schema(model) — RfqFile model → StageFile response schema
"""

from uuid import UUID, uuid4
from datetime import date, datetime, timezone
from typing import Optional, List, Literal
import math

from pydantic import BaseModel, ConfigDict, model_validator


GO_NO_GO_DECISION_FIELD = "go_nogo_decision"
GO_NO_GO_VALUE_GO = "go"
GO_NO_GO_VALUE_NO_GO = "no_go"
GO_NO_GO_VALIDATION_MESSAGE = "Please choose Go or No-Go before continuing."
DESIGN_APPROVED_FIELD = "design_approved"
BOQ_COMPLETED_FIELD = "boq_completed"
AUTO_BLOCKER_SOURCE_FIELD = "workflow_auto_blocker_source"
LIFECYCLE_HISTORY_EVENTS_FIELD = "workflow_history_events"
YES_NO_VALUE_YES = "yes"
YES_NO_VALUE_NO = "no"
TERMINAL_OUTCOME_FIELD = "rfq_terminal_outcome"
TERMINAL_OUTCOME_AWARDED = "awarded"
TERMINAL_OUTCOME_LOST = "lost"
TERMINAL_OUTCOME_VALIDATION_MESSAGE = (
    "Please choose Awarded or Lost before completing this RFQ."
)
LOST_REASON_CODE_FIELD = "rfq_lost_reason_code"
LOST_REASON_OTHER_DETAIL_FIELD = "rfq_lost_reason_other"
LOST_REASON_REQUIRED_MESSAGE = (
    "Please choose a lost reason before completing this RFQ as Lost."
)
LOST_REASON_OTHER_REQUIRED_MESSAGE = (
    "Please enter the lost reason details when Other is selected."
)
ESTIMATION_COMPLETED_FIELD = "estimation_completed"
ESTIMATION_AMOUNT_FIELD = "estimation_amount"
ESTIMATION_CURRENCY_FIELD = "estimation_currency"
FINAL_PRICE_FIELD = "final_price"
FINAL_PRICE_CURRENCY_FIELD = "final_price_currency"
APPROVAL_SIGNATURE_FIELD = "approval_signature"
DEFAULT_CURRENCY_CODE = "SAR"
DESIGN_APPROVED_VALIDATION_MESSAGE = (
    "Please choose Yes or No for Design Approved before continuing."
)
BOQ_COMPLETED_VALIDATION_MESSAGE = (
    "Please choose Yes or No for BOQ Completed before continuing."
)
ESTIMATION_AMOUNT_VALIDATION_MESSAGE = (
    "Please enter a valid numeric estimation amount before continuing."
)
FINAL_PRICE_VALIDATION_MESSAGE = (
    "Please enter a valid numeric final price before continuing."
)
APPROVAL_SIGNATURE_VALIDATION_MESSAGE = (
    "Please enter the internal approval reference or sign-off code before continuing."
)
BLOCKER_REASON_REQUIRED_MESSAGE = (
    "Please choose a blocker reason when marking the stage as blocked."
)
STAGE_PROGRESS_READ_ONLY_MESSAGE = (
    "Stage progress is derived truth and cannot be updated manually from the current stage workspace."
)
GO_NO_GO_CONFIRM_CANCEL_MESSAGE = (
    "This No-Go decision requires confirmation to cancel the RFQ. "
    "Confirm the cancellation and provide a reason to continue."
)
GO_NO_GO_REASON_REQUIRED_MESSAGE = (
    "Please provide a cancellation reason for the No-Go decision."
)

CONTROLLED_YES_NO_DECISION_FIELDS = {
    DESIGN_APPROVED_FIELD: {
        "label": "Design Approved",
        "validation_message": DESIGN_APPROVED_VALIDATION_MESSAGE,
    },
    BOQ_COMPLETED_FIELD: {
        "label": "BOQ Completed",
        "validation_message": BOQ_COMPLETED_VALIDATION_MESSAGE,
    },
}

LOST_REASON_LABELS = {
    "commercial_gap": "Commercial competitiveness",
    "technical_gap": "Technical non-compliance",
    "delivery_schedule": "Delivery / schedule",
    "scope_misalignment": "Scope misalignment",
    "client_strategy_change": "Client strategy change",
    "no_feedback": "No feedback received",
    "other": "Other",
}

TRACKED_STAGE_HISTORY_FIELDS = (
    GO_NO_GO_DECISION_FIELD,
    DESIGN_APPROVED_FIELD,
    BOQ_COMPLETED_FIELD,
    TERMINAL_OUTCOME_FIELD,
    LOST_REASON_CODE_FIELD,
)

LIFECYCLE_HISTORY_EVENT_TYPES = {
    "decision_recorded",
    "blocker_created",
    "blocker_updated",
    "blocker_resolved",
    "terminal_outcome_recorded",
}

COMMERCIAL_FIELD_CONFIG = {
    ESTIMATION_COMPLETED_FIELD: {
        "amount_key": ESTIMATION_AMOUNT_FIELD,
        "currency_key": ESTIMATION_CURRENCY_FIELD,
        "validation_message": ESTIMATION_AMOUNT_VALIDATION_MESSAGE,
    },
    FINAL_PRICE_FIELD: {
        "amount_key": FINAL_PRICE_FIELD,
        "currency_key": FINAL_PRICE_CURRENCY_FIELD,
        "validation_message": FINAL_PRICE_VALIDATION_MESSAGE,
    },
}


def normalize_go_no_go_decision_value(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(GO_NO_GO_VALIDATION_MESSAGE)

    normalized = value.strip().lower().replace("—", "-")
    if not normalized:
        return None

    if normalized == "proceed" or normalized.startswith("go"):
        return GO_NO_GO_VALUE_GO

    if (
        normalized in {"no go", "no-go", "nogo", "no_go"}
        or normalized.startswith("no-go")
        or normalized.startswith("no go")
        or normalized.startswith("no_go")
    ):
        return GO_NO_GO_VALUE_NO_GO

    raise ValueError(GO_NO_GO_VALIDATION_MESSAGE)


def is_controlled_yes_no_decision_field(field_key: str) -> bool:
    return field_key in CONTROLLED_YES_NO_DECISION_FIELDS


def is_commercial_stage_field(field_key: str) -> bool:
    return field_key in COMMERCIAL_FIELD_CONFIG


def is_managed_stage_support_field(field_key: str) -> bool:
    return field_key in {
        ESTIMATION_AMOUNT_FIELD,
        ESTIMATION_CURRENCY_FIELD,
        FINAL_PRICE_CURRENCY_FIELD,
    }


def get_commercial_amount_key(field_key: str) -> str:
    return COMMERCIAL_FIELD_CONFIG[field_key]["amount_key"]


def get_commercial_currency_key(field_key: str) -> str:
    return COMMERCIAL_FIELD_CONFIG[field_key]["currency_key"]


def get_commercial_validation_message(field_key: str) -> str:
    return COMMERCIAL_FIELD_CONFIG[field_key]["validation_message"]


def normalize_yes_no_decision_value(value, *, allow_legacy_text: bool = False):
    if value is None:
        return None

    if isinstance(value, bool):
        return YES_NO_VALUE_YES if value else YES_NO_VALUE_NO

    if not isinstance(value, str):
        raise ValueError("Please choose Yes or No before continuing.")

    normalized = value.strip().lower().replace("—", "-")
    if not normalized:
        return None

    if normalized in {"yes", "y", "true"}:
        return YES_NO_VALUE_YES

    if normalized in {"no", "n", "false"}:
        return YES_NO_VALUE_NO

    if normalized.startswith("yes") or normalized.startswith("approved") or normalized.startswith("completed"):
        return YES_NO_VALUE_YES

    if (
        normalized.startswith("no")
        or normalized.startswith("not approved")
        or normalized.startswith("not completed")
    ):
        return YES_NO_VALUE_NO

    if allow_legacy_text and normalized:
        return YES_NO_VALUE_YES

    raise ValueError("Please choose Yes or No before continuing.")


def normalize_controlled_stage_decision_value(
    field_key: str,
    value,
    *,
    allow_legacy_text: bool = False,
):
    if field_key == GO_NO_GO_DECISION_FIELD:
        return normalize_go_no_go_decision_value(value)

    if is_controlled_yes_no_decision_field(field_key):
        try:
            return normalize_yes_no_decision_value(
                value,
                allow_legacy_text=allow_legacy_text,
            )
        except ValueError as exc:
            raise ValueError(get_controlled_stage_decision_validation_message(field_key)) from exc

    return value


def normalize_terminal_outcome_value(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(TERMINAL_OUTCOME_VALIDATION_MESSAGE)

    normalized = value.strip().lower().replace("—", "-")
    if not normalized:
        return None

    if normalized in {"awarded", "award", "won"}:
        return TERMINAL_OUTCOME_AWARDED

    if normalized in {"lost", "loss"}:
        return TERMINAL_OUTCOME_LOST

    raise ValueError(TERMINAL_OUTCOME_VALIDATION_MESSAGE)


def normalize_lost_reason_code(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(LOST_REASON_REQUIRED_MESSAGE)

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    if normalized in LOST_REASON_LABELS:
        return normalized

    reverse_lookup = {
        label.strip().lower().replace("/", " ").replace("-", " ").replace("  ", " "): code
        for code, label in LOST_REASON_LABELS.items()
    }
    normalized_label = normalized.replace("_", " ")
    if normalized_label in reverse_lookup:
        return reverse_lookup[normalized_label]

    raise ValueError(LOST_REASON_REQUIRED_MESSAGE)


def normalize_lost_reason_other_detail(value):
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def get_lost_reason_label(reason_code: str | None) -> str | None:
    if reason_code is None:
        return None
    return LOST_REASON_LABELS.get(reason_code)


def get_lost_reason_other_detail_from_captured_data(captured_data: dict | None) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    return normalize_lost_reason_other_detail(captured_data.get(LOST_REASON_OTHER_DETAIL_FIELD))


def normalize_auto_blocker_source_field(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("workflow_auto_blocker_source must be a controlled decision field.")

    normalized = value.strip()
    if not normalized:
        return None

    if not is_controlled_yes_no_decision_field(normalized):
        raise ValueError("workflow_auto_blocker_source must be a controlled decision field.")

    return normalized


def get_auto_blocker_source_field(captured_data: dict | None) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    try:
        return normalize_auto_blocker_source_field(captured_data.get(AUTO_BLOCKER_SOURCE_FIELD))
    except ValueError:
        return None


def get_lifecycle_history_events_from_captured_data(captured_data: dict | None) -> list[dict]:
    if not isinstance(captured_data, dict):
        return []

    value = captured_data.get(LIFECYCLE_HISTORY_EVENTS_FIELD)
    if not isinstance(value, list):
        return []

    normalized_events = []
    for event in value:
        normalized_event = normalize_lifecycle_history_event(event)
        if normalized_event is not None:
            normalized_events.append(normalized_event)

    return normalized_events


def normalize_lifecycle_history_event(event: dict | None) -> dict | None:
    if not isinstance(event, dict):
        return None

    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None

    normalized_type = event_type.strip()
    if normalized_type not in LIFECYCLE_HISTORY_EVENT_TYPES:
        return None

    normalized_event = {"type": normalized_type}

    for key in ("id", "at", "actor_name", "field_key", "value", "reason", "detail"):
        value = event.get(key)
        if not isinstance(value, str):
            continue
        normalized_value = value.strip()
        if normalized_value:
            normalized_event[key] = normalized_value

    source = event.get("source")
    if isinstance(source, str):
        normalized_source = source.strip().lower()
        if normalized_source in {"manual", "automatic"}:
            normalized_event["source"] = normalized_source

    return normalized_event


def sanitize_stage_captured_data_for_response(captured_data: dict | None) -> dict | None:
    if not isinstance(captured_data, dict):
        return captured_data

    next_captured_data = dict(captured_data)
    normalized_events = get_lifecycle_history_events_from_captured_data(next_captured_data)
    if normalized_events:
        next_captured_data[LIFECYCLE_HISTORY_EVENTS_FIELD] = normalized_events
    else:
        next_captured_data.pop(LIFECYCLE_HISTORY_EVENTS_FIELD, None)

    return next_captured_data


def normalize_stage_history_text_value(value) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalize_stage_history_blocker_status(value) -> str | None:
    return value if value in {"Blocked", "Resolved"} else None


def get_tracked_stage_history_field_value(
    captured_data: dict | None,
    field_key: str,
) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    if field_key == TERMINAL_OUTCOME_FIELD:
        return get_terminal_outcome_from_captured_data(captured_data)
    if field_key == LOST_REASON_CODE_FIELD:
        return get_lost_reason_code_from_captured_data(captured_data)
    if field_key == GO_NO_GO_DECISION_FIELD:
        try:
            return normalize_go_no_go_decision_value(captured_data.get(field_key))
        except ValueError:
            return None
    if is_controlled_yes_no_decision_field(field_key):
        try:
            return normalize_controlled_stage_decision_value(
                field_key,
                captured_data.get(field_key),
                allow_legacy_text=True,
            )
        except ValueError:
            return None

    return normalize_stage_history_text_value(captured_data.get(field_key))


def build_stage_history_event(
    event_type: str,
    *,
    actor_name: str | None = None,
    field_key: str | None = None,
    value: str | None = None,
    reason: str | None = None,
    source: str | None = None,
) -> dict:
    event = {
        "id": str(uuid4()),
        "type": event_type,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if actor_name:
        event["actor_name"] = actor_name
    if field_key:
        event["field_key"] = field_key
    if value:
        event["value"] = value
    if reason:
        event["reason"] = reason
    if source:
        event["source"] = source
    return event


def append_terminal_outcome_history_event(
    events: list[dict],
    *,
    actor_name: str | None,
    value: str,
    reason: str | None,
) -> None:
    last_event = events[-1] if events else None
    if (
        isinstance(last_event, dict)
        and last_event.get("type") == "terminal_outcome_recorded"
        and last_event.get("field_key") == TERMINAL_OUTCOME_FIELD
        and last_event.get("value") == value
        and last_event.get("reason") == reason
    ):
        return

    events.append(
        build_stage_history_event(
            "terminal_outcome_recorded",
            actor_name=actor_name,
            field_key=TERMINAL_OUTCOME_FIELD,
            value=value,
            reason=reason,
        )
    )


def get_terminal_outcome_from_captured_data(captured_data: dict | None) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    try:
        return normalize_terminal_outcome_value(captured_data.get(TERMINAL_OUTCOME_FIELD))
    except ValueError:
        return None


def get_lost_reason_code_from_captured_data(captured_data: dict | None) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    try:
        return normalize_lost_reason_code(captured_data.get(LOST_REASON_CODE_FIELD))
    except ValueError:
        return None


def normalize_terminal_outcome_stage_fields(captured_data: dict) -> dict:
    next_captured_data = dict(captured_data)
    raw_outcome = next_captured_data.get(TERMINAL_OUTCOME_FIELD)

    if raw_outcome is None:
        next_captured_data.pop(TERMINAL_OUTCOME_FIELD, None)
        next_captured_data.pop(LOST_REASON_CODE_FIELD, None)
        next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)
        return next_captured_data

    outcome = normalize_terminal_outcome_value(raw_outcome)
    if outcome is None:
        next_captured_data.pop(TERMINAL_OUTCOME_FIELD, None)
        next_captured_data.pop(LOST_REASON_CODE_FIELD, None)
        next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)
        return next_captured_data

    next_captured_data[TERMINAL_OUTCOME_FIELD] = outcome

    if outcome == TERMINAL_OUTCOME_LOST:
        reason_code = normalize_lost_reason_code(
            next_captured_data.get(LOST_REASON_CODE_FIELD)
        )
        if reason_code is None:
            next_captured_data.pop(LOST_REASON_CODE_FIELD, None)
            next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)
        else:
            next_captured_data[LOST_REASON_CODE_FIELD] = reason_code
            if reason_code == "other":
                other_detail = normalize_lost_reason_other_detail(
                    next_captured_data.get(LOST_REASON_OTHER_DETAIL_FIELD)
                )
                if other_detail is None:
                    next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)
                else:
                    next_captured_data[LOST_REASON_OTHER_DETAIL_FIELD] = other_detail
            else:
                next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)
    else:
        next_captured_data.pop(LOST_REASON_CODE_FIELD, None)
        next_captured_data.pop(LOST_REASON_OTHER_DETAIL_FIELD, None)

    return next_captured_data


def build_terminal_outcome_reason(
    outcome: str,
    *,
    lost_reason_code: str | None = None,
    lost_reason_other_detail: str | None = None,
    outcome_detail: str | None = None,
) -> str | None:
    normalized_detail = outcome_detail.strip() if isinstance(outcome_detail, str) else None
    detail = normalized_detail or None
    other_detail = normalize_lost_reason_other_detail(lost_reason_other_detail)

    if outcome == TERMINAL_OUTCOME_LOST:
        label = get_lost_reason_label(lost_reason_code)
        if lost_reason_code == "other":
            if other_detail and detail:
                return f"Other: {other_detail} ({detail})"
            if other_detail:
                return f"Other: {other_detail}"
        if label and detail:
            return f"{label}: {detail}"
        return label or detail or other_detail

    return detail


def normalize_currency_code(value) -> str:
    if value is None:
        return DEFAULT_CURRENCY_CODE

    if not isinstance(value, str):
        raise ValueError("Please choose a valid currency code.")

    normalized = value.strip().upper()
    if not normalized:
        return DEFAULT_CURRENCY_CODE

    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Please choose a valid currency code.")

    return normalized


def normalize_numeric_amount(value, *, validation_message: str):
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(validation_message)

    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        try:
            numeric = float(normalized)
        except ValueError as exc:
            raise ValueError(validation_message) from exc
    else:
        raise ValueError(validation_message)

    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(validation_message)

    return numeric


def normalize_commercial_stage_fields(captured_data: dict) -> dict:
    next_captured_data = dict(captured_data)

    for field_key in COMMERCIAL_FIELD_CONFIG:
        amount_key = get_commercial_amount_key(field_key)
        currency_key = get_commercial_currency_key(field_key)

        should_normalize = any(
            key in next_captured_data for key in {field_key, amount_key, currency_key}
        )
        if not should_normalize:
            continue

        amount = normalize_numeric_amount(
            next_captured_data.get(amount_key),
            validation_message=get_commercial_validation_message(field_key),
        )

        if amount is None:
            if amount_key != field_key:
                next_captured_data.pop(amount_key, None)
            next_captured_data.pop(currency_key, None)
            if field_key == ESTIMATION_COMPLETED_FIELD:
                next_captured_data.pop(field_key, None)
            else:
                next_captured_data.pop(field_key, None)
            continue

        next_captured_data[amount_key] = amount
        next_captured_data[currency_key] = normalize_currency_code(
            next_captured_data.get(currency_key)
        )

        if field_key == ESTIMATION_COMPLETED_FIELD:
            next_captured_data[field_key] = True
        else:
            next_captured_data[field_key] = amount

    return next_captured_data


def normalize_approval_signature_value(value):
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(APPROVAL_SIGNATURE_VALIDATION_MESSAGE)

    normalized = str(value).strip()
    return normalized or None


def normalize_stage_captured_data(captured_data: dict) -> dict:
    next_captured_data = dict(captured_data)

    next_captured_data.pop(LIFECYCLE_HISTORY_EVENTS_FIELD, None)

    for field_key in list(next_captured_data.keys()):
        if (
            field_key != GO_NO_GO_DECISION_FIELD
            and not is_controlled_yes_no_decision_field(field_key)
        ):
            continue

        normalized_decision = normalize_controlled_stage_decision_value(
            field_key,
            next_captured_data.get(field_key),
        )
        if normalized_decision is None:
            next_captured_data.pop(field_key, None)
        else:
            next_captured_data[field_key] = normalized_decision

    next_captured_data = normalize_commercial_stage_fields(next_captured_data)

    if APPROVAL_SIGNATURE_FIELD in next_captured_data:
        normalized_signature = normalize_approval_signature_value(
            next_captured_data.get(APPROVAL_SIGNATURE_FIELD)
        )
        if normalized_signature is None:
            next_captured_data.pop(APPROVAL_SIGNATURE_FIELD, None)
        else:
            next_captured_data[APPROVAL_SIGNATURE_FIELD] = normalized_signature

    next_captured_data = normalize_terminal_outcome_stage_fields(next_captured_data)

    if AUTO_BLOCKER_SOURCE_FIELD in next_captured_data:
        auto_blocker_source = normalize_auto_blocker_source_field(
            next_captured_data.get(AUTO_BLOCKER_SOURCE_FIELD)
        )
        if auto_blocker_source is None:
            next_captured_data.pop(AUTO_BLOCKER_SOURCE_FIELD, None)
        else:
            next_captured_data[AUTO_BLOCKER_SOURCE_FIELD] = auto_blocker_source

    return next_captured_data


def get_commercial_amount_value(captured_data: dict | None, field_key: str):
    if not isinstance(captured_data, dict):
        return None

    amount_key = get_commercial_amount_key(field_key)
    try:
        return normalize_numeric_amount(
            captured_data.get(amount_key),
            validation_message=get_commercial_validation_message(field_key),
        )
    except ValueError:
        return None


def get_stage_field_validation_message(field_key: str) -> str | None:
    decision_message = get_controlled_stage_decision_validation_message(field_key)
    if decision_message:
        return decision_message

    if is_commercial_stage_field(field_key):
        return get_commercial_validation_message(field_key)

    if field_key == APPROVAL_SIGNATURE_FIELD:
        return APPROVAL_SIGNATURE_VALIDATION_MESSAGE

    return None


def get_controlled_stage_decision_validation_message(field_key: str) -> str | None:
    if field_key == GO_NO_GO_DECISION_FIELD:
        return GO_NO_GO_VALIDATION_MESSAGE

    config = CONTROLLED_YES_NO_DECISION_FIELDS.get(field_key)
    if config:
        return config["validation_message"]

    return None


def get_negative_decision_blocker_reason_message(field_key: str) -> str:
    if field_key == DESIGN_APPROVED_FIELD:
        return "Please choose a blocker reason when Design Approved is set to No."

    if field_key == BOQ_COMPLETED_FIELD:
        return "Please choose a blocker reason when BOQ Completed is set to No."

    return BLOCKER_REASON_REQUIRED_MESSAGE


def find_negative_blocking_decision(
    mandatory_fields: str | None,
    captured_data: dict | None,
) -> str | None:
    if not mandatory_fields or not isinstance(captured_data, dict):
        return None

    required = [field.strip() for field in mandatory_fields.split(",") if field.strip()]
    for field in required:
        if not is_controlled_yes_no_decision_field(field):
            continue

        try:
            decision = normalize_controlled_stage_decision_value(
                field,
                captured_data.get(field),
                allow_legacy_text=True,
            )
        except ValueError:
            continue

        if decision == YES_NO_VALUE_NO:
            return field

    return None


def find_negative_update_decision_field(captured_data: dict | None) -> str | None:
    if not isinstance(captured_data, dict):
        return None

    for field_key in CONTROLLED_YES_NO_DECISION_FIELDS:
        try:
            decision = normalize_controlled_stage_decision_value(
                field_key,
                captured_data.get(field_key),
            )
        except ValueError:
            continue

        if decision == YES_NO_VALUE_NO:
            return field_key

    return None


# ═══════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════

class RfqStageUpdateRequest(BaseModel):
    progress: Optional[int] = None
    captured_data: Optional[dict] = None
    blocker_status: Optional[Literal["Blocked", "Resolved"]] = None
    blocker_reason_code: Optional[str] = None

    @model_validator(mode="after")
    def validate_blocker_fields(self):
        if self.progress is not None:
            raise ValueError(STAGE_PROGRESS_READ_ONLY_MESSAGE)

        normalized_reason = self.blocker_reason_code.strip() if isinstance(self.blocker_reason_code, str) else None
        self.blocker_reason_code = normalized_reason or None

        if isinstance(self.captured_data, dict):
            self.captured_data = normalize_stage_captured_data(self.captured_data)

        terminal_outcome = get_terminal_outcome_from_captured_data(self.captured_data)
        if terminal_outcome == TERMINAL_OUTCOME_LOST:
            lost_reason_code = get_lost_reason_code_from_captured_data(self.captured_data)
            if not lost_reason_code:
                raise ValueError(LOST_REASON_REQUIRED_MESSAGE)
            if (
                lost_reason_code == "other"
                and not get_lost_reason_other_detail_from_captured_data(self.captured_data)
            ):
                raise ValueError(LOST_REASON_OTHER_REQUIRED_MESSAGE)

        negative_update_decision_field = find_negative_update_decision_field(self.captured_data)
        if negative_update_decision_field:
            if not self.blocker_reason_code:
                raise ValueError(
                    get_negative_decision_blocker_reason_message(
                        negative_update_decision_field
                    )
                )
            self.blocker_status = "Blocked"

        if self.blocker_status == "Blocked" and not self.blocker_reason_code:
            raise ValueError(BLOCKER_REASON_REQUIRED_MESSAGE)

        if self.blocker_reason_code and self.blocker_status not in {"Blocked", "Resolved"}:
            raise ValueError("blocker_reason_code requires blocker_status")

        if self.blocker_status != "Blocked":
            self.blocker_reason_code = None

        return self


class RfqStageAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_no_go_cancel: bool = False
    terminal_outcome: Optional[str] = None
    lost_reason_code: Optional[str] = None
    outcome_reason: Optional[str] = None

    @model_validator(mode="after")
    def normalize_reason(self):
        self.terminal_outcome = normalize_terminal_outcome_value(self.terminal_outcome)
        self.lost_reason_code = normalize_lost_reason_code(self.lost_reason_code)
        normalized_reason = self.outcome_reason.strip() if isinstance(self.outcome_reason, str) else None
        self.outcome_reason = normalized_reason or None
        if self.terminal_outcome != TERMINAL_OUTCOME_LOST:
            self.lost_reason_code = None
        elif not self.lost_reason_code:
            raise ValueError(LOST_REASON_REQUIRED_MESSAGE)
        return self

class NoteCreateRequest(BaseModel):
    text: str


# ═══════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════

class StageNoteResponse(BaseModel):
    id: UUID
    user_name: str
    text: str
    created_at: datetime
    class Config:
        from_attributes = True

class StageFileResponse(BaseModel):
    id: UUID
    filename: str
    download_url: str
    storage_reference: Optional[str] = None
    type: str
    uploaded_by: str
    size_bytes: Optional[int] = None
    uploaded_at: datetime
    class Config:
        from_attributes = True

class SubtaskBrief(BaseModel):
    id: UUID
    name: str
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    progress: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class RfqStageResponse(BaseModel):
    id: UUID
    name: str
    order: int
    assigned_team: Optional[str] = None
    status: str
    progress: int
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    blocker_status: Optional[str] = None
    blocker_reason_code: Optional[str] = None
    class Config:
        from_attributes = True

class RfqStageListResponse(BaseModel):
    data: List[RfqStageResponse]
    class Config:
        from_attributes = True

class RfqStageDetailResponse(RfqStageResponse):
    captured_data: Optional[dict] = None
    mandatory_fields: Optional[str] = None
    notes: List[StageNoteResponse] = []
    files: List[StageFileResponse] = []
    subtasks: List[SubtaskBrief] = []


# ═══════════════════════════════════════════════════
# CONVERSION FUNCTIONS
# ═══════════════════════════════════════════════════

def to_response(stage) -> RfqStageResponse:
    blocker_status = _normalize_blocker_status(stage.blocker_status)
    return RfqStageResponse(
        id=stage.id,
        name=stage.name,
        order=stage.order,
        assigned_team=stage.assigned_team,
        status=stage.status,
        progress=stage.progress,
        planned_start=stage.planned_start,
        planned_end=stage.planned_end,
        actual_start=stage.actual_start,
        actual_end=stage.actual_end,
        blocker_status=blocker_status,
        blocker_reason_code=_normalize_blocker_reason(blocker_status, stage.blocker_reason_code),
    )

def to_detail(stage, notes=None, files=None, subtasks=None) -> RfqStageDetailResponse:
    blocker_status = _normalize_blocker_status(stage.blocker_status)
    return RfqStageDetailResponse(
        id=stage.id,
        name=stage.name,
        order=stage.order,
        assigned_team=stage.assigned_team,
        status=stage.status,
        progress=stage.progress,
        planned_start=stage.planned_start,
        planned_end=stage.planned_end,
        actual_start=stage.actual_start,
        actual_end=stage.actual_end,
        blocker_status=blocker_status,
        blocker_reason_code=_normalize_blocker_reason(blocker_status, stage.blocker_reason_code),
        captured_data=sanitize_stage_captured_data_for_response(stage.captured_data),
        mandatory_fields=stage.mandatory_fields,
        notes=[StageNoteResponse.model_validate(n) for n in (notes or [])],
        files=[file_to_schema(f) for f in (files or [])],
        subtasks=[SubtaskBrief.model_validate(s) for s in (subtasks or [])],
    )


def _normalize_blocker_status(value: Optional[str]) -> Optional[str]:
    return value if value in {"Blocked", "Resolved"} else None


def _normalize_blocker_reason(
    blocker_status: Optional[str],
    blocker_reason_code: Optional[str],
) -> Optional[str]:
    normalized_reason = blocker_reason_code.strip() if isinstance(blocker_reason_code, str) else None
    if blocker_status not in {"Blocked", "Resolved"} or not normalized_reason:
        return None
    return normalized_reason


def file_to_schema(file) -> StageFileResponse:
    return StageFileResponse(
        id=file.id,
        filename=file.filename,
        download_url=f"/rfq-manager/v1/files/{file.id}/download",
        storage_reference=file.file_path,
        type=file.type,
        uploaded_by=file.uploaded_by,
        size_bytes=file.size_bytes,
        uploaded_at=file.uploaded_at,
    )

import logging
import re
from contextvars import ContextVar
from uuid import uuid4

from prometheus_client import Counter, Histogram


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

HTTP_REQUESTS_TOTAL = Counter(
    "rfq_manager_http_requests_total",
    "Total HTTP requests processed by the API",
    ["method", "route", "status_class"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "rfq_manager_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
)


def get_request_id() -> str:
    return request_id_context.get()


def resolve_request_id(
    incoming_request_id: str | None,
    incoming_correlation_id: str | None,
) -> str:
    candidate = (incoming_request_id or "").strip() or (incoming_correlation_id or "").strip()
    if candidate and _VALID_REQUEST_ID.match(candidate):
        return candidate
    return str(uuid4())


def route_label_from_request(request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return route_path
    return "unmatched"


def configure_request_id_logging() -> None:
    if getattr(configure_request_id_logging, "_configured", False):
        return

    base_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = base_factory(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return record

    logging.setLogRecordFactory(record_factory)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s",
        )

    configure_request_id_logging._configured = True
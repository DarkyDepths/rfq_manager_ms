"""
FastAPI application factory.

Creates the FastAPI app instance with:
- CORS middleware configuration
- Exception handlers (custom error classes → JSON responses)
- Route registration for all 6 resource routers (rfq, workflow, rfq_stage, subtask, reminder, file)
- Health-check endpoint at /health
- OpenAPI metadata (title, version, description)

Entry point: `create_app()` returns the configured FastAPI instance.
Run with: `uvicorn src.app:app --reload`
"""
import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from fastapi import APIRouter

from src.config.settings import settings
from src.utils.errors import AppError
from src.utils.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    configure_request_id_logging,
    get_request_id,
    request_id_context,
    resolve_request_id,
    route_label_from_request,
)


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    App factory pattern.

    Why a function instead of just `app = FastAPI()`?
    Because tests can call create_app() with a different config
    (e.g. test database) without affecting the real app.
    """

    app = FastAPI(
        title="rfq_manager_ms",
        version="1.0.0",
        description="RFQ Lifecycle Management API — Gulf Heavy Industries",
    )

    configure_request_id_logging()

    # ── CORS Middleware ────────────────────────────────
    # When your frontend (localhost:3000) calls your API (localhost:8000),
    # the browser blocks it by default (security). CORS tells the browser
    # "it's okay, allow requests from these origins."
    #
    # In dev: CORS_ORIGINS = "*" (allow everything)
    # In production: CORS_ORIGINS = "https://ghi-portal.com,https://admin.ghi.com"
    origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],       # GET, POST, PATCH, DELETE, etc.
        allow_headers=["*"],       # Authorization, Content-Type, etc.
    )

    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        request_id = resolve_request_id(
            request.headers.get("X-Request-ID"),
            request.headers.get("X-Correlation-ID"),
        )
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        response = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_seconds = time.perf_counter() - started_at
            route_label = route_label_from_request(request)
            status_class = f"{status_code // 100}xx"

            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                route=route_label,
                status_class=status_class,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                route=route_label,
            ).observe(duration_seconds)

            logger.info(
                "request_complete method=%s path=%s status_code=%s duration_ms=%.2f request_id=%s",
                request.method,
                request.url.path,
                status_code,
                duration_seconds * 1000,
                request_id,
            )
            request_id_context.reset(token)

    @app.on_event("startup")
    async def log_auth_mode():
        if settings.AUTH_BYPASS_ENABLED:
            logger.warning("Auth bypass enabled for local/dev mode only.")
            if settings.AUTH_BYPASS_DEBUG_HEADERS_ENABLED:
                logger.warning("X-Debug-* auth header overrides enabled for local/dev bypass mode.")
        else:
            logger.info("Auth enforcement enabled via IAM bearer token resolution.")

    # ── Global Exception Handler ──────────────────────
    # Catches any AppError (NotFoundError, BadRequestError, etc.)
    # and converts it to a clean JSON response.
    #
    # Without this, you'd write raise HTTPException(status_code=404, ...)
    # in every route. With this, controllers just raise NotFoundError("...")
    # and the handler takes care of the HTTP part.
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError):
        request_id = getattr(request.state, "request_id", get_request_id())
        return JSONResponse(
            status_code=error.status_code,
            content={"error": error.__class__.__name__, "message": error.message, "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    # ── Validation Error Handler ──────────────────────
    # Catch Pydantic/FastAPI validation errors and format
    # them to match the AppError shape
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", get_request_id())
        error_msgs = []
        for err in exc.errors():
            loc = ".".join([str(x) for x in err["loc"]])
            msg = err["msg"]
            error_msgs.append(f"{loc}: {msg}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "UnprocessableEntityError",
                "message": "Validation failed: " + " | ".join(error_msgs),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", get_request_id())
        logger.exception("Unhandled exception during request request_id=%s", request_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    # ── Health Check ──────────────────────────────────
    # The simplest possible endpoint. If this responds,
    # the server is alive. Used by monitoring tools,
    # load balancers, and you during development.
    @app.get("/health", include_in_schema=False)
    def health_check():
        """#31 — Health check."""
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ── Route Registration ────────────────────────────
    # All API routes live under /rfq-manager/v1 (matches OpenAPI spec servers.url)
    from src.routes.rfq_route import router as rfq_router
    from src.routes.workflow_route import router as workflow_router
    from src.routes.rfq_stage_route import router as rfq_stage_router
    from src.routes.subtask_route import router as subtask_router
    from src.routes.file_route import stage_files_router, file_router
    from src.routes.reminder_route import router as reminder_router

    v1 = APIRouter(prefix="/rfq-manager/v1")
    v1.include_router(rfq_router)
    v1.include_router(workflow_router)
    v1.include_router(rfq_stage_router)
    v1.include_router(subtask_router)
    v1.include_router(stage_files_router)
    v1.include_router(file_router)
    v1.include_router(reminder_router)

    app.include_router(v1)

    return app


# ── Module-level app instance ─────────────────────────
# uvicorn looks for this: uvicorn src.app:app --reload
app = create_app()

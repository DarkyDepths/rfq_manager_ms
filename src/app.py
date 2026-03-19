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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from fastapi import APIRouter

from src.config.settings import settings
from src.utils.errors import AppError


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

    # ── V1 Auth Bypass (explicit, config-controlled) ─────────────
    # V1 runs with open endpoints while rfq_iam_ms integration is pending.
    # This middleware injects a deterministic demo user context for internal use.
    @app.middleware("http")
    async def inject_v1_auth_context(request: Request, call_next):
        if settings.AUTH_BYPASS_ENABLED:
            request.state.user = {
                "id": settings.AUTH_BYPASS_USER_ID,
                "name": settings.AUTH_BYPASS_USER_NAME,
                "team": settings.AUTH_BYPASS_TEAM,
            }
        return await call_next(request)

    @app.on_event("startup")
    async def log_v1_auth_mode():
        if settings.AUTH_BYPASS_ENABLED:
            logger.warning("V1: auth bypassed, see rfq_iam_ms integration plan.")

    # ── Global Exception Handler ──────────────────────
    # Catches any AppError (NotFoundError, BadRequestError, etc.)
    # and converts it to a clean JSON response.
    #
    # Without this, you'd write raise HTTPException(status_code=404, ...)
    # in every route. With this, controllers just raise NotFoundError("...")
    # and the handler takes care of the HTTP part.
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError):
        return JSONResponse(
            status_code=error.status_code,
            content={"error": error.__class__.__name__, "message": error.message},
        )

    # ── Validation Error Handler ──────────────────────
    # Catch Pydantic/FastAPI validation errors and format
    # them to match the AppError shape
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_msgs = []
        for err in exc.errors():
            loc = ".".join([str(x) for x in err["loc"]])
            msg = err["msg"]
            error_msgs.append(f"{loc}: {msg}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "UnprocessableEntityError",
                "message": "Validation failed: " + " | ".join(error_msgs)
            },
        )

    # ── Health Check ──────────────────────────────────
    # The simplest possible endpoint. If this responds,
    # the server is alive. Used by monitoring tools,
    # load balancers, and you during development.
    @app.get("/health")
    def health_check():
        """#31 — Health check."""
        return {"status": "ok"}

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

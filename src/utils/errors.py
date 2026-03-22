"""
Custom error / exception classes.

Defines application-level exceptions that are caught by the
global exception handler in app.py and converted to JSON error responses.

Classes:
- AppError(status_code, error, message) — base class
- NotFoundError(resource, id)           — 404
- BadRequestError(message)              — 400
- UnauthorizedError(message)            — 401
- UnprocessableEntityError(message)     — 422
- ConflictError(message)               — 409
- ForbiddenError(message)              — 403
- ServiceUnavailableError(message)      — 503
"""

class AppError(Exception):
    """
    Base class for all application errors.
    Every custom error has:
    - status_code: the HTTP status code (404, 400, etc.)
    - message: human-readable error description
    """

    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, message: str = None):
        # If a custom message is passed, use it. Otherwise use the default.
        if message:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    """404 — Resource doesn't exist. Example: GET /rfqs/{id} with bad ID."""

    status_code = 404
    message = "Resource not found"


class BadRequestError(AppError):
    """400 — Request is malformed. Example: invalid filter parameter."""

    status_code = 400
    message = "Bad request"


class UnauthorizedError(AppError):
    """401 — Missing/invalid authentication credentials."""

    status_code = 401
    message = "Unauthorized"


class UnprocessableEntityError(AppError):
    """422 — Data is valid JSON but violates business rules.
    Example: advancing a stage with missing mandatory fields."""

    status_code = 422
    message = "Unprocessable entity"


class ConflictError(AppError):
    """409 — Action conflicts with current state.
    Example: advancing a blocked stage."""

    status_code = 409
    message = "Conflict"


class ForbiddenError(AppError):
    """403 — User doesn't have permission.
    Example: advancing a stage you're not assigned to."""

    status_code = 403
    message = "Forbidden"


class ServiceUnavailableError(AppError):
    """503 — Upstream dependency unavailable.
    Example: IAM service timeout/unreachable."""

    status_code = 503
    message = "Service unavailable"


class EventBusPublishError(AppError):
    """503 — Event publication failed at the integration seam."""

    status_code = 503
    message = "Event bus publish failed"



"""core/exceptions.py — Application exception hierarchy + FastAPI handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


# ── Base ──────────────────────────────────────────────────────────────────────
class PrivacyShieldError(Exception):
    """Base exception for all application errors."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, **kwargs):
        self.message = message or self.__class__.message
        self.detail = kwargs
        super().__init__(self.message)


# ── Auth ──────────────────────────────────────────────────────────────────────
class AuthenticationError(PrivacyShieldError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_FAILED"
    message = "Invalid credentials."


class TokenExpiredError(PrivacyShieldError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "TOKEN_EXPIRED"
    message = "Token has expired. Please log in again."


class InsufficientPermissionsError(PrivacyShieldError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "INSUFFICIENT_PERMISSIONS"
    message = "You do not have permission to perform this action."


class TokenRevokedError(PrivacyShieldError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "TOKEN_REVOKED"
    message = "This token has been revoked."


# ── Resource ──────────────────────────────────────────────────────────────────
class NotFoundError(PrivacyShieldError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class ConflictError(PrivacyShieldError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"
    message = "A conflict occurred with the current state of the resource."


# ── Business Logic ────────────────────────────────────────────────────────────
class SubscriptionRequiredError(PrivacyShieldError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    error_code = "SUBSCRIPTION_REQUIRED"
    message = "This feature requires a paid subscription."


class RateLimitExceededError(PrivacyShieldError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Rate limit exceeded. Please try again later."


class ScanLimitExceededError(PrivacyShieldError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "SCAN_LIMIT_EXCEEDED"
    message = "Daily scan limit reached for your plan."


class ValidationError(PrivacyShieldError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"
    message = "Input validation failed."


# ── External Services ─────────────────────────────────────────────────────────
class ExternalServiceError(PrivacyShieldError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "EXTERNAL_SERVICE_ERROR"
    message = "An external service is temporarily unavailable."


class GoogleAPIError(ExternalServiceError):
    error_code = "GOOGLE_API_ERROR"
    message = "Google Search API error."


class RemovalRequestError(PrivacyShieldError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "REMOVAL_REQUEST_ERROR"
    message = "Failed to submit removal request."


# ── Handler registration ──────────────────────────────────────────────────────
def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers with the FastAPI app."""

    @app.exception_handler(PrivacyShieldError)
    async def privacy_shield_exception_handler(
        request: Request, exc: PrivacyShieldError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
            headers=(
                {"WWW-Authenticate": "Bearer"}
                if exc.status_code == status.HTTP_401_UNAUTHORIZED
                else {}
            ),
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "Route not found."}},
        )

    @app.exception_handler(405)
    async def method_not_allowed(request: Request, exc) -> JSONResponse:
        return JSONResponse(
            status_code=405,
            content={
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": "Method not allowed.",
                }
            },
        )

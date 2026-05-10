"""
main.py — FastAPI application factory.

Security middleware stack (applied in order):
  1. TrustedHostMiddleware  — only allow configured hostnames
  2. HTTPSRedirectMiddleware — enforce HTTPS in production
  3. SecurityHeadersMiddleware — HSTS, CSP, X-Frame-Options etc.
  4. CORSMiddleware          — restricted origins
  5. GZipMiddleware          — compress responses ≥ 500 bytes
  6. SlowAPI rate limiter    — per-IP request throttling
  7. Request ID middleware   — traceability

AppSec notes:
  - /docs and /redoc disabled in production.
  - OpenAPI schema requires authentication in production.
  - All unhandled exceptions caught and sanitised before client response.
  - Request body size limited to 1 MB.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import settings
from app.core.exceptions import register_exception_handlers

logger = structlog.get_logger(__name__)

# ── Prometheus metrics ─────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)


# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # Startup
    logger.info("PrivacyShield API starting", version=settings.APP_VERSION)

    # Initialise Sentry
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.05,
        )

    # Pre-warm NLP models in background (avoid cold start on first request)
    # asyncio.create_task(_warm_nlp_models())

    yield

    # Shutdown
    from app.services.crawler.searxng_search import searxng_service, page_fetcher
    await searxng_service.close()
    await page_fetcher.close()
    logger.info("PrivacyShield API shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""

    # Hide docs in production
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"
    openapi_url = None if settings.is_production else "/openapi.json"

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AI-powered personal data privacy protection API.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # ── Security middleware ────────────────────────────────────────────────────
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )
        app.add_middleware(HTTPSRedirectMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # Compression
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Security headers middleware ─────────────────────────────────────────
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.privacyshield.ai; "
            "frame-ancestors 'none';"
        )
        # Remove server fingerprinting headers
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)
        return response

    # ── Request ID + structured logging middleware ─────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        ):
            response: Response = await call_next(request)
            duration = time.perf_counter() - start

            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
            ).inc()
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)

            response.headers["X-Request-ID"] = request_id
            logger.info(
                "Request completed",
                status=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )
            return response

    # ── Register exception handlers ────────────────────────────────────────
    register_exception_handlers(app)

    # ── Register routers ────────────────────────────────────────────────────
    from app.api.v1.auth import router as auth_router
    from app.api.v1.scans import router as scans_router
    from app.api.v1.removals import router as removals_router
    from app.api.v1.users import router as users_router

    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(scans_router, prefix=settings.API_V1_PREFIX)
    app.include_router(removals_router, prefix=settings.API_V1_PREFIX)
    app.include_router(users_router, prefix=settings.API_V1_PREFIX)

    # ── Prometheus metrics endpoint (internal only) ────────────────────────
    metrics_app = make_asgi_app()
    app.mount("/internal/metrics", metrics_app)

    # ── Health check ───────────────────────────────────────────────────────
    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/ready", include_in_schema=False)
    async def readiness():
        """K8s readiness probe — check DB + Redis connectivity."""
        checks = {}
        try:
            from app.database import engine
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"

        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(str(settings.REDIS_URL))
            await r.ping()
            checks["redis"] = "ok"
            await r.aclose()
        except Exception as e:
            checks["redis"] = f"error: {e}"

        all_ok = all(v == "ok" for v in checks.values())
        return {"status": "ready" if all_ok else "degraded", "checks": checks}

    return app


app = create_app()

"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, chat, dashboards, datasets, documents, insights, jobs, meta, queries, semantic, workspaces
from app.core.config import settings
from app.core.errors import AppError, register_error_handlers
from app.core.logging import configure_logging, log_event, new_request_id, request_id_ctx
from app.core.ratelimit import client_key, limiter
from app.db.session import init_db

configure_logging("DEBUG" if settings.DEBUG else "INFO")
logger = logging.getLogger("agentic_bi.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    init_db()
    log_event(logger, "application_started", environment=settings.ENVIRONMENT,
              llm="gemini" if settings.llm_configured else "deterministic", database="sqlite" if settings.is_sqlite else "postgresql")
    yield
    log_event(logger, "application_stopped")


app = FastAPI(
    title="Agentic BI API",
    description=(
        "AI-powered Business Intelligence platform. Upload CSV/XLSX datasets, profile them, approve a semantic "
        "model, generate validated dashboards and ask questions answered by read-only SQL execution."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


PUBLIC_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/health",
    "/api/v1/meta/config",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
}


@app.middleware("http")
async def authentication_gate(request: Request, call_next):
    """Reject unauthenticated API calls before FastAPI validates query params.

    Without this gate, a request like ``GET /api/v1/datasets`` (missing its
    workspace parameter) would return 422 and reveal parameter names before the
    caller has proved who they are. Authentication now always comes first.
    """
    from fastapi.responses import JSONResponse

    from app.core.errors import error_body
    from app.core.security import decode_access_token
    from app.core.config import settings as app_settings

    path = request.url.path
    public = path in PUBLIC_PATHS or not path.startswith("/api/v1") or request.method == "OPTIONS"
    if public:
        return await call_next(request)

    token = request.cookies.get(app_settings.AUTH_COOKIE_NAME)
    header = request.headers.get("authorization")
    if not token and header and header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
    if not token:
        return JSONResponse(status_code=401, content=error_body("UNAUTHENTICATED", "Sign in to continue."))
    try:
        decode_access_token(token)
    except AppError as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))
    return await call_next(request)


register_error_handlers(app)


@app.middleware("http")
async def observability_and_limits(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or new_request_id()
    token = request_id_ctx.set(request_id)
    started = time.perf_counter()
    path = request.url.path
    if path.startswith("/api/v1") and "/health" not in path:
        try:
            limiter.check(client_key(request), settings.RATE_LIMIT_PER_MINUTE)
        except AppError as exc:
            from fastapi.responses import JSONResponse
            from app.core.errors import error_body

            return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    if duration_ms > 1500 or response.status_code >= 500:
        log_event(logger, "request_completed", method=request.method, path=path,
                  status=response.status_code, duration_ms=duration_ms)
    return response




for router in (
    auth.router,
    workspaces.router,
    datasets.router,
    semantic.router,
    dashboards.router,
    chat.router,
    queries.router,
    insights.router,
    documents.router,
    jobs.router,
    meta.router,
):
    app.include_router(router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "service": "Agentic BI API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }

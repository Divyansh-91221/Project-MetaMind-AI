"""FastAPI application entrypoint.

Owns only cross-cutting wiring: lifespan, middleware, exception handlers and router
registration. No business logic.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import settings
from app.core.constants import REQUEST_ID_HEADER
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger, set_request_context
from app.db.session import check_database, dispose_engine
from app.graph.neo4j_client import get_graph_store
from app.ingestion.scheduler import scheduler
from app.schemas.common import HealthStatus
from app.utils.timestamps import utcnow

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start and stop long-lived resources."""
    logger.info("application_starting", extra={"version": __version__, "env": settings.app_env})

    graph = get_graph_store()
    try:
        await graph.connect()
    except Exception as exc:  # noqa: BLE001 - the API still serves catalog endpoints
        logger.warning("graph_unavailable_at_startup", extra={"error": str(exc)})

    if not await check_database():
        logger.error("postgres_unavailable_at_startup")

    await scheduler.start()
    yield

    await scheduler.stop()
    await graph.close()
    await dispose_engine()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "AI-native enterprise metadata intelligence platform: discovery, catalog, lineage, "
        "impact analysis, governance and a tool-based metadata Copilot."
    ),
    docs_url=settings.docs_url,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    """Attach a correlation id and log request timing."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    set_request_context(request_id=request_id)
    started = time.perf_counter()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health", response_model=HealthStatus, tags=["system"], summary="Liveness and readiness")
async def health() -> HealthStatus:
    """Reports dependency health without failing the request."""
    postgres_ok = await check_database()
    graph_ok = await get_graph_store().health_check()
    return HealthStatus(
        status="ok" if postgres_ok else "degraded",
        version=__version__,
        environment=settings.app_env,
        postgres=postgres_ok,
        graph=graph_ok,
        checked_at=utcnow(),
    )


@app.get("/", tags=["system"], summary="Service metadata")
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": __version__,
        "docs": settings.docs_url or "disabled",
        "api": settings.api_v1_prefix,
    }

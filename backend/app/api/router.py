"""API router assembly.

Router ordering matters: routers with ``{path:path}`` catch-all parameters are registered
after the ones with fixed sub-paths within each module, and modules with literal prefixes come
first here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    connectors,
    copilot,
    glossary,
    governance,
    impact,
    lineage,
    metadata,
    quality,
    search,
)
from app.core.config import settings

api_router = APIRouter(prefix=settings.api_v1_prefix)

api_router.include_router(connectors.router)
api_router.include_router(search.router)
api_router.include_router(copilot.router)
api_router.include_router(glossary.router)
api_router.include_router(governance.router)
api_router.include_router(quality.router)
api_router.include_router(metadata.router)
api_router.include_router(lineage.router)
api_router.include_router(impact.router)

__all__ = ["api_router"]

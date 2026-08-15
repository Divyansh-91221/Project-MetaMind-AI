"""FastAPI dependencies.

Keeps routes declarative: authentication, session management and service construction all
happen here, so handlers stay thin.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.logging import set_request_context
from app.core.security import Permission, Principal, anonymous_principal, decode_token
from app.db.session import get_session
from app.graph.base import GraphStore
from app.graph.neo4j_client import get_graph_store

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped transactional session."""
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Principal:
    """Resolve the caller.

    With ``AUTH_ENABLED=false`` a local developer principal is returned so the stack runs
    without an identity provider. Turning authentication on requires no route changes.
    """
    if not settings.auth_enabled:
        principal = anonymous_principal()
    else:
        if credentials is None or not credentials.credentials:
            raise AuthenticationError("A bearer token is required.")
        principal = decode_token(credentials.credentials)

    set_request_context(principal=principal.subject)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_permission(permission: Permission):  # type: ignore[no-untyped-def]
    """Dependency factory enforcing a single RBAC permission."""

    async def _dependency(principal: CurrentPrincipal) -> Principal:
        principal.require(permission)
        return principal

    return _dependency


def get_graph() -> GraphStore:
    """Process-wide graph store."""
    return get_graph_store()


GraphDep = Annotated[GraphStore, Depends(get_graph)]


class PaginationQuery:
    """Reusable limit/offset query parameters."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=500, description="Page size.")] = 50,
        offset: Annotated[int, Query(ge=0, description="Number of records to skip.")] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


Pagination = Annotated[PaginationQuery, Depends(PaginationQuery)]

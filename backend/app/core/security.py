"""Authentication / authorization scaffolding.

The first local version runs with ``AUTH_ENABLED=false`` and a synthetic principal so a
developer can start without an identity provider. The structure below is intentionally the
shape an enterprise deployment needs (OIDC/SSO + RBAC), so enabling it later does not require
touching services or routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    STEWARD = "steward"
    ADMIN = "admin"


class Permission(StrEnum):
    METADATA_READ = "metadata:read"
    METADATA_WRITE = "metadata:write"
    LINEAGE_READ = "lineage:read"
    LINEAGE_VERIFY = "lineage:verify"
    GOVERNANCE_WRITE = "governance:write"
    CONNECTOR_MANAGE = "connector:manage"
    COPILOT_USE = "copilot:use"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.METADATA_READ, Permission.LINEAGE_READ}),
    Role.ANALYST: frozenset(
        {Permission.METADATA_READ, Permission.LINEAGE_READ, Permission.COPILOT_USE}
    ),
    Role.STEWARD: frozenset(
        {
            Permission.METADATA_READ,
            Permission.METADATA_WRITE,
            Permission.LINEAGE_READ,
            Permission.LINEAGE_VERIFY,
            Permission.GOVERNANCE_WRITE,
            Permission.COPILOT_USE,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}


@dataclass(slots=True, frozen=True)
class Principal:
    """The authenticated caller. Propagated into audit events."""

    subject: str
    display_name: str = ""
    email: str | None = None
    roles: frozenset[Role] = field(default_factory=lambda: frozenset({Role.VIEWER}))
    tenant_id: str | None = None

    @property
    def permissions(self) -> frozenset[Permission]:
        perms: set[Permission] = set()
        for role in self.roles:
            perms |= ROLE_PERMISSIONS.get(role, frozenset())
        return frozenset(perms)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.has(permission):
            raise AuthorizationError(
                f"Principal '{self.subject}' lacks permission '{permission}'.",
                details={"required_permission": permission.value},
            )


def anonymous_principal() -> Principal:
    """Development principal used when authentication is disabled."""
    return Principal(
        subject=settings.default_principal,
        display_name="Local Developer",
        roles=frozenset({Role.ADMIN}),
    )


def decode_token(token: str) -> Principal:
    """Validate a bearer token and map claims onto a :class:`Principal`.

    TODO: replace the shared-secret path with JWKS retrieval from the enterprise IdP and
    cache signing keys. TODO: map IdP groups to :class:`Role` through configuration.
    """
    if not settings.jwt_secret:
        raise AuthenticationError("Authentication is enabled but no verification key is configured.")

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"verify_aud": bool(settings.jwt_audience)},
        )
    except jwt.PyJWTError as exc:
        logger.warning("token_rejected", extra={"reason": str(exc)})
        raise AuthenticationError("Invalid or expired token.") from exc

    raw_roles = claims.get("roles") or claims.get("groups") or []
    roles = {Role(role) for role in raw_roles if role in set(Role)} or {Role.VIEWER}

    return Principal(
        subject=str(claims.get("sub", "unknown")),
        display_name=str(claims.get("name", "")),
        email=claims.get("email"),
        roles=frozenset(roles),
        tenant_id=claims.get("tid") or claims.get("tenant_id"),
    )

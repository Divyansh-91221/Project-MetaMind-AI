"""Append-only audit trail access."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction
from app.core.logging import get_request_id
from app.models.audit import AuditEvent
from app.utils.serialization import to_jsonable
from app.utils.timestamps import utcnow


class AuditRepository:
    """Writes are append-only; the application never updates or deletes audit rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        action: AuditAction,
        *,
        principal: str = "system",
        entity_id: uuid.UUID | None = None,
        entity_urn: str | None = None,
        resource_type: str | None = None,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            occurred_at=utcnow(),
            principal=principal,
            request_id=get_request_id(),
            entity_id=entity_id,
            entity_urn=entity_urn,
            resource_type=resource_type,
            summary=summary,
            payload=to_jsonable(payload or {}),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        *,
        action: AuditAction | None = None,
        entity_urn: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc())
        if action is not None:
            stmt = stmt.where(AuditEvent.action == action)
        if entity_urn:
            stmt = stmt.where(AuditEvent.entity_urn == entity_urn)
        stmt = stmt.limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

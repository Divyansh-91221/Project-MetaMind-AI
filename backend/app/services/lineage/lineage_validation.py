"""Human validation of lineage.

Architectural rule: the LLM may *propose* lineage, but only a human (or a high-trust
deterministic extractor) can make it authoritative. This module owns the review queue and the
verification transitions, and it records every decision in the audit trail.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction, LineageMethod, VerificationStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.lineage import LineageEdge
from app.repositories.audit_repository import AuditRepository
from app.repositories.lineage_repository import LineageRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[VerificationStatus, set[VerificationStatus]] = {
    VerificationStatus.UNVERIFIED: {
        VerificationStatus.VERIFIED,
        VerificationStatus.REJECTED,
        VerificationStatus.NEEDS_REVIEW,
    },
    VerificationStatus.NEEDS_REVIEW: {
        VerificationStatus.VERIFIED,
        VerificationStatus.REJECTED,
    },
    VerificationStatus.VERIFIED: {VerificationStatus.NEEDS_REVIEW, VerificationStatus.REJECTED},
    VerificationStatus.REJECTED: {VerificationStatus.NEEDS_REVIEW, VerificationStatus.VERIFIED},
}


class LineageValidationService:
    """Manages the review queue and verification state machine."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lineage_repo = LineageRepository(session)
        self.audit_repo = AuditRepository(session)

    async def review_queue(self, *, limit: int = 50) -> list[LineageEdge]:
        """Edges awaiting a human decision, lowest confidence first."""
        return await self.lineage_repo.list_pending_verification(limit=limit)

    async def verify(
        self,
        edge_id: uuid.UUID,
        *,
        status: VerificationStatus,
        principal: str,
        note: str | None = None,
    ) -> LineageEdge:
        """Apply a verification decision to a lineage edge."""
        edge = await self.lineage_repo.get_by_id(edge_id)
        if edge is None:
            raise NotFoundError(f"Lineage edge {edge_id} was not found.")

        allowed = _ALLOWED_TRANSITIONS.get(edge.verification_status, set())
        if status is not edge.verification_status and status not in allowed:
            raise ValidationError(
                f"Cannot move lineage edge from {edge.verification_status} to {status}.",
                details={"allowed": sorted(item.value for item in allowed)},
            )

        await self.lineage_repo.set_verification(
            edge, status=status, principal=principal, note=note
        )

        action = (
            AuditAction.LINEAGE_VERIFIED
            if status is VerificationStatus.VERIFIED
            else AuditAction.LINEAGE_REJECTED
        )
        await self.audit_repo.record(
            action,
            principal=principal,
            entity_id=edge.target_id,
            resource_type="lineage_edge",
            summary=f"Lineage edge {edge_id} marked {status.value}.",
            payload={
                "edge_id": str(edge_id),
                "status": status.value,
                "method": edge.method.value,
                "note": note,
            },
        )
        logger.info(
            "lineage_verification_recorded",
            extra={"edge_id": str(edge_id), "status": status.value, "principal": principal},
        )
        return edge

    @staticmethod
    def requires_human_review(edge: LineageEdge, *, threshold: float = 0.7) -> bool:
        """AI-inferred or low-confidence edges must never be presented as fact."""
        if edge.verification_status is VerificationStatus.VERIFIED:
            return False
        return edge.method is LineageMethod.AI_INFERRED or edge.confidence < threshold

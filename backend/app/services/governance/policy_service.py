"""Policy evaluation.

Policies are declarative JSON rules matched against an asset's classification, sensitivity,
platform, tags and entity type. Evaluation is advisory in this version - it reports which
policies apply and which obligations follow - and is the natural place to plug in enforcement
(masking, access decisions) once RBAC is wired up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ClassificationLevel, SensitivityTag
from app.core.logging import get_logger
from app.models.governance import Policy
from app.models.metadata import MetadataEntity
from app.repositories.governance_repository import GovernanceRepository

logger = get_logger(__name__)

DEFAULT_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "name": "PII Access Control",
        "policy_type": "ACCESS",
        "description": "Assets containing personal data require an approved access request.",
        "enforcement": "ADVISORY",
        "rule": {"sensitivity": ["PII"], "obligation": "approved_access_request"},
    },
    {
        "name": "Restricted Data Masking",
        "policy_type": "MASKING",
        "description": "Restricted columns must be masked outside the owning domain.",
        "enforcement": "ADVISORY",
        "rule": {"classification_level": ["RESTRICTED"], "obligation": "dynamic_masking"},
    },
    {
        "name": "Financial Reporting Retention",
        "policy_type": "RETENTION",
        "description": "Financial reporting assets are retained for seven years.",
        "enforcement": "ADVISORY",
        "rule": {"sensitivity": ["FINANCIAL"], "obligation": "retain_7_years"},
    },
    {
        "name": "Certified Dashboard Ownership",
        "policy_type": "STEWARDSHIP",
        "description": "Dashboards and KPIs must have a named business owner.",
        "enforcement": "ADVISORY",
        "rule": {"entity_type": ["DASHBOARD", "KPI", "REPORT"], "obligation": "business_owner"},
    },
)


@dataclass(slots=True)
class PolicyEvaluation:
    policy: Policy
    applies: bool
    reason: str


class PolicyService:
    """Matches policies to assets and explains why they apply."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = GovernanceRepository(session)

    async def seed_defaults(self) -> None:
        """Install the baseline policy set (idempotent)."""
        for policy in DEFAULT_POLICIES:
            await self.repo.upsert_policy(**policy)

    async def applicable_policies(
        self,
        entity: MetadataEntity,
        *,
        sensitivities: set[SensitivityTag],
        levels: set[ClassificationLevel],
    ) -> list[Policy]:
        evaluations = await self.evaluate(entity, sensitivities=sensitivities, levels=levels)
        return [evaluation.policy for evaluation in evaluations if evaluation.applies]

    async def evaluate(
        self,
        entity: MetadataEntity,
        *,
        sensitivities: set[SensitivityTag],
        levels: set[ClassificationLevel],
    ) -> list[PolicyEvaluation]:
        """Evaluate every active policy against the asset."""
        results: list[PolicyEvaluation] = []
        for policy in await self.repo.list_policies(active_only=True):
            applies, reason = self._matches(policy, entity, sensitivities, levels)
            results.append(PolicyEvaluation(policy=policy, applies=applies, reason=reason))
        return results

    @staticmethod
    def _matches(
        policy: Policy,
        entity: MetadataEntity,
        sensitivities: set[SensitivityTag],
        levels: set[ClassificationLevel],
    ) -> tuple[bool, str]:
        rule = policy.rule or {}
        checks: list[tuple[str, bool]] = []

        if required := rule.get("sensitivity"):
            matched = bool({tag.value for tag in sensitivities} & set(required))
            checks.append((f"sensitivity in {required}", matched))
        if required := rule.get("classification_level"):
            matched = bool({level.value for level in levels} & set(required))
            checks.append((f"classification level in {required}", matched))
        if required := rule.get("entity_type"):
            matched = entity.entity_type.value in required
            checks.append((f"entity type in {required}", matched))
        if required := rule.get("platform"):
            matched = entity.platform in required
            checks.append((f"platform in {required}", matched))
        if required := rule.get("tag"):
            matched = bool(set(entity.tags) & set(required))
            checks.append((f"tag in {required}", matched))

        if not checks:
            return False, "Policy has no matching criteria."
        applies = all(matched for _, matched in checks)
        reason = "; ".join(f"{label}: {'yes' if matched else 'no'}" for label, matched in checks)
        return applies, reason

"""Governance tool: ownership, classification, policy and sensitive-data discovery."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.constants import SensitivityTag
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.schemas.governance import SensitiveAssetsQuery
from app.services.governance.governance_service import GovernanceService


class GovernanceTool(Tool):
    name = "governance_lookup"
    description = (
        "Return ownership, classification, sensitivity and applicable policies for an asset, "
        "or list assets carrying a given sensitivity such as PII."
    )
    argument_hint = "urn: str | sensitivity: 'PII'|'PCI'|'FINANCIAL', limit: int"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = GovernanceService(session)

    async def run(
        self,
        *,
        urn: str | None = None,
        sensitivity: str | None = None,
        limit: int = 25,
        **_: Any,
    ) -> ToolResult:
        if sensitivity:
            return await self._sensitive_assets(sensitivity, limit)
        if urn:
            return await self._profile(urn)
        return ToolResult(warnings=["governance_lookup requires either 'urn' or 'sensitivity'."])

    async def _profile(self, urn: str) -> ToolResult:
        try:
            profile = await self.service.get_profile(urn)
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        owners = (
            ", ".join(f"{item.owner.name} ({item.role.value})" for item in profile.owners)
            or "no owner assigned"
        )
        classifications = (
            ", ".join(item.classification.name for item in profile.classifications) or "none"
        )
        evidence = [
            EvidenceItem(
                kind="governance",
                title=f"Governance profile for {profile.entity_name}",
                detail=(
                    f"Owners: {owners}. Classifications: {classifications}. "
                    f"Classification level: {profile.classification_level.value}. "
                    f"Contains PII: {'yes' if profile.contains_pii else 'no'}."
                ),
                urn=profile.entity_urn,
                source="governance registry (PostgreSQL)",
                payload=profile.model_dump(mode="json"),
            )
        ]
        evidence.extend(
            EvidenceItem(
                kind="governance",
                title=f"Policy: {policy.name}",
                detail=f"{policy.description or ''} Enforcement: {policy.enforcement}.",
                urn=profile.entity_urn,
                source="policy registry",
                payload=policy.rule,
            )
            for policy in profile.applicable_policies
        )

        return ToolResult(
            summary=f"Ownership and classification for {profile.entity_name}.",
            evidence=evidence,
            data={"profile": profile.model_dump(mode="json")},
            warnings=profile.compliance_notes,
        )

    async def _sensitive_assets(self, sensitivity: str, limit: int) -> ToolResult:
        try:
            tag = SensitivityTag(sensitivity.upper())
        except ValueError:
            return ToolResult(warnings=[f"Unknown sensitivity tag '{sensitivity}'."])

        rows = await self.service.sensitive_assets(
            SensitiveAssetsQuery(sensitivity=tag, limit=limit)
        )
        evidence = [
            EvidenceItem(
                kind="governance",
                title=str(row["qualified_name"]),
                detail=(
                    f"{str(row['entity_type']).title()} on {row['platform']} classified as "
                    f"{row['classification']} ({row['level']})"
                    + (f", regulation {row['regulation']}." if row.get("regulation") else ".")
                ),
                urn=str(row["urn"]),
                source="classification registry",
            )
            for row in rows
        ]
        return ToolResult(
            summary=f"{len(rows)} asset(s) classified as {tag.value}.",
            evidence=evidence,
            data={"assets": rows},
            warnings=[] if rows else [f"No assets are classified as {tag.value}."],
        )

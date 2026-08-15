"""Data classification and sensitivity detection.

Classification is rule-driven and explainable by default. Rules produce a suggestion with a
confidence score and stored evidence; only a steward (or a high-confidence exact rule) marks
an assignment as confirmed. AI-suggested classifications follow the same review path as
AI-inferred lineage - they are never silently treated as fact.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ClassificationLevel, SensitivityTag
from app.core.logging import get_logger
from app.models.metadata import MetadataEntity
from app.repositories.governance_repository import GovernanceRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    """A named, auditable detection rule."""

    name: str
    pattern: re.Pattern[str]
    level: ClassificationLevel
    sensitivity: SensitivityTag
    confidence: float
    description: str
    regulation: str | None = None


DEFAULT_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        name="PII.Email",
        pattern=re.compile(r"(^|_)e?mail(_|$)"),
        level=ClassificationLevel.CONFIDENTIAL,
        sensitivity=SensitivityTag.PII,
        confidence=0.95,
        description="Email address of an identifiable person.",
        regulation="GDPR",
    ),
    ClassificationRule(
        name="PII.Name",
        pattern=re.compile(r"(first|last|full|customer|contact)_?name$"),
        level=ClassificationLevel.CONFIDENTIAL,
        sensitivity=SensitivityTag.PII,
        confidence=0.85,
        description="Name of an identifiable person or organisation.",
        regulation="GDPR",
    ),
    ClassificationRule(
        name="PII.CustomerIdentifier",
        pattern=re.compile(r"(^|_)(customer|client|party)_?id$"),
        level=ClassificationLevel.CONFIDENTIAL,
        sensitivity=SensitivityTag.PII,
        confidence=0.8,
        description="Identifier that can be linked back to a natural person.",
        regulation="GDPR",
    ),
    ClassificationRule(
        name="PII.NationalId",
        pattern=re.compile(r"(ssn|national_?id|tax_?id|passport)"),
        level=ClassificationLevel.RESTRICTED,
        sensitivity=SensitivityTag.PII,
        confidence=0.97,
        description="Government-issued identifier.",
        regulation="GDPR",
    ),
    ClassificationRule(
        name="PCI.CardNumber",
        pattern=re.compile(r"(card_?number|pan|cvv|iban|account_?number)"),
        level=ClassificationLevel.RESTRICTED,
        sensitivity=SensitivityTag.PCI,
        confidence=0.95,
        description="Payment instrument data.",
        regulation="PCI-DSS",
    ),
    ClassificationRule(
        name="Financial.Amount",
        pattern=re.compile(r"(amount|revenue|price|cost|margin|salary)"),
        level=ClassificationLevel.INTERNAL,
        sensitivity=SensitivityTag.FINANCIAL,
        confidence=0.6,
        description="Monetary value used in financial reporting.",
        regulation="SOX",
    ),
)


@dataclass(slots=True)
class ClassificationSuggestion:
    entity_urn: str
    classification_name: str
    sensitivity: SensitivityTag
    level: ClassificationLevel
    confidence: float
    matched_rule: str
    evidence: dict[str, str]


class ClassificationService:
    """Applies classification rules and persists the resulting assignments."""

    def __init__(
        self, session: AsyncSession, rules: tuple[ClassificationRule, ...] = DEFAULT_RULES
    ) -> None:
        self.session = session
        self.repo = GovernanceRepository(session)
        self.rules = rules

    def suggest(self, entity: MetadataEntity) -> list[ClassificationSuggestion]:
        """Evaluate every rule against an entity's name and description."""
        haystack = f"{entity.name} {entity.qualified_name}".lower()
        suggestions: list[ClassificationSuggestion] = []
        for rule in self.rules:
            if not rule.pattern.search(haystack):
                continue
            suggestions.append(
                ClassificationSuggestion(
                    entity_urn=entity.urn,
                    classification_name=rule.name,
                    sensitivity=rule.sensitivity,
                    level=rule.level,
                    confidence=rule.confidence,
                    matched_rule=rule.name,
                    evidence={
                        "rule": rule.name,
                        "pattern": rule.pattern.pattern,
                        "matched_on": entity.name,
                    },
                )
            )
        return suggestions

    async def ensure_definitions(self) -> None:
        """Make sure every rule has a backing classification definition row."""
        for rule in self.rules:
            await self.repo.upsert_classification(
                rule.name,
                level=rule.level,
                sensitivity=rule.sensitivity,
                description=rule.description,
                regulation=rule.regulation,
            )

    async def apply(
        self, entity: MetadataEntity, *, principal: str = "system", auto_confirm_above: float = 0.9
    ) -> list[ClassificationSuggestion]:
        """Persist rule matches. High-confidence exact rules are auto-confirmed."""
        suggestions = self.suggest(entity)
        for suggestion in suggestions:
            classification = await self.repo.get_classification(suggestion.classification_name)
            if classification is None:
                await self.ensure_definitions()
                classification = await self.repo.get_classification(
                    suggestion.classification_name
                )
            if classification is None:  # pragma: no cover - defensive
                continue
            await self.repo.assign_classification(
                entity.id,
                classification.id,
                method="RULE",
                confidence=suggestion.confidence,
                confirmed=suggestion.confidence >= auto_confirm_above,
                assigned_by=principal,
                evidence=suggestion.evidence,
            )
        if suggestions:
            logger.debug(
                "classifications_applied",
                extra={"urn": entity.urn, "count": len(suggestions)},
            )
        return suggestions

    async def assign_named(
        self,
        entity_id: uuid.UUID,
        classification_name: str,
        *,
        method: str = "MANUAL",
        confidence: float = 1.0,
        confirmed: bool = True,
        principal: str = "system",
    ) -> None:
        """Attach a classification declared by a connector or a steward."""
        classification = await self.repo.get_classification(classification_name)
        if classification is None:
            await self.ensure_definitions()
            classification = await self.repo.get_classification(classification_name)
        if classification is None:
            classification = await self.repo.upsert_classification(
                classification_name,
                level=ClassificationLevel.INTERNAL,
                sensitivity=SensitivityTag.NONE,
                description="Created on demand during ingestion.",
            )
        await self.repo.assign_classification(
            entity_id,
            classification.id,
            method=method,
            confidence=confidence,
            confirmed=confirmed,
            assigned_by=principal,
        )

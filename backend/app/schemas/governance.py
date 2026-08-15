"""Governance API contracts: ownership, classification and policy."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import EmailStr, Field

from app.core.constants import ClassificationLevel, OwnershipRole, SensitivityTag
from app.schemas.common import APIModel


class OwnerRead(APIModel):
    id: uuid.UUID
    name: str
    email: str | None = None
    owner_type: str = "TEAM"
    department: str | None = None


class OwnerCreate(APIModel):
    name: str
    email: EmailStr | None = None
    owner_type: str = "TEAM"
    department: str | None = None
    external_id: str | None = None


class OwnershipAssignment(APIModel):
    entity_urn: str
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    role: OwnershipRole = OwnershipRole.DATA_OWNER


class OwnershipRead(APIModel):
    role: OwnershipRole
    owner: OwnerRead


class ClassificationRead(APIModel):
    id: uuid.UUID
    name: str
    level: ClassificationLevel
    sensitivity: SensitivityTag
    description: str | None = None
    regulation: str | None = None


class EntityClassificationRead(APIModel):
    classification: ClassificationRead
    method: str = "MANUAL"
    confidence: float = 1.0
    confirmed: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class ClassificationAssignment(APIModel):
    entity_urn: str
    classification_name: str
    method: str = "MANUAL"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed: bool = True


class PolicyRead(APIModel):
    id: uuid.UUID
    name: str
    policy_type: str
    description: str | None = None
    enforcement: str = "ADVISORY"
    active: bool = True
    rule: dict[str, Any] = Field(default_factory=dict)


class GovernanceProfile(APIModel):
    """Everything a steward needs to know about one asset."""

    entity_urn: str
    entity_name: str
    owners: list[OwnershipRead] = Field(default_factory=list)
    classifications: list[EntityClassificationRead] = Field(default_factory=list)
    highest_sensitivity: SensitivityTag = SensitivityTag.NONE
    classification_level: ClassificationLevel = ClassificationLevel.INTERNAL
    applicable_policies: list[PolicyRead] = Field(default_factory=list)
    contains_pii: bool = False
    unowned: bool = True
    compliance_notes: list[str] = Field(default_factory=list)


class SensitiveAssetsQuery(APIModel):
    sensitivity: SensitivityTag = SensitivityTag.PII
    platform: str | None = None
    limit: int = Field(default=50, ge=1, le=500)

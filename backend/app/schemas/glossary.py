"""Business glossary API contracts."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class BusinessTermBase(APIModel):
    name: str
    domain: str = "enterprise"
    definition: str
    short_description: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    abbreviation: str | None = None
    is_kpi: bool = False
    calculation: str | None = None
    unit: str | None = None
    status: str = "APPROVED"
    steward: str | None = None


class BusinessTermCreate(BusinessTermBase):
    linked_entity_urns: list[str] = Field(default_factory=list)


class BusinessTermRead(BusinessTermBase):
    id: uuid.UUID
    properties: dict[str, Any] = Field(default_factory=dict)


class LinkedAsset(APIModel):
    urn: str
    name: str
    qualified_name: str
    entity_type: str
    platform: str
    method: str = "MANUAL"
    confidence: float = 1.0


class BusinessTermDetail(BusinessTermRead):
    """A term plus the technical assets that implement it."""

    linked_assets: list[LinkedAsset] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)


class TermAssignmentRequest(APIModel):
    term_name: str
    entity_urn: str
    method: str = "MANUAL"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

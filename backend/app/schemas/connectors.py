"""Connector registration and discovery contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.constants import PlatformType
from app.schemas.common import APIModel


class ConnectorDescriptor(APIModel):
    """Describes a connector implementation available in the registry."""

    name: str
    platform: PlatformType
    description: str = ""
    supports_lineage: bool = False
    supports_column_lineage: bool = False
    supports_quality: bool = False
    implemented: bool = True
    required_config: list[str] = Field(default_factory=list)


class DataSourceCreate(APIModel):
    """Register a data source. Secrets are referenced, never stored inline."""

    name: str = Field(min_length=1, max_length=255)
    connector_type: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = Field(
        default=None,
        description="Key in the environment/secret manager holding the credentials.",
    )
    enabled: bool = True


class DataSourceRead(APIModel):
    id: uuid.UUID
    name: str
    connector_type: str
    platform: PlatformType
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    last_ingested_at: datetime | None = None
    last_ingestion_status: str | None = None
    created_at: datetime


class ConnectionTestResult(APIModel):
    success: bool
    message: str = ""
    latency_ms: float = 0.0

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


class IngestionRunRead(APIModel):
    """One ingestion run, assembled from its audit trail events."""

    run_id: str
    connector: str
    status: str = "RUNNING"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    assets_processed: int | None = None
    lineage_edges: int | None = None
    warnings: list[str] = Field(default_factory=list)


class DemoResetResult(APIModel):
    """Outcome of a demo-data reset - reuses the ingestion, graph and index jobs."""

    success: bool
    entities_created: int = 0
    entities_updated: int = 0
    lineage_edges_created: int = 0
    lineage_edges_updated: int = 0
    graph: str = ""
    index: str = ""

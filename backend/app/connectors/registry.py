"""Connector registry.

Connectors are looked up by name at runtime, so adding a new source system means adding a
class and registering it - no service, API or ingestion code changes.
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import MetadataConnector
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)

_REGISTRY: dict[str, type[MetadataConnector]] = {}


def register_connector(connector_cls: type[MetadataConnector]) -> type[MetadataConnector]:
    """Register a connector class. Usable as a decorator."""
    name = connector_cls.name.lower()
    if name in _REGISTRY and _REGISTRY[name] is not connector_cls:
        logger.warning("connector_overridden", extra={"connector": name})
    _REGISTRY[name] = connector_cls
    return connector_cls


def get_connector_class(name: str) -> type[MetadataConnector]:
    try:
        return _REGISTRY[name.lower().strip()]
    except KeyError as exc:
        raise NotFoundError(
            f"Unknown connector '{name}'.",
            details={"available": sorted(_REGISTRY)},
        ) from exc


def create_connector(name: str, config: dict[str, Any] | None = None) -> MetadataConnector:
    """Instantiate a connector with its configuration."""
    return get_connector_class(name)(config or {})


def list_connectors() -> list[type[MetadataConnector]]:
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def _bootstrap() -> None:
    """Import and register the built-in connectors.

    Imports are local to avoid circular imports at module load time.
    """
    from app.connectors.bi.powerbi import PowerBIConnector
    from app.connectors.demo import DemoConnector
    from app.connectors.events.openlineage import OpenLineageConnector
    from app.connectors.relational.generic_sql import GenericSQLConnector
    from app.connectors.relational.postgres import PostgresConnector
    from app.connectors.warehouse.snowflake import SnowflakeConnector

    for connector_cls in (
        DemoConnector,
        PostgresConnector,
        GenericSQLConnector,
        SnowflakeConnector,
        PowerBIConnector,
        OpenLineageConnector,
    ):
        register_connector(connector_cls)


_bootstrap()

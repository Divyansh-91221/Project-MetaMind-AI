"""Power BI connector (skeleton).

Power BI exposes datasets, reports, dashboards and dataset-to-source relationships through
the Scanner API. The mapping to platform entities is documented here so the implementation
milestone is mechanical.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    RawLineage,
)
from app.core.constants import EntityType, PlatformType
from app.core.exceptions import ConnectorError

# Power BI object -> catalog entity mapping used by the implementation.
OBJECT_TYPE_MAP: dict[str, EntityType] = {
    "dataset": EntityType.DATASET,
    "report": EntityType.REPORT,
    "dashboard": EntityType.DASHBOARD,
    "table": EntityType.TABLE,
    "column": EntityType.COLUMN,
}

SCANNER_API = "https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo"


class PowerBIConnector(MetadataConnector):
    """Extracts BI assets and their upstream data sources from Power BI."""

    name = "powerbi"
    platform = PlatformType.POWERBI
    description = "Power BI workspaces, datasets, reports, dashboards and their lineage."
    capabilities = ConnectorCapabilities(
        supports_lineage=True,
        supports_column_lineage=True,
        supports_quality=True,
        implemented=False,
    )
    required_config = ("tenant_id", "client_id", "workspace_ids")

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    async def test_connection(self) -> tuple[bool, str]:
        missing = self.validate_config()
        if missing:
            return False, f"Missing configuration: {', '.join(missing)}"
        return False, "Power BI connector is not implemented yet."

    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        # TODO: call the Scanner API with a service principal token and map workspace objects
        # through OBJECT_TYPE_MAP. Credentials must be resolved from `secret_ref`.
        raise ConnectorError(
            "Power BI connector is not implemented yet.",
            details={"scanner_api": SCANNER_API},
        )
        yield  # pragma: no cover

    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        # TODO: dataset -> report/dashboard USES edges and dataset -> warehouse table edges
        # from the datasourceInstances section of the Scanner API response.
        return
        yield  # pragma: no cover

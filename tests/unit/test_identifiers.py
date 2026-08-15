"""URN generation must be stable - it is the backbone of idempotent ingestion."""

from __future__ import annotations

import pytest

from app.core.constants import EntityType
from app.utils.identifiers import (
    build_qualified_name,
    build_urn,
    column_urn,
    is_urn,
    normalize_name,
    parse_urn,
    urn_to_uuid,
)

pytestmark = pytest.mark.unit


def test_urn_is_deterministic() -> None:
    first = build_urn(EntityType.TABLE, "snowflake", "snowflake.sales")
    second = build_urn(EntityType.TABLE, "SNOWFLAKE", "Snowflake.Sales")
    assert first == second == "urn:emc:table:snowflake:snowflake.sales"
    assert urn_to_uuid(first) == urn_to_uuid(second)


def test_urn_round_trip() -> None:
    urn = column_urn("sap", "sap.orders", "amount")
    entity_type, platform, qualified_name = parse_urn(urn)
    assert entity_type is EntityType.COLUMN
    assert platform == "sap"
    assert qualified_name == "sap.orders.amount"


def test_different_entity_types_never_collide() -> None:
    table = build_urn(EntityType.TABLE, "snowflake", "snowflake.customer")
    dataset = build_urn(EntityType.DATASET, "snowflake", "snowflake.customer")
    assert table != dataset
    assert urn_to_uuid(table) != urn_to_uuid(dataset)


def test_normalization_strips_quoting_and_whitespace() -> None:
    assert normalize_name('  "Customer Name" ') == "customer_name"
    assert build_qualified_name("SAP", None, "Customer") == "sap.customer"


@pytest.mark.parametrize("value", ["not-a-urn", "urn:other:table:x:y", "urn:emc:table:x"])
def test_malformed_urns_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_urn(value)


def test_is_urn() -> None:
    assert is_urn("urn:emc:table:sap:sap.customer")
    assert not is_urn("sap.customer")

"""Uniqueness tool: prove whether a field is unique from schema evidence."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.services.metadata.metadata_service import MetadataService


class UniquenessTool(Tool):
    name = "uniqueness_lookup"
    description = (
        "Return schema evidence for whether a column or key is unique, including primary key and "
        "unique constraints extracted from the catalog."
    )
    argument_hint = "urn: str"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = MetadataService(session)

    async def run(self, *, urn: str, **_: Any) -> ToolResult:  # type: ignore[override]
        try:
            detail = await self.service.get_entity_detail(urn)
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        target = detail
        if detail.entity_type.value == "COLUMN" and detail.parent_urn:
            try:
                target = await self.service.get_entity_detail(detail.parent_urn)
            except NotFoundError:
                target = detail

        constraints = _constraint_evidence(target)
        column_flags: list[str] = []
        if detail.is_primary_key:
            column_flags.append("primary key")
        if not constraints and not column_flags:
            return ToolResult(
                summary=f"No uniqueness evidence found for {detail.qualified_name}.",
                warnings=["No primary key or unique constraint is recorded for this asset."],
            )

        evidence: list[EvidenceItem] = []
        for constraint in constraints:
            evidence.append(
                EvidenceItem(
                    kind="constraint",
                    title=constraint["title"],
                    detail=constraint["detail"],
                    urn=target.urn,
                    source="catalog constraints (PostgreSQL)",
                    confidence=1.0,
                    constraint_type=constraint["type"],
                    constraint_name=constraint["name"],
                    constraint_columns=constraint["columns"],
                    payload=constraint,
                )
            )

        if column_flags:
            evidence.append(
                EvidenceItem(
                    kind="constraint",
                    title=f"{detail.qualified_name} uniqueness",
                    detail="This column is recorded as part of a primary key, so it is unique by definition.",
                    urn=detail.urn,
                    source="catalog columns (PostgreSQL)",
                    confidence=1.0,
                    constraint_type="PRIMARY KEY",
                    constraint_columns=[detail.name],
                    payload={"primary_key": True},
                )
            )

        summary = (
            f"Uniqueness evidence for {detail.qualified_name}: "
            f"{len(evidence)} schema constraint(s) recorded."
        )
        return ToolResult(summary=summary, evidence=evidence, data={"constraints": constraints})


def _constraint_evidence(detail: Any) -> list[dict[str, Any]]:
    constraints = detail.properties.get("constraints") or []
    results: list[dict[str, Any]] = []
    for constraint in constraints:
        constraint_type = str(constraint.get("type") or "UNKNOWN").upper()
        columns = [str(column) for column in constraint.get("columns") or []]
        if not columns:
            continue
        results.append(
            {
                "name": str(constraint.get("name") or "constraint"),
                "type": constraint_type,
                "columns": columns,
                "title": f"{constraint_type} on {detail.qualified_name}",
                "detail": (
                    f"{constraint_type.title()} constraint {constraint.get('name') or 'unnamed'} "
                    f"covers {', '.join(columns)}."
                ),
            }
        )
    return results
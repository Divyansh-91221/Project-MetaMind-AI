"""Data access for Metadata Enrichment runs, columns, mappings and issues.

All lookups are keyed by the run's primary key plus natural fields (dataset/column name) -
never by a hardcoded literal ID - so the organiser's workbook keeps working if IDs change.
"""

from __future__ import annotations

import uuid
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EnrichmentIssueStatus, EnrichmentMappingStatus, EnrichmentStage
from app.models.enrichment import (
    EnrichmentColumn,
    EnrichmentIssue,
    EnrichmentMapping,
    EnrichmentRun,
)


class EnrichmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #
    async def create_run(self, **values: Any) -> EnrichmentRun:
        run = EnrichmentRun(**values)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run(self, run_id: uuid.UUID) -> EnrichmentRun | None:
        return await self.session.get(EnrichmentRun, run_id)

    async def set_stage(
        self, run: EnrichmentRun, stage: EnrichmentStage, *, error: str | None = None
    ) -> None:
        run.stage = stage
        if error is not None:
            run.error = error
        await self.session.flush()

    async def refresh_counts(self, run: EnrichmentRun) -> None:
        mappings = await self.list_mappings(run.id)
        issues = await self.list_issues(run.id)
        run.mapping_count = len(mappings)
        run.issue_count = len(issues)
        run.open_issue_count = sum(
            1 for issue in issues if issue.status is EnrichmentIssueStatus.OPEN
        )
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Columns
    # ------------------------------------------------------------------ #
    async def add_column(self, run_id: uuid.UUID, **values: Any) -> EnrichmentColumn:
        column = EnrichmentColumn(run_id=run_id, **values)
        self.session.add(column)
        await self.session.flush()
        return column

    async def list_columns(self, run_id: uuid.UUID) -> list[EnrichmentColumn]:
        stmt = select(EnrichmentColumn).where(EnrichmentColumn.run_id == run_id)
        return list((await self.session.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------ #
    # Mappings
    # ------------------------------------------------------------------ #
    async def add_mapping(self, run_id: uuid.UUID, **values: Any) -> EnrichmentMapping:
        mapping = EnrichmentMapping(run_id=run_id, **values)
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def list_mappings(self, run_id: uuid.UUID) -> list[EnrichmentMapping]:
        stmt = (
            select(EnrichmentMapping)
            .where(EnrichmentMapping.run_id == run_id)
            .order_by(EnrichmentMapping.dataset_name, EnrichmentMapping.column_name)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_mapping(self, mapping_id: uuid.UUID) -> EnrichmentMapping | None:
        return await self.session.get(EnrichmentMapping, mapping_id)

    # ------------------------------------------------------------------ #
    # Issues
    # ------------------------------------------------------------------ #
    async def add_issue(self, run_id: uuid.UUID, **values: Any) -> EnrichmentIssue:
        issue = EnrichmentIssue(run_id=run_id, **values)
        self.session.add(issue)
        await self.session.flush()
        return issue

    async def list_issues(
        self, run_id: uuid.UUID, *, mapping_id: uuid.UUID | None = None
    ) -> list[EnrichmentIssue]:
        stmt = select(EnrichmentIssue).where(EnrichmentIssue.run_id == run_id)
        if mapping_id is not None:
            stmt = stmt.where(EnrichmentIssue.mapping_id == mapping_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def clear_generated_state(self, run_id: uuid.UUID) -> None:
        """Remove previously generated mappings/issues before re-processing a run."""
        for mapping in await self.list_mappings(run_id):
            await self.session.delete(mapping)
        for issue in await self.list_issues(run_id):
            await self.session.delete(issue)
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Cross-run search (used by the Copilot tool - a question rarely names a run id)
    # ------------------------------------------------------------------ #
    async def search_mappings(self, query: str, *, limit: int = 5) -> list[EnrichmentMapping]:
        ignored = {
            "about", "confidence", "enrichment", "explain", "export", "including",
            "issue", "issues", "json", "mapping", "mappings", "review", "status",
            "testing", "the", "uploaded", "with",
        }
        terms = [
            token for token in re.findall(r"[a-z0-9_]+", query.lower())
            if len(token) >= 3 and token not in ignored
        ]
        if not terms:
            terms = [query.lower().strip()]
        predicates = []
        for term in terms:
            pattern = f"%{term}%"
            predicates.extend(
                [
                    func.lower(EnrichmentMapping.column_name).like(pattern),
                    func.lower(EnrichmentMapping.dataset_name).like(pattern),
                    func.lower(func.coalesce(EnrichmentMapping.business_term, "")).like(pattern),
                ]
            )
        stmt = (
            select(EnrichmentMapping)
            .where(or_(*predicates))
            .order_by(EnrichmentMapping.updated_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def open_issues(self, *, limit: int = 10) -> list[EnrichmentIssue]:
        stmt = (
            select(EnrichmentIssue)
            .where(EnrichmentIssue.status == EnrichmentIssueStatus.OPEN)
            .order_by(EnrichmentIssue.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def pending_review_mappings(self, *, limit: int = 10) -> list[EnrichmentMapping]:
        stmt = (
            select(EnrichmentMapping)
            .where(
                EnrichmentMapping.status.in_(
                    [EnrichmentMappingStatus.PENDING_REVIEW, EnrichmentMappingStatus.NEEDS_REVIEW]
                )
            )
            .order_by(EnrichmentMapping.updated_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

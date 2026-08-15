"""Data access for the metadata catalog.

Repositories own SQL. Services own business rules. Nothing here imports FastAPI.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import EntityType
from app.models.metadata import DataSource, MetadataEntity
from app.utils.identifiers import urn_to_uuid
from app.utils.timestamps import utcnow

# Columns that a re-ingestion is allowed to overwrite. Curated fields (description edited by a
# steward, tags) are handled explicitly by the service so ingestion never silently clobbers them.
_UPSERT_COLUMNS = (
    "entity_type",
    "platform",
    "name",
    "qualified_name",
    "display_name",
    "parent_id",
    "data_source_id",
    "data_type",
    "ordinal_position",
    "is_nullable",
    "is_primary_key",
    "row_count",
    "properties",
    "source_system",
    "last_seen_at",
)


class MetadataRepository:
    """CRUD and query access for :class:`MetadataEntity` and :class:`DataSource`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get_by_id(self, entity_id: uuid.UUID) -> MetadataEntity | None:
        return await self.session.get(MetadataEntity, entity_id)

    async def get_by_urn(self, urn: str) -> MetadataEntity | None:
        stmt = select(MetadataEntity).where(MetadataEntity.urn == urn)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_detail_by_urn(self, urn: str) -> MetadataEntity | None:
        """Load an entity with the relationships needed by the asset details page."""
        stmt = (
            select(MetadataEntity)
            .where(MetadataEntity.urn == urn)
            .options(
                selectinload(MetadataEntity.children),
                selectinload(MetadataEntity.owners),
                selectinload(MetadataEntity.classifications),
                selectinload(MetadataEntity.parent),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_many_by_urns(self, urns: list[str]) -> list[MetadataEntity]:
        if not urns:
            return []
        stmt = select(MetadataEntity).where(MetadataEntity.urn.in_(urns))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_children(
        self, parent_id: uuid.UUID, entity_type: EntityType | None = None
    ) -> list[MetadataEntity]:
        stmt = select(MetadataEntity).where(MetadataEntity.parent_id == parent_id)
        if entity_type is not None:
            stmt = stmt.where(MetadataEntity.entity_type == entity_type)
        stmt = stmt.order_by(MetadataEntity.ordinal_position, MetadataEntity.name)
        return list((await self.session.execute(stmt)).scalars().all())

    def _apply_filters(
        self,
        stmt: Select[Any],
        *,
        entity_type: EntityType | None,
        platform: str | None,
        parent_id: uuid.UUID | None,
        search: str | None,
        tag: str | None,
        include_deleted: bool,
    ) -> Select[Any]:
        if entity_type is not None:
            stmt = stmt.where(MetadataEntity.entity_type == entity_type)
        if platform:
            stmt = stmt.where(MetadataEntity.platform == platform)
        if parent_id is not None:
            stmt = stmt.where(MetadataEntity.parent_id == parent_id)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(MetadataEntity.name).like(pattern),
                    func.lower(MetadataEntity.qualified_name).like(pattern),
                    func.lower(func.coalesce(MetadataEntity.description, "")).like(pattern),
                )
            )
        if tag:
            stmt = stmt.where(MetadataEntity.tags.contains([tag]))
        if not include_deleted:
            stmt = stmt.where(MetadataEntity.deleted_at.is_(None))
        return stmt

    async def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        platform: str | None = None,
        parent_id: uuid.UUID | None = None,
        search: str | None = None,
        tag: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MetadataEntity], int]:
        """Return a page of entities plus the total match count."""
        base = select(MetadataEntity)
        base = self._apply_filters(
            base,
            entity_type=entity_type,
            platform=platform,
            parent_id=parent_id,
            search=search,
            tag=tag,
            include_deleted=include_deleted,
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = base.order_by(MetadataEntity.qualified_name).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return rows, total

    async def keyword_search(
        self,
        query: str,
        *,
        entity_types: list[EntityType] | None = None,
        platforms: list[str] | None = None,
        limit: int = 20,
    ) -> list[MetadataEntity]:
        """Lexical search used on its own and as the keyword half of hybrid search."""
        pattern = f"%{query.lower()}%"
        stmt = select(MetadataEntity).where(
            MetadataEntity.deleted_at.is_(None),
            or_(
                func.lower(MetadataEntity.name).like(pattern),
                func.lower(MetadataEntity.qualified_name).like(pattern),
                func.lower(func.coalesce(MetadataEntity.display_name, "")).like(pattern),
                func.lower(func.coalesce(MetadataEntity.description, "")).like(pattern),
            ),
        )
        if entity_types:
            stmt = stmt.where(MetadataEntity.entity_type.in_(entity_types))
        if platforms:
            stmt = stmt.where(MetadataEntity.platform.in_(platforms))
        # Exact and prefix matches first, then shorter (more specific) qualified names.
        stmt = stmt.order_by(
            (func.lower(MetadataEntity.name) == query.lower()).desc(),
            func.length(MetadataEntity.qualified_name),
        ).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_by_name(self, name: str, *, limit: int = 10) -> list[MetadataEntity]:
        """Entity-resolution helper: match on name or the last segment of the qualified name."""
        lowered = name.lower().strip()
        stmt = (
            select(MetadataEntity)
            .where(
                MetadataEntity.deleted_at.is_(None),
                or_(
                    func.lower(MetadataEntity.name) == lowered,
                    func.lower(MetadataEntity.qualified_name) == lowered,
                    func.lower(MetadataEntity.qualified_name).like(f"%.{lowered}"),
                ),
            )
            .order_by(func.length(MetadataEntity.qualified_name))
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_by_type(self) -> dict[str, int]:
        stmt = (
            select(MetadataEntity.entity_type, func.count())
            .where(MetadataEntity.deleted_at.is_(None))
            .group_by(MetadataEntity.entity_type)
        )
        rows = (await self.session.execute(stmt)).all()
        return {row[0].value: int(row[1]) for row in rows}

    async def count_by_platform(self) -> dict[str, int]:
        stmt = (
            select(MetadataEntity.platform, func.count())
            .where(MetadataEntity.deleted_at.is_(None))
            .group_by(MetadataEntity.platform)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(row[0]): int(row[1]) for row in rows}

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def upsert(self, values: dict[str, Any]) -> tuple[MetadataEntity, bool]:
        """Insert or update by URN.

        Uses ``INSERT ... ON CONFLICT`` so concurrent ingestion runs cannot create duplicates.
        Returns the row and whether it was newly created.
        """
        urn = values["urn"]
        values.setdefault("id", urn_to_uuid(urn))
        values.setdefault("last_seen_at", utcnow())

        existing = await self.get_by_urn(urn)

        update_set = {
            column: values[column] for column in _UPSERT_COLUMNS if values.get(column) is not None
        }
        # Descriptions from a source system must not overwrite a curated description.
        if values.get("description") and (existing is None or not existing.description):
            update_set["description"] = values["description"]

        stmt = (
            pg_insert(MetadataEntity)
            .values(**values)
            .on_conflict_do_update(index_elements=[MetadataEntity.urn], set_=update_set)
            .returning(MetadataEntity)
        )
        entity = (await self.session.execute(stmt)).scalar_one()
        await self.session.flush()
        return entity, existing is None

    async def update_curated_fields(
        self, entity: MetadataEntity, changes: dict[str, Any]
    ) -> MetadataEntity:
        for key, value in changes.items():
            if value is not None:
                setattr(entity, key, value)
        await self.session.flush()
        return entity

    async def soft_delete(self, entity: MetadataEntity) -> None:
        entity.deleted_at = utcnow()
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Data sources
    # ------------------------------------------------------------------ #
    async def get_data_source(self, name: str) -> DataSource | None:
        stmt = select(DataSource).where(DataSource.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_data_sources(self) -> list[DataSource]:
        stmt = select(DataSource).order_by(DataSource.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_data_source(self, **values: Any) -> DataSource:
        data_source = DataSource(**values)
        self.session.add(data_source)
        await self.session.flush()
        return data_source

    async def upsert_data_source(self, name: str, **values: Any) -> DataSource:
        existing = await self.get_data_source(name)
        if existing is None:
            return await self.create_data_source(name=name, **values)
        for key, value in values.items():
            setattr(existing, key, value)
        await self.session.flush()
        return existing

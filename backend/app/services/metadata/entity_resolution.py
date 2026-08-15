"""Entity resolution.

Two jobs:

1. **Ingestion-time** - decide whether an incoming record is the same asset as one already in
   the catalog (URN first, then qualified name, then name + platform).
2. **Query-time** - map a natural-language mention such as "customer_id" or "the sales
   dashboard" onto concrete catalog entities. This is the step that keeps the Copilot honest:
   the agent answers about resolved URNs, never about a name the model invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType
from app.core.logging import get_logger
from app.models.metadata import MetadataEntity
from app.repositories.metadata_repository import MetadataRepository
from app.utils.identifiers import is_urn, normalize_name

logger = get_logger(__name__)

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "what",
        "where",
        "which",
        "who",
        "does",
        "do",
        "is",
        "are",
        "from",
        "come",
        "comes",
        "uses",
        "use",
        "used",
        "break",
        "change",
        "changes",
        "show",
        "me",
        "of",
        "for",
        "in",
        "on",
        "to",
        "and",
        "or",
        "my",
        "this",
        "that",
        "table",
        "column",
        "dataset",
        "dashboard",
        "report",
        "kpi",
        "data",
        "if",
        "will",
        "why",
        "how",
        "stale",
        "owns",
        "own",
        "owner",
        "contain",
        "contains",
        "definition",
        "business",
        "lineage",
        "depend",
        "depends",
        "dependent",
    }
)

_TOKEN = re.compile(r"[A-Za-z0-9_.]+")


@dataclass(slots=True)
class ResolutionCandidate:
    """A candidate match with an explainable score."""

    entity: MetadataEntity
    score: float
    matched_on: str

    @property
    def urn(self) -> str:
        return self.entity.urn


class EntityResolutionService:
    """Resolves mentions and duplicate records to catalog entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = MetadataRepository(session)

    # ------------------------------------------------------------------ #
    # Query-time resolution
    # ------------------------------------------------------------------ #
    def extract_mentions(self, text: str) -> list[str]:
        """Pull likely asset names out of a natural-language question."""
        mentions: list[str] = []
        for token in _TOKEN.findall(text):
            lowered = token.lower().strip(".")
            if not lowered or lowered in _STOPWORDS or len(lowered) < 3:
                continue
            if lowered.isdigit():
                continue
            mentions.append(lowered)

        # Multi-word names such as "monthly revenue" that the tokenizer split apart.
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
        for first, second in zip(words, words[1:], strict=False):
            if first in _STOPWORDS or second in _STOPWORDS:
                continue
            mentions.append(f"{first} {second}")

        seen: set[str] = set()
        return [m for m in mentions if not (m in seen or seen.add(m))]

    async def resolve(
        self, mention: str, *, limit: int = 5, entity_types: list[EntityType] | None = None
    ) -> list[ResolutionCandidate]:
        """Resolve one mention to ranked candidates."""
        mention = mention.strip()
        if not mention:
            return []

        if is_urn(mention):
            entity = await self.repo.get_by_urn(mention)
            return [ResolutionCandidate(entity, 1.0, "urn")] if entity else []

        candidates: dict[str, ResolutionCandidate] = {}

        for entity in await self.repo.find_by_name(mention, limit=limit * 2):
            score = self._score(entity, mention)
            candidates[entity.urn] = ResolutionCandidate(entity, score, "name")

        if len(candidates) < limit:
            for entity in await self.repo.keyword_search(
                mention, entity_types=entity_types, limit=limit * 2
            ):
                if entity.urn not in candidates:
                    candidates[entity.urn] = ResolutionCandidate(
                        entity, self._score(entity, mention) * 0.8, "keyword"
                    )

        ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
        if entity_types:
            preferred = [c for c in ranked if c.entity.entity_type in entity_types]
            ranked = preferred + [c for c in ranked if c not in preferred]
        return ranked[:limit]

    async def resolve_query(
        self, text: str, *, limit: int = 5
    ) -> list[ResolutionCandidate]:
        """Resolve every mention in a question and return the best overall candidates."""
        results: dict[str, ResolutionCandidate] = {}
        for mention in self.extract_mentions(text)[:8]:
            for candidate in await self.resolve(mention, limit=3):
                existing = results.get(candidate.urn)
                if existing is None or candidate.score > existing.score:
                    results[candidate.urn] = candidate
        ranked = sorted(results.values(), key=lambda c: c.score, reverse=True)
        logger.debug("entity_resolution", extra={"query": text, "matches": len(ranked)})
        return ranked[:limit]

    @staticmethod
    def _score(entity: MetadataEntity, mention: str) -> float:
        """Explainable scoring: exactness first, then specificity."""
        mention_norm = normalize_name(mention)
        name = entity.name.lower()
        qualified = entity.qualified_name.lower()

        if qualified == mention_norm:
            score = 1.0
        elif name == mention_norm:
            score = 0.95
        elif qualified.endswith(f".{mention_norm}"):
            score = 0.9
        elif mention_norm in qualified:
            score = 0.7
        elif mention_norm in (entity.description or "").lower():
            score = 0.4
        else:
            score = 0.3

        # Prefer concrete assets over containers when both match.
        if entity.entity_type in (EntityType.DATA_SOURCE, EntityType.DATABASE, EntityType.SCHEMA):
            score -= 0.1
        if entity.properties.get("placeholder"):
            score -= 0.2
        return round(max(0.0, score), 3)

    # ------------------------------------------------------------------ #
    # Ingestion-time resolution
    # ------------------------------------------------------------------ #
    async def find_existing(
        self, *, urn: str, qualified_name: str, platform: str
    ) -> MetadataEntity | None:
        """Match an incoming record to an existing row, URN first."""
        entity = await self.repo.get_by_urn(urn)
        if entity is not None:
            return entity
        for candidate in await self.repo.find_by_name(qualified_name, limit=5):
            if candidate.platform == platform and candidate.qualified_name == qualified_name:
                return candidate
        return None

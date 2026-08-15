"""Search tool: hybrid discovery over the catalog and documentation."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.constants import SearchMode
from app.schemas.copilot import EvidenceItem
from app.schemas.search import SearchRequest
from app.services.search.hybrid_search import SearchService
from app.utils.serialization import truncate


class SearchTool(Tool):
    name = "catalog_search"
    description = (
        "Find assets and documentation by natural language or keyword. Use when the user has "
        "not named a specific asset, or to discover related assets."
    )
    argument_hint = "query: str, limit: int"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = SearchService(session)

    async def run(self, *, query: str, limit: int = 8, **_: Any) -> ToolResult:
        response = await self.service.search(
            SearchRequest(q=query, mode=SearchMode.HYBRID, limit=limit)
        )
        retrieval = await self.service.retrieve(query, top_k=limit)

        evidence: list[EvidenceItem] = [
            EvidenceItem(
                kind="entity",
                title=hit.qualified_name,
                detail=(
                    f"{hit.entity_type.value.title()} on {hit.platform}. "
                    f"{hit.description or 'No description available.'}"
                ),
                urn=hit.urn,
                source=f"catalog search ({', '.join(hit.matched_on)})",
                confidence=min(1.0, hit.score),
                payload={"score": hit.score},
            )
            for hit in response.hits
        ]

        evidence.extend(
            EvidenceItem(
                kind="document",
                title=document.document_title,
                detail=truncate(document.content, 600),
                urn=document.entity_urn,
                source=document.source_uri or document.document_type.value,
                confidence=min(1.0, document.score),
                payload={"document_type": document.document_type.value},
            )
            for document in retrieval.documents
        )

        return ToolResult(
            summary=f"{len(response.hits)} asset(s) and {len(retrieval.documents)} document(s) matched.",
            evidence=evidence,
            data={"hits": [hit.model_dump(mode="json") for hit in response.hits]},
            warnings=[] if evidence else [f"Nothing in the catalog matched '{query}'."],
        )

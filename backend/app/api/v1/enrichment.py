"""Metadata Enrichment ("Upload & Enrich") endpoints.

Upload structured data (CSV/XLSX) and documentation (PDF/DOCX/TXT/MD), run AI mapping,
review, and integrate the result into the existing catalog. Every response reuses the same
error envelope and dependency style as the rest of the API.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import Permission
from app.schemas.enrichment import (
    EnrichmentColumnRead,
    EnrichmentDocumentSearchResult,
    EnrichmentIntegrationResult,
    EnrichmentIssueRead,
    EnrichmentIssueResolveRequest,
    EnrichmentMappingRead,
    EnrichmentReviewRequest,
    EnrichmentRunRead,
)
from app.services.enrichment.enrichment_service import EnrichmentService
from app.services.enrichment.integration import EnrichmentIntegrationService
from app.utils.serialization import dumps

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


@router.post("/upload", response_model=EnrichmentRunRead, summary="Upload data + documentation")
async def upload(
    session: DbSession,
    principal: CurrentPrincipal,
    dataset_name: str = Form(...),
    source_system: str | None = Form(default=None),
    business_domain: str | None = Form(default=None),
    description: str | None = Form(default=None),
    structured_files: list[UploadFile] = File(default=[]),
    documentation_files: list[UploadFile] = File(default=[]),
) -> EnrichmentRunRead:
    principal.require(Permission.METADATA_WRITE)
    structured = [(f.filename or "upload.csv", await f.read()) for f in structured_files if f.filename]
    documentation = [
        (f.filename or "doc.txt", await f.read()) for f in documentation_files if f.filename
    ]
    run = await EnrichmentService(session).create_and_ingest(
        dataset_name=dataset_name,
        source_system=source_system,
        business_domain=business_domain,
        description=description,
        structured_files=structured,
        documentation_files=documentation,
        principal=principal.subject,
    )
    return EnrichmentRunRead.model_validate(run)


@router.post(
    "/{run_id}/process", response_model=EnrichmentRunRead, summary="Run AI mapping and validation"
)
async def process_run(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> EnrichmentRunRead:
    principal.require(Permission.METADATA_WRITE)
    run = await EnrichmentService(session).process(run_id, principal=principal.subject)
    return EnrichmentRunRead.model_validate(run)


@router.get("/{run_id}/status", response_model=EnrichmentRunRead, summary="Run status")
async def get_status(run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal) -> EnrichmentRunRead:
    principal.require(Permission.METADATA_READ)
    run = await EnrichmentService(session).get_status(run_id)
    return EnrichmentRunRead.model_validate(run)


@router.get(
    "/{run_id}/columns", response_model=list[EnrichmentColumnRead], summary="Discovered columns"
)
async def list_columns(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> list[EnrichmentColumnRead]:
    principal.require(Permission.METADATA_READ)
    service = EnrichmentService(session)
    await service.get_status(run_id)
    columns = await service.repo.list_columns(run_id)
    return [EnrichmentColumnRead.model_validate(c) for c in columns]


@router.get(
    "/{run_id}/mappings", response_model=list[EnrichmentMappingRead], summary="Column mappings"
)
async def list_mappings(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> list[EnrichmentMappingRead]:
    principal.require(Permission.METADATA_READ)
    mappings = await EnrichmentService(session).list_mappings(run_id)
    return [EnrichmentMappingRead.model_validate(m) for m in mappings]


@router.get("/{run_id}/issues", response_model=list[EnrichmentIssueRead], summary="Quality issues")
async def list_issues(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> list[EnrichmentIssueRead]:
    principal.require(Permission.METADATA_READ)
    issues = await EnrichmentService(session).list_issues(run_id)
    return [EnrichmentIssueRead.model_validate(i) for i in issues]


@router.post(
    "/{run_id}/issues/{issue_id}/resolve",
    response_model=EnrichmentIssueRead,
    summary="Resolve an enrichment quality issue",
)
async def resolve_issue(
    run_id: uuid.UUID,
    issue_id: uuid.UUID,
    payload: EnrichmentIssueResolveRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> EnrichmentIssueRead:
    principal.require(Permission.METADATA_WRITE)
    issue = await EnrichmentService(session).resolve_issue(
        run_id,
        issue_id,
        principal=principal.subject,
        resolution_note=payload.resolution_note,
    )
    return EnrichmentIssueRead.model_validate(issue)


@router.get(
    "/{run_id}/search",
    response_model=list[EnrichmentDocumentSearchResult],
    summary="Search uploaded documentation within a run",
)
async def search_documents(
    run_id: uuid.UUID,
    session: DbSession,
    principal: CurrentPrincipal,
    q: str,
    limit: int = 5,
) -> list[EnrichmentDocumentSearchResult]:
    principal.require(Permission.METADATA_READ)
    return await EnrichmentService(session).search_documents(run_id, q, limit=limit)


@router.get("/{run_id}/metadata", summary="Enriched metadata (canonical shape)")
async def get_metadata(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> list[dict]:
    principal.require(Permission.METADATA_READ)
    return await EnrichmentService(session).build_export(run_id)


@router.post("/{run_id}/review", response_model=EnrichmentMappingRead, summary="Approve/reject/edit a mapping")
async def review(
    run_id: uuid.UUID,
    payload: EnrichmentReviewRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> EnrichmentMappingRead:
    principal.require(Permission.METADATA_WRITE)
    mapping = await EnrichmentService(session).review(run_id, payload, principal=principal.subject)
    return EnrichmentMappingRead.model_validate(mapping)


@router.post(
    "/{run_id}/integrate", response_model=EnrichmentIntegrationResult, summary="Integrate into the catalog"
)
async def integrate(
    run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> EnrichmentIntegrationResult:
    principal.require(Permission.METADATA_WRITE)
    return await EnrichmentIntegrationService(session).integrate(run_id, principal=principal.subject)


@router.get("/{run_id}/export/json", summary="Export enriched metadata as JSON")
async def export_json(run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal) -> Response:
    principal.require(Permission.METADATA_READ)
    export = await EnrichmentService(session).build_export(run_id)
    return Response(content=dumps(export, indent=2), media_type="application/json")


@router.get("/{run_id}/export/yaml", summary="Export enriched metadata as YAML")
async def export_yaml(run_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal) -> Response:
    principal.require(Permission.METADATA_READ)
    import yaml

    export = await EnrichmentService(session).build_export(run_id)
    return Response(content=yaml.safe_dump(export, sort_keys=False), media_type="application/yaml")

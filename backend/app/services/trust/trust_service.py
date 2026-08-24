"""Trust Center aggregation service."""

from __future__ import annotations

from app.core.constants import EntityType, OwnershipRole, QualityStatus, SensitivityTag
from app.core.exceptions import NotFoundError
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.trust import (
    AssetTrustSummary,
    DependencyRiskSummary,
    OwnershipSummary,
    ReliabilitySummary,
    SensitiveFieldDetection,
    TrustDimension,
    TrustIssue,
    TrustScoreExplanation,
)
from app.services.governance.governance_service import GovernanceService
from app.services.impact.impact_service import ImpactService
from app.services.metadata.metadata_service import MetadataService
from app.services.quality.quality_service import QualityService
from app.services.trust.trust_scoring import (
    DependencySignal,
    SensitiveSignal,
    build_trust_issues,
    compute_trust_score,
    dependency_risk,
    score_freshness,
    score_lineage_health,
    score_ownership,
    score_quality,
    score_security,
    trust_status,
)


class TrustService:
    def __init__(self, session) -> None:
        self.session = session
        self.metadata_service = MetadataService(session)
        self.quality_service = QualityService(session)
        self.governance_service = GovernanceService(session)
        self.impact_service = ImpactService(session)
        self.metadata_repo = MetadataRepository(session)
        self.governance_repo = GovernanceRepository(session)

    async def get_asset_trust(self, urn: str) -> AssetTrustSummary:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        detail = await self.metadata_service.get_entity_detail(urn)
        quality = await self.quality_service.get_profile(urn)
        governance = await self.governance_service.get_profile(urn)
        impact = await self.impact_service.analyze(urn, depth=6, min_confidence=0.0)
        dependencies = await self.impact_service.dependencies(urn, depth=5)

        columns = await self.metadata_repo.get_children(entity.id, entity_type=EntityType.COLUMN)
        classification_ids = [entity.id, *[column.id for column in columns]]
        classifications = await self.governance_repo.classifications_for_entities(classification_ids)
        sensitive_assignments = [
            assignment
            for assignment in classifications
            if assignment.classification.sensitivity is not SensitivityTag.NONE
        ]

        pending_sensitive_reviews = sum(
            1 for assignment in sensitive_assignments if not assignment.confirmed
        )

        dependency_signal = DependencySignal(
            downstream_asset_count=impact.summary.total_impacted,
            critical_downstream_consumers=impact.summary.critical_assets,
            dashboards_affected=impact.summary.dashboards_affected,
            reports_affected=impact.summary.by_entity_type.get("REPORT", 0),
            unverified_dependency_count=dependencies.unverified_dependency_count,
            inferred_path_count=impact.summary.inferred_paths,
        )
        dependency_level, dependency_reason = dependency_risk(dependency_signal)

        freshness = quality.freshness
        freshness_score = score_freshness(
            freshness.status if freshness else None,
            is_stale=freshness.is_stale if freshness else False,
        )
        quality_score = score_quality([metric.status for metric in quality.metrics])
        lineage_score = score_lineage_health(dependency_signal)
        ownership_score = score_ownership(not governance.unowned)
        security_score = score_security(
            SensitiveSignal(
                sensitive_count=len(sensitive_assignments),
                pending_review_count=pending_sensitive_reviews,
            )
        )

        components = {
            "freshness": freshness_score,
            "quality": quality_score,
            "lineage_health": lineage_score,
            "ownership": ownership_score,
            "security": security_score,
        }
        total = compute_trust_score(components)

        quality_warning_count = sum(
            1
            for metric in quality.metrics
            if metric.status in {QualityStatus.WARN, QualityStatus.FAIL}
        )
        raw_issues = build_trust_issues(
            freshness_score=freshness_score,
            quality_warning_count=quality_warning_count,
            pending_sensitive_reviews=pending_sensitive_reviews,
            dependency_level=dependency_level,
            has_owner=not governance.unowned,
        )

        quality_by_name = {
            metric.metric_name.lower(): metric.value
            for metric in quality.metrics
            if metric.value is not None
        }

        reliability = ReliabilitySummary(
            freshness_status=(freshness.status.value if freshness else QualityStatus.UNKNOWN.value),
            freshness_last_updated_at=freshness.last_updated_at if freshness else None,
            freshness_age_hours=freshness.age_hours if freshness else None,
            freshness_expected_interval_hours=(
                freshness.expected_interval_hours if freshness else None
            ),
            is_stale=freshness.is_stale if freshness else False,
            freshness_failure_reason=freshness.failure_reason if freshness else None,
            quality_score=quality_score,
            quality_warning_count=quality_warning_count,
            completeness=quality_by_name.get("completeness"),
            validity=quality_by_name.get("validity"),
            null_rate=quality_by_name.get("null_rate"),
            anomaly_count=(
                int(quality_by_name["anomaly_count"])
                if "anomaly_count" in quality_by_name
                else None
            ),
        )

        dependency_summary = DependencyRiskSummary(
            upstream_asset_count=(
                len(dependencies.direct_dependencies) + len(dependencies.transitive_dependencies)
            ),
            downstream_asset_count=impact.summary.total_impacted,
            critical_downstream_consumers=impact.summary.critical_assets,
            dashboards_affected=impact.summary.dashboards_affected,
            reports_affected=impact.summary.by_entity_type.get("REPORT", 0),
            dependency_risk_level=dependency_level,
            reason=dependency_reason,
            unverified_dependency_count=dependencies.unverified_dependency_count,
            inferred_path_count=impact.summary.inferred_paths,
        )

        owner_name = next(
            (
                owner.owner.name
                for owner in governance.owners
                if owner.role == OwnershipRole.DATA_OWNER.value
            ),
            governance.owners[0].owner.name if governance.owners else None,
        )
        steward_name = next(
            (
                owner.owner.name
                for owner in governance.owners
                if owner.role == OwnershipRole.DATA_STEWARD.value
            ),
            None,
        )
        team_name = next(
            (owner.owner.name for owner in governance.owners if "TEAM" in owner.role),
            owner_name,
        )

        ownership = OwnershipSummary(
            owner=owner_name,
            steward=steward_name,
            status="UNOWNED" if governance.unowned else "ASSIGNED",
            team=team_name,
            warning=(
                "Ownership gap detected. Assign an accountable owner to increase trust."
                if governance.unowned
                else None
            ),
        )

        sensitive_rows = [
            SensitiveFieldDetection(
                assignment_id=str(assignment.id),
                entity_urn=assignment.entity.urn,
                qualified_name=assignment.entity.qualified_name,
                column_name=(assignment.entity.name if assignment.entity.entity_type is EntityType.COLUMN else None),
                classification=assignment.classification.name,
                confidence=assignment.confidence,
                detection_source=assignment.method,
                review_status="CONFIRMED" if assignment.confirmed else "PENDING_REVIEW",
                evidence=assignment.evidence,
            )
            for assignment in sorted(
                sensitive_assignments,
                key=lambda row: (
                    row.entity.entity_type != EntityType.COLUMN,
                    row.entity.qualified_name,
                    row.classification.name,
                ),
            )
        ]

        dimensions = [
            TrustDimension(
                key="freshness",
                label="Freshness",
                score=freshness_score,
                status=self._score_status(freshness_score),
                reason=(
                    "Data is stale or freshness checks are warning."
                    if freshness_score < 70
                    else "Freshness checks are healthy."
                ),
                evidence=[
                    f"freshness_status={reliability.freshness_status}",
                    (
                        f"age_hours={reliability.freshness_age_hours:.2f}"
                        if reliability.freshness_age_hours is not None
                        else "age_hours=unknown"
                    ),
                ],
            ),
            TrustDimension(
                key="quality",
                label="Data Quality",
                score=quality_score,
                status=self._score_status(quality_score),
                reason=(
                    "One or more quality metrics are warning or failing."
                    if quality_warning_count > 0
                    else "Quality metrics are healthy."
                ),
                evidence=[
                    f"quality_metrics={len(quality.metrics)}",
                    f"quality_warnings={quality_warning_count}",
                ],
            ),
            TrustDimension(
                key="lineage_health",
                label="Lineage Health",
                score=lineage_score,
                status=self._score_status(lineage_score),
                reason=dependency_reason,
                evidence=[
                    f"downstream_assets={dependency_signal.downstream_asset_count}",
                    f"critical_consumers={dependency_signal.critical_downstream_consumers}",
                    f"unverified_dependencies={dependency_signal.unverified_dependency_count}",
                ],
            ),
            TrustDimension(
                key="ownership",
                label="Ownership",
                score=ownership_score,
                status="CRITICAL" if governance.unowned else "HEALTHY",
                reason=(
                    "No accountable owner assigned."
                    if governance.unowned
                    else "Accountable ownership is assigned."
                ),
                evidence=[
                    f"owners={len(governance.owners)}",
                ],
            ),
            TrustDimension(
                key="security",
                label="Security / Sensitive Data",
                score=security_score,
                status=(
                    "PENDING_REVIEW"
                    if pending_sensitive_reviews > 0
                    else self._score_status(security_score)
                ),
                reason=(
                    f"{pending_sensitive_reviews} sensitive field(s) await review."
                    if pending_sensitive_reviews > 0
                    else "Sensitive-data classifications are reviewed."
                ),
                evidence=[
                    f"sensitive_fields={len(sensitive_rows)}",
                    f"pending_reviews={pending_sensitive_reviews}",
                ],
            ),
        ]

        issues = [
            TrustIssue(
                code=item["code"],
                severity=item["severity"],
                title=item["title"],
                detail=item["detail"],
                target_page=item["target_page"],
                target_url=self._target_url(item["target_page"], urn),
            )
            for item in raw_issues
        ]

        positives, negatives = self._score_explanation(
            dimensions=dimensions,
            issues=issues,
            pending_sensitive_reviews=pending_sensitive_reviews,
        )

        return AssetTrustSummary(
            entity_urn=entity.urn,
            asset_name=(entity.display_name or entity.name),
            platform=entity.platform,
            asset_type=entity.entity_type.value,
            description=entity.description,
            owner=owner_name,
            last_updated_at=(freshness.last_updated_at if freshness else entity.updated_at),
            trust_score=total,
            trust_status=trust_status(total),
            dimensions=dimensions,
            reliability=reliability,
            dependency_risk=dependency_summary,
            sensitive_data=sensitive_rows,
            ownership=ownership,
            issues=issues,
            explanation=TrustScoreExplanation(positives=positives, negatives=negatives),
        )

    @staticmethod
    def _score_status(score: int) -> str:
        if score >= 85:
            return "HEALTHY"
        if score >= 65:
            return "WARNING"
        return "CRITICAL"

    @staticmethod
    def _target_url(target_page: str, urn: str) -> str:
        if target_page == "quality":
            return f"/assets?urn={urn}"
        if target_page == "impact":
            return f"/impact?urn={urn}"
        if target_page == "lineage":
            return f"/lineage?urn={urn}"
        if target_page == "governance":
            return "/governance"
        return f"/assets?urn={urn}"

    @staticmethod
    def _score_explanation(
        *,
        dimensions: list[TrustDimension],
        issues: list[TrustIssue],
        pending_sensitive_reviews: int,
    ) -> tuple[list[str], list[str]]:
        positives = [
            f"{dimension.label} is strong ({dimension.score}/100)."
            for dimension in dimensions
            if dimension.score >= 85
        ]
        negatives = [issue.title for issue in issues]
        if pending_sensitive_reviews == 0:
            positives.append("Sensitive-data detections are reviewed.")
        if not negatives:
            negatives.append("No active trust warnings were detected.")
        return positives, negatives

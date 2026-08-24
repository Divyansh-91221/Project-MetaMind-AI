"""Trust Center deterministic scoring tests."""

from __future__ import annotations

import pytest

from app.core.constants import QualityStatus
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
)

pytestmark = pytest.mark.unit


class TestTrustScore:
    def test_trust_score_is_deterministic(self) -> None:
        components = {
            "freshness": 95,
            "quality": 90,
            "lineage_health": 88,
            "ownership": 100,
            "security": 82,
        }
        assert compute_trust_score(components) == compute_trust_score(components)

    def test_freshness_scoring_penalizes_stale_data(self) -> None:
        healthy = score_freshness(QualityStatus.PASS, is_stale=False)
        stale = score_freshness(QualityStatus.WARN, is_stale=True)
        assert healthy > stale

    def test_quality_scoring_reflects_metric_statuses(self) -> None:
        high = score_quality([QualityStatus.PASS, QualityStatus.PASS])
        low = score_quality([QualityStatus.FAIL, QualityStatus.WARN])
        assert high > low


class TestSensitiveDataAggregation:
    def test_security_score_drops_when_sensitive_reviews_are_pending(self) -> None:
        reviewed = score_security(SensitiveSignal(sensitive_count=4, pending_review_count=0))
        pending = score_security(SensitiveSignal(sensitive_count=4, pending_review_count=2))
        assert reviewed > pending


class TestDependencyRisk:
    def test_dependency_risk_levels_are_derived_from_blast_radius(self) -> None:
        low, _ = dependency_risk(
            DependencySignal(
                downstream_asset_count=2,
                critical_downstream_consumers=0,
                dashboards_affected=0,
                reports_affected=0,
                unverified_dependency_count=0,
                inferred_path_count=0,
            )
        )
        high, _ = dependency_risk(
            DependencySignal(
                downstream_asset_count=24,
                critical_downstream_consumers=5,
                dashboards_affected=4,
                reports_affected=3,
                unverified_dependency_count=2,
                inferred_path_count=1,
            )
        )
        assert low == "LOW"
        assert high in {"HIGH", "CRITICAL"}

    def test_lineage_health_is_lower_for_higher_dependency_risk(self) -> None:
        low_score = score_lineage_health(
            DependencySignal(
                downstream_asset_count=3,
                critical_downstream_consumers=0,
                dashboards_affected=0,
                reports_affected=0,
                unverified_dependency_count=0,
                inferred_path_count=0,
            )
        )
        high_score = score_lineage_health(
            DependencySignal(
                downstream_asset_count=18,
                critical_downstream_consumers=4,
                dashboards_affected=3,
                reports_affected=2,
                unverified_dependency_count=3,
                inferred_path_count=2,
            )
        )
        assert low_score > high_score


class TestOwnershipRisk:
    def test_unowned_assets_are_penalized(self) -> None:
        assert score_ownership(True) > score_ownership(False)


class TestTrustIssues:
    def test_issue_generation_uses_real_signals(self) -> None:
        issues = build_trust_issues(
            freshness_score=60,
            quality_warning_count=2,
            pending_sensitive_reviews=1,
            dependency_level="HIGH",
            has_owner=False,
        )
        codes = {issue["code"] for issue in issues}
        assert {
            "freshness_degraded",
            "quality_warnings",
            "sensitive_pending_review",
            "dependency_risk_high",
            "unowned_asset",
        }.issubset(codes)

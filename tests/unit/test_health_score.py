"""Deterministic health-score tests.

Pure function, no I/O: this is what keeps the score reproducible and explainable, which
matters more for stewardship trust than any single weighting choice.
"""

from __future__ import annotations

import pytest

from app.core.constants import QualityStatus
from app.services.metadata.health_score import WEIGHTS, compute_health_score

pytestmark = pytest.mark.unit


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)


class TestComputeHealthScore:
    def test_perfect_asset_scores_100(self) -> None:
        result = compute_health_score(
            freshness_status=QualityStatus.PASS,
            quality_pass_ratio=1.0,
            has_owner=True,
            classification_state="confirmed",
            lineage_state="verified",
        )
        assert result.total == 100
        assert result.label == "Excellent"

    def test_worst_asset_scores_low(self) -> None:
        result = compute_health_score(
            freshness_status=QualityStatus.FAIL,
            quality_pass_ratio=0.0,
            has_owner=False,
            classification_state="unconfirmed",
            lineage_state="inferred",
        )
        assert result.total < 50
        assert result.label == "At risk"

    def test_untracked_asset_is_neutral_not_penalised(self) -> None:
        """No freshness/quality/lineage data yet should read as neutral, not broken."""
        result = compute_health_score(
            freshness_status=None,
            quality_pass_ratio=None,
            has_owner=True,
            classification_state="none",
            lineage_state="none",
        )
        assert 50 <= result.total <= 85

    def test_missing_owner_is_the_dominant_ownership_signal(self) -> None:
        with_owner = compute_health_score(
            freshness_status=QualityStatus.PASS,
            quality_pass_ratio=1.0,
            has_owner=True,
            classification_state="none",
            lineage_state="verified",
        )
        without_owner = compute_health_score(
            freshness_status=QualityStatus.PASS,
            quality_pass_ratio=1.0,
            has_owner=False,
            classification_state="none",
            lineage_state="verified",
        )
        assert without_owner.total < with_owner.total

    def test_unconfirmed_classification_scores_lower_than_confirmed(self) -> None:
        confirmed = compute_health_score(
            freshness_status=QualityStatus.PASS,
            quality_pass_ratio=1.0,
            has_owner=True,
            classification_state="confirmed",
            lineage_state="verified",
        )
        unconfirmed = compute_health_score(
            freshness_status=QualityStatus.PASS,
            quality_pass_ratio=1.0,
            has_owner=True,
            classification_state="unconfirmed",
            lineage_state="verified",
        )
        assert unconfirmed.total < confirmed.total

    def test_total_is_bounded_between_zero_and_hundred(self) -> None:
        result = compute_health_score(
            freshness_status=QualityStatus.FAIL,
            quality_pass_ratio=0.0,
            has_owner=False,
            classification_state="unconfirmed",
            lineage_state="inferred",
        )
        assert 0 <= result.total <= 100

    def test_components_returned_for_explainability(self) -> None:
        result = compute_health_score(
            freshness_status=QualityStatus.WARN,
            quality_pass_ratio=0.5,
            has_owner=True,
            classification_state="confirmed",
            lineage_state="verified",
        )
        assert set(result.components) == {
            "freshness",
            "quality",
            "ownership",
            "governance",
            "lineage",
        }

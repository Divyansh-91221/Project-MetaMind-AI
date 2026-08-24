"""Confidence scoring and lineage normalisation tests.

These encode the trust model: how a relationship was observed determines how much it is
believed, AI inference is penalised, and duplicate assertions become corroboration rather
than duplicate edges.
"""

from __future__ import annotations

import pytest

from app.connectors.base import RawLineage
from app.core.constants import LineageLevel, LineageMethod, RelationshipType
from app.services.lineage.lineage_confidence import (
    MAX_CONFIDENCE_UNVERIFIED,
    ConfidenceSignals,
    LineageConfidenceScorer,
)
from app.services.lineage.lineage_normalizer import LineageNormalizer

pytestmark = pytest.mark.unit


@pytest.fixture
def scorer() -> LineageConfidenceScorer:
    return LineageConfidenceScorer()


@pytest.fixture
def normalizer() -> LineageNormalizer:
    return LineageNormalizer()


def _raw(
    source: str = "urn:emc:column:sap:sap.orders.amount",
    target: str = "urn:emc:column:snowflake:snowflake.sales.total_revenue",
    **kwargs: object,
) -> RawLineage:
    return RawLineage(source_urn=source, target_urn=target, **kwargs)  # type: ignore[arg-type]


class TestMethodRanking:
    def test_manual_outranks_automated_extraction(self, scorer: LineageConfidenceScorer) -> None:
        manual = scorer.score(ConfidenceSignals(method=LineageMethod.MANUAL))
        parsed = scorer.score(ConfidenceSignals(method=LineageMethod.SQL_PARSE))
        assert manual.score > parsed.score

    def test_sql_parse_outranks_ai_inference(self, scorer: LineageConfidenceScorer) -> None:
        parsed = scorer.score(ConfidenceSignals(method=LineageMethod.SQL_PARSE))
        inferred = scorer.score(ConfidenceSignals(method=LineageMethod.AI_INFERRED))
        assert parsed.score > inferred.score

    def test_ai_inferred_always_requires_review(self, scorer: LineageConfidenceScorer) -> None:
        result = scorer.score(
            ConfidenceSignals(
                method=LineageMethod.AI_INFERRED,
                has_transformation=True,
                has_pipeline_context=True,
                has_source_evidence=True,
                exact_name_match=True,
            )
        )
        assert result.requires_review is True


class TestSignals:
    def test_supporting_signals_raise_the_score(self, scorer: LineageConfidenceScorer) -> None:
        bare = scorer.score(ConfidenceSignals(method=LineageMethod.SQL_PARSE))
        rich = scorer.score(
            ConfidenceSignals(
                method=LineageMethod.SQL_PARSE,
                has_transformation=True,
                has_pipeline_context=True,
                has_source_evidence=True,
                exact_name_match=True,
            )
        )
        assert rich.score > bare.score

    def test_name_similarity_only_is_penalised(self, scorer: LineageConfidenceScorer) -> None:
        weak = scorer.score(
            ConfidenceSignals(method=LineageMethod.AI_INFERRED, name_similarity_only=True)
        )
        assert weak.score < 0.4

    def test_type_mismatch_lowers_confidence(self, scorer: LineageConfidenceScorer) -> None:
        match = scorer.score(
            ConfidenceSignals(method=LineageMethod.SQL_PARSE, data_type_match=True)
        )
        mismatch = scorer.score(
            ConfidenceSignals(method=LineageMethod.SQL_PARSE, data_type_match=False)
        )
        assert mismatch.score < match.score

    def test_corroboration_raises_confidence(self, scorer: LineageConfidenceScorer) -> None:
        single = scorer.score(
            ConfidenceSignals(method=LineageMethod.SQL_PARSE, corroborating_methods=1)
        )
        several = scorer.score(
            ConfidenceSignals(method=LineageMethod.SQL_PARSE, corroborating_methods=3)
        )
        assert several.score > single.score

    def test_score_is_explained(self, scorer: LineageConfidenceScorer) -> None:
        result = scorer.score(
            ConfidenceSignals(method=LineageMethod.SQL_PARSE, has_transformation=True)
        )
        assert len(result.explanation) >= 2


class TestBounds:
    def test_unverified_lineage_never_reaches_certainty(
        self, scorer: LineageConfidenceScorer
    ) -> None:
        """Only a human decision may assert 1.0."""
        result = scorer.score(
            ConfidenceSignals(
                method=LineageMethod.MANUAL,
                has_transformation=True,
                has_pipeline_context=True,
                has_source_evidence=True,
                exact_name_match=True,
                data_type_match=True,
                corroborating_methods=5,
                observation_count=100,
            )
        )
        assert result.score <= MAX_CONFIDENCE_UNVERIFIED

    def test_score_never_goes_negative(self, scorer: LineageConfidenceScorer) -> None:
        result = scorer.score(
            ConfidenceSignals(
                method=LineageMethod.AI_INFERRED,
                name_similarity_only=True,
                data_type_match=False,
            )
        )
        assert result.score > 0.0


class TestNormalizer:
    def test_duplicate_assertions_collapse_into_one_edge(
        self, normalizer: LineageNormalizer
    ) -> None:
        merged = normalizer.normalize([_raw(), _raw(), _raw()])
        assert len(merged) == 1

    def test_strongest_method_wins(self, normalizer: LineageNormalizer) -> None:
        merged = normalizer.normalize(
            [
                _raw(method=LineageMethod.AI_INFERRED, confidence=0.4),
                _raw(method=LineageMethod.SQL_PARSE),
            ]
        )
        assert merged[0].method is LineageMethod.SQL_PARSE

    def test_corroborating_methods_are_recorded_as_evidence(
        self, normalizer: LineageNormalizer
    ) -> None:
        merged = normalizer.normalize(
            [
                _raw(method=LineageMethod.SQL_PARSE),
                _raw(method=LineageMethod.OPENLINEAGE),
            ]
        )
        assert set(merged[0].evidence["corroborating_methods"]) == {"SQL_PARSE", "OPENLINEAGE"}

    def test_transformation_is_preserved_from_whichever_source_had_it(
        self, normalizer: LineageNormalizer
    ) -> None:
        merged = normalizer.normalize(
            [
                _raw(method=LineageMethod.CONNECTOR_DECLARED),
                _raw(method=LineageMethod.SQL_PARSE, transformation="SUM(amount)"),
            ]
        )
        assert merged[0].transformation == "SUM(amount)"

    def test_whitespace_in_transformations_is_collapsed(
        self, normalizer: LineageNormalizer
    ) -> None:
        merged = normalizer.normalize([_raw(transformation="SUM(\n   amount\n)")])
        assert merged[0].transformation == "SUM( amount )"

    def test_self_referencing_edges_are_dropped(self, normalizer: LineageNormalizer) -> None:
        same = "urn:emc:column:sap:sap.orders.amount"
        assert normalizer.normalize([_raw(source=same, target=same)]) == []

    def test_edges_missing_an_endpoint_are_dropped(self, normalizer: LineageNormalizer) -> None:
        assert normalizer.normalize([_raw(source="")]) == []

    def test_observed_at_is_always_populated(self, normalizer: LineageNormalizer) -> None:
        merged = normalizer.normalize([_raw()])
        assert merged[0].observed_at is not None

    def test_inferred_edges_keep_their_low_confidence_despite_corroboration(
        self, normalizer: LineageNormalizer
    ) -> None:
        """An AI guess must not be laundered into a high score by repetition."""
        merged = normalizer.normalize(
            [
                _raw(method=LineageMethod.AI_INFERRED, confidence=0.3),
                _raw(method=LineageMethod.AI_INFERRED, confidence=0.4),
            ]
        )
        assert merged[0].method is LineageMethod.AI_INFERRED
        assert merged[0].confidence == 0.3

    def test_distinct_levels_stay_separate_edges(self, normalizer: LineageNormalizer) -> None:
        merged = normalizer.normalize(
            [
                _raw(level=LineageLevel.TABLE),
                _raw(level=LineageLevel.COLUMN),
            ]
        )
        assert len(merged) == 2

    def test_distinct_relationships_stay_separate_edges(
        self, normalizer: LineageNormalizer
    ) -> None:
        merged = normalizer.normalize(
            [
                _raw(relationship=RelationshipType.DERIVED_FROM),
                _raw(relationship=RelationshipType.USES),
            ]
        )
        assert len(merged) == 2

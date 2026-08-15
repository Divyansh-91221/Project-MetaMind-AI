"""Lineage confidence scoring.

Confidence is derived from *how* a relationship was observed, never asserted by the LLM.
The scorer combines:

* a base score per extraction method,
* corroboration - the same edge seen by several independent methods or repeatedly over time,
* signal quality - an explicit transformation, a known pipeline, matching column names,
* penalties - AI inference, missing evidence, name-similarity-only matches.

Human verification always pins confidence to 1.0 (or 0.0 on rejection); the score is only a
prior for review prioritisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.constants import METHOD_BASE_CONFIDENCE, LineageMethod

MAX_CONFIDENCE_UNVERIFIED = 0.98
MIN_CONFIDENCE = 0.05


@dataclass(slots=True)
class ConfidenceSignals:
    """Inputs to the scorer. All optional - absent signals simply do not contribute."""

    method: LineageMethod = LineageMethod.CONNECTOR_DECLARED
    has_transformation: bool = False
    has_pipeline_context: bool = False
    has_source_evidence: bool = False
    exact_name_match: bool = False
    name_similarity_only: bool = False
    corroborating_methods: int = 0
    observation_count: int = 1
    data_type_match: bool | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConfidenceResult:
    score: float
    explanation: list[str]

    @property
    def requires_review(self) -> bool:
        return self.score < 0.7


class LineageConfidenceScorer:
    """Deterministic, explainable confidence scoring."""

    def score(self, signals: ConfidenceSignals) -> ConfidenceResult:
        base = METHOD_BASE_CONFIDENCE.get(signals.method, 0.5)
        explanation = [f"Base score {base:.2f} for extraction method {signals.method.value}."]
        score = base

        if signals.has_transformation:
            score += 0.03
            explanation.append("Explicit transformation expression captured (+0.03).")
        if signals.has_pipeline_context:
            score += 0.02
            explanation.append("Linked to a known pipeline or job run (+0.02).")
        if signals.has_source_evidence:
            score += 0.02
            explanation.append("Source evidence (SQL/event payload) stored (+0.02).")
        if signals.exact_name_match:
            score += 0.02
            explanation.append("Source and target column names match exactly (+0.02).")
        if signals.data_type_match is True:
            score += 0.02
            explanation.append("Source and target data types are compatible (+0.02).")
        elif signals.data_type_match is False:
            score -= 0.05
            explanation.append("Source and target data types differ (-0.05).")

        if signals.corroborating_methods > 1:
            bonus = min(0.08, 0.04 * (signals.corroborating_methods - 1))
            score += bonus
            explanation.append(
                f"Corroborated by {signals.corroborating_methods} independent methods (+{bonus:.2f})."
            )
        if signals.observation_count > 3:
            score += 0.02
            explanation.append(
                f"Observed {signals.observation_count} times across runs (+0.02)."
            )

        if signals.method is LineageMethod.AI_INFERRED:
            score -= 0.05
            explanation.append("AI-inferred relationship: penalised and flagged for review (-0.05).")
        if signals.name_similarity_only:
            score -= 0.15
            explanation.append("Supported only by name similarity (-0.15).")
        if not signals.has_source_evidence and signals.method is not LineageMethod.MANUAL:
            score -= 0.05
            explanation.append("No stored source evidence (-0.05).")

        explanation.extend(signals.reasons)
        score = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE_UNVERIFIED, score))
        return ConfidenceResult(score=round(score, 3), explanation=explanation)

    def score_edge(
        self,
        *,
        method: LineageMethod,
        transformation: str | None,
        pipeline_urn: str | None,
        evidence: dict[str, object] | None,
        source_column: str | None = None,
        target_column: str | None = None,
        observation_count: int = 1,
    ) -> ConfidenceResult:
        """Convenience wrapper used by the ingestion processors."""
        evidence = evidence or {}
        return self.score(
            ConfidenceSignals(
                method=method,
                has_transformation=bool(transformation),
                has_pipeline_context=bool(pipeline_urn),
                has_source_evidence=bool(evidence.get("sql") or evidence.get("source")),
                exact_name_match=bool(
                    source_column and target_column and source_column.lower() == target_column.lower()
                ),
                name_similarity_only=str(evidence.get("source", "")).startswith("name-similarity"),
                observation_count=observation_count,
            )
        )


scorer = LineageConfidenceScorer()

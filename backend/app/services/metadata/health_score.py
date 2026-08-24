"""Deterministic data health score.

Combines freshness, quality, ownership, governance and lineage signals that already exist in
the catalog into a single 0-100 score. No LLM involved: every input is a fact already surfaced
elsewhere in the UI, so the score is always explainable and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.constants import QualityStatus

ClassificationState = Literal["none", "confirmed", "unconfirmed"]
LineageState = Literal["none", "verified", "inferred"]

# Percentage weight each dimension contributes to the total. Sums to 1.0.
WEIGHTS: dict[str, float] = {
    "freshness": 0.25,
    "quality": 0.25,
    "ownership": 0.15,
    "governance": 0.20,
    "lineage": 0.15,
}

_FRESHNESS_SCORES: dict[QualityStatus | None, int] = {
    QualityStatus.PASS: 100,
    QualityStatus.WARN: 60,
    QualityStatus.FAIL: 20,
    QualityStatus.UNKNOWN: 50,
    None: 60,
}

_OWNERSHIP_SCORES = {True: 100, False: 30}

_GOVERNANCE_SCORES: dict[ClassificationState, int] = {
    "none": 85,
    "confirmed": 100,
    "unconfirmed": 60,
}

_LINEAGE_SCORES: dict[LineageState, int] = {
    "none": 70,
    "inferred": 65,
    "verified": 100,
}


@dataclass(slots=True)
class HealthScoreResult:
    total: int
    components: dict[str, int] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=lambda: dict(WEIGHTS))
    label: str = "Unknown"


def _label_for(total: int) -> str:
    if total >= 85:
        return "Excellent"
    if total >= 70:
        return "Good"
    if total >= 50:
        return "Needs attention"
    return "At risk"


def compute_health_score(
    *,
    freshness_status: QualityStatus | None,
    quality_pass_ratio: float | None,
    has_owner: bool,
    classification_state: ClassificationState,
    lineage_state: LineageState,
) -> HealthScoreResult:
    """Pure, deterministic scoring function - no I/O, no randomness, no LLM.

    ``quality_pass_ratio`` is the share of the asset's latest quality metrics that passed
    (PASS=1.0, WARN=0.5, FAIL=0.0), or ``None`` when no metrics have been recorded yet.
    """
    components = {
        "freshness": _FRESHNESS_SCORES.get(freshness_status, 50),
        "quality": 60 if quality_pass_ratio is None else round(quality_pass_ratio * 100),
        "ownership": _OWNERSHIP_SCORES[has_owner],
        "governance": _GOVERNANCE_SCORES[classification_state],
        "lineage": _LINEAGE_SCORES[lineage_state],
    }
    total = round(sum(components[key] * weight for key, weight in WEIGHTS.items()))
    total = max(0, min(100, total))
    return HealthScoreResult(total=total, components=components, label=_label_for(total))

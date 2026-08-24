"""Deterministic Trust Center scoring helpers.

Pure functions only: no I/O, no randomness, no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.constants import QualityStatus

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

TRUST_WEIGHTS: dict[str, float] = {
    "freshness": 0.24,
    "quality": 0.24,
    "lineage_health": 0.20,
    "ownership": 0.14,
    "security": 0.18,
}


@dataclass(slots=True)
class DependencySignal:
    downstream_asset_count: int
    critical_downstream_consumers: int
    dashboards_affected: int
    reports_affected: int
    unverified_dependency_count: int
    inferred_path_count: int


@dataclass(slots=True)
class SensitiveSignal:
    sensitive_count: int
    pending_review_count: int


def score_freshness(status: QualityStatus | None, *, is_stale: bool) -> int:
    if status is QualityStatus.PASS and not is_stale:
        return 100
    if status is QualityStatus.WARN or is_stale:
        return 65
    if status is QualityStatus.FAIL:
        return 25
    return 55


def score_quality(statuses: list[QualityStatus]) -> int:
    if not statuses:
        return 60
    severity = {
        QualityStatus.PASS: 1.0,
        QualityStatus.WARN: 0.5,
        QualityStatus.UNKNOWN: 0.5,
        QualityStatus.FAIL: 0.0,
    }
    ratio = sum(severity[state] for state in statuses) / len(statuses)
    return round(ratio * 100)


def dependency_risk(signal: DependencySignal) -> tuple[RiskLevel, str]:
    score = 0
    if signal.downstream_asset_count >= 20:
        score += 3
    elif signal.downstream_asset_count >= 8:
        score += 2
    elif signal.downstream_asset_count >= 3:
        score += 1

    if signal.critical_downstream_consumers >= 5:
        score += 3
    elif signal.critical_downstream_consumers >= 2:
        score += 2
    elif signal.critical_downstream_consumers == 1:
        score += 1

    if signal.unverified_dependency_count >= 3:
        score += 1
    if signal.inferred_path_count >= 1:
        score += 1

    if score >= 7:
        return "CRITICAL", "This asset feeds many business-critical downstream consumers."
    if score >= 5:
        return "HIGH", "This asset has broad downstream blast radius and critical consumers."
    if score >= 3:
        return "MEDIUM", "This asset feeds multiple downstream consumers."
    return "LOW", "Downstream dependency footprint is limited."


def score_lineage_health(signal: DependencySignal) -> int:
    level, _ = dependency_risk(signal)
    base = {
        "LOW": 96,
        "MEDIUM": 82,
        "HIGH": 68,
        "CRITICAL": 52,
    }[level]
    if signal.unverified_dependency_count > 0:
        base -= min(12, signal.unverified_dependency_count * 3)
    if signal.inferred_path_count > 0:
        base -= min(10, signal.inferred_path_count * 2)
    return max(0, min(100, base))


def score_ownership(has_owner: bool) -> int:
    return 100 if has_owner else 25


def score_security(signal: SensitiveSignal) -> int:
    if signal.sensitive_count == 0:
        return 100
    pending_ratio = signal.pending_review_count / signal.sensitive_count
    if pending_ratio == 0:
        return 90
    return max(40, 90 - round(pending_ratio * 60))


def compute_trust_score(components: dict[str, int]) -> int:
    total = round(sum(components[key] * TRUST_WEIGHTS[key] for key in TRUST_WEIGHTS))
    return max(0, min(100, total))


def trust_status(total: int) -> str:
    if total >= 90:
        return "Trusted with minor warnings"
    if total >= 75:
        return "Generally trusted"
    if total >= 60:
        return "Use with caution"
    return "Trust at risk"


def build_trust_issues(
    *,
    freshness_score: int,
    quality_warning_count: int,
    pending_sensitive_reviews: int,
    dependency_level: RiskLevel,
    has_owner: bool,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if freshness_score < 70:
        issues.append(
            {
                "code": "freshness_degraded",
                "severity": "WARNING",
                "title": "Data freshness degraded",
                "detail": "Recent freshness checks indicate the asset may be stale.",
                "target_page": "quality",
            }
        )

    if quality_warning_count > 0:
        level = "CRITICAL" if quality_warning_count >= 2 else "WARNING"
        issues.append(
            {
                "code": "quality_warnings",
                "severity": level,
                "title": f"{quality_warning_count} quality warning(s) detected",
                "detail": "Quality metrics include warning/failure states.",
                "target_page": "quality",
            }
        )

    if pending_sensitive_reviews > 0:
        issues.append(
            {
                "code": "sensitive_pending_review",
                "severity": "WARNING",
                "title": f"{pending_sensitive_reviews} sensitive field(s) awaiting review",
                "detail": "Detected sensitive classifications are not yet confirmed.",
                "target_page": "governance",
            }
        )

    if dependency_level in {"HIGH", "CRITICAL"}:
        issues.append(
            {
                "code": "dependency_risk_high",
                "severity": "CRITICAL" if dependency_level == "CRITICAL" else "WARNING",
                "title": f"Dependency risk is {dependency_level}",
                "detail": "Many downstream assets may be affected by changes.",
                "target_page": "impact",
            }
        )

    if not has_owner:
        issues.append(
            {
                "code": "unowned_asset",
                "severity": "CRITICAL",
                "title": "Asset is unowned",
                "detail": "No accountable owner is assigned.",
                "target_page": "governance",
            }
        )

    return issues

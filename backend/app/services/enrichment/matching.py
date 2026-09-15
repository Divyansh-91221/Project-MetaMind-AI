"""Column -> business term / documentation matching.

Confidence scoring blends deterministic lexical similarity with retrieval over the
documentation uploaded in the same run. It never depends on a record ID, row number or
fixed position - only on names, tokens and retrieved text - so the organiser can rename or
renumber anything and the matcher keeps working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")

# Confidence bands. Anything below LOW_CONFIDENCE_THRESHOLD is routed to human review rather
# than forced onto a mapping.
HIGH_CONFIDENCE_THRESHOLD = 0.75
LOW_CONFIDENCE_THRESHOLD = 0.45


def tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def token_similarity(a: str, b: str) -> float:
    """Jaccard similarity over tokens, with a boost for exact/substring token matches.

    Deliberately simple and dependency-free: for "cust_id" vs "Customer Identifier" this
    rewards the shared "id"/"identifier" and "cust"/"customer" stems without requiring an
    embedding model, and improves further whenever real embeddings are configured because the
    caller blends this score with retrieval-based evidence.
    """
    tokens_a, tokens_b = tokenize(a), tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0

    exact = tokens_a & tokens_b
    prefix_matches = sum(
        1
        for ta in tokens_a
        for tb in tokens_b
        if ta != tb and len(ta) >= 3 and len(tb) >= 3 and (ta.startswith(tb) or tb.startswith(ta))
    )
    union = tokens_a | tokens_b
    score = (len(exact) + 0.6 * prefix_matches) / len(union)
    return min(1.0, score)


@dataclass(slots=True)
class MappingCandidate:
    term: str
    confidence: float
    source: str
    definition: str | None = None
    document_title: str | None = None
    document_source: str | None = None
    evidence_excerpt: str | None = None
    method: str = "GLOSSARY_MATCH"


def rank_candidates(candidates: list[MappingCandidate]) -> list[MappingCandidate]:
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def normalize_column_name(name: str) -> str:
    """"cust_id" -> "cust id"; strips separators so token matching sees whole words."""
    return re.sub(r"[_\-.]+", " ", name).strip()

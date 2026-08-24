"""Group raw audit events into ingestion run summaries.

Ingestion runs are not stored in their own table - each run already writes
``INGESTION_STARTED`` / ``INGESTION_COMPLETED`` / ``INGESTION_FAILED`` audit events keyed by a
shared ``run_id`` in their payload. This module is the pure, dependency-free grouping logic so
it can be unit tested without a database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class AuditEventLike(Protocol):
    """Structural type covering the ORM ``AuditEvent`` and plain test doubles alike."""

    action: Any
    payload: dict[str, Any]
    occurred_at: datetime
    summary: str | None


def group_ingestion_events(events: list[AuditEventLike], *, limit: int = 50) -> list[dict[str, Any]]:
    """Fold started/completed/failed events into one run summary per ``run_id``.

    Events without a ``run_id`` in their payload are skipped: they predate this feature or are
    malformed, and silently dropping them is safer than guessing a grouping.

    Timestamps are normalised to ISO-8601 strings so a real ``datetime`` (from ``occurred_at``)
    and a JSON-round-tripped payload value never have to be compared directly.
    """
    runs: dict[str, dict[str, Any]] = {}

    def _iso(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value) if value else ""

    for event in events:
        run_id = event.payload.get("run_id")
        if not run_id:
            continue
        run = runs.setdefault(
            run_id,
            {
                "run_id": run_id,
                "connector": "unknown",
                "status": "RUNNING",
                "started_at": "",
                "completed_at": "",
                "assets_processed": None,
                "lineage_edges": None,
                "warnings": [],
            },
        )

        action = str(event.action.value if hasattr(event.action, "value") else event.action)
        if action == "INGESTION_STARTED":
            run["connector"] = event.payload.get("connector", run["connector"])
            run["started_at"] = run["started_at"] or _iso(event.occurred_at)
        elif action == "INGESTION_COMPLETED":
            run["connector"] = event.payload.get("connector", run["connector"])
            run["status"] = "PARTIAL" if event.payload.get("errors") else "SUCCESS"
            run["started_at"] = _iso(event.payload.get("started_at")) or run["started_at"]
            run["completed_at"] = _iso(event.payload.get("completed_at")) or _iso(event.occurred_at)
            run["assets_processed"] = event.payload.get("entities_created", 0) + event.payload.get(
                "entities_updated", 0
            )
            run["lineage_edges"] = event.payload.get(
                "lineage_edges_created", 0
            ) + event.payload.get("lineage_edges_updated", 0)
            run["warnings"] = list(event.payload.get("errors") or [])
        elif action == "INGESTION_FAILED":
            run["status"] = "FAILED"
            run["completed_at"] = run["completed_at"] or _iso(event.occurred_at)
            error = event.payload.get("error")
            if error:
                run["warnings"] = [*run["warnings"], str(error)]

    for run in runs.values():
        run["started_at"] = run["started_at"] or None
        run["completed_at"] = run["completed_at"] or None

    ordered = sorted(
        runs.values(),
        key=lambda run: run["started_at"] or run["completed_at"] or "",
        reverse=True,
    )
    return ordered[:limit]

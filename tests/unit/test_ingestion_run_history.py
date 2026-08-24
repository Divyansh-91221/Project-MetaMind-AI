"""Ingestion run-history grouping tests.

Pure function over plain event-like objects, so run assembly is verified without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.ingestion.run_history import group_ingestion_events

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class FakeEvent:
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str | None = None


NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


class TestGroupIngestionEvents:
    def test_completed_run_reports_success_and_counts(self) -> None:
        events = [
            FakeEvent(
                action="INGESTION_STARTED",
                payload={"run_id": "run-1", "connector": "demo"},
                occurred_at=NOW,
            ),
            FakeEvent(
                action="INGESTION_COMPLETED",
                payload={
                    "run_id": "run-1",
                    "connector": "demo",
                    "entities_created": 10,
                    "entities_updated": 2,
                    "lineage_edges_created": 5,
                    "lineage_edges_updated": 0,
                    "errors": [],
                    "started_at": NOW.isoformat(),
                    "completed_at": (NOW + timedelta(seconds=3)).isoformat(),
                },
                occurred_at=NOW + timedelta(seconds=3),
            ),
        ]
        runs = group_ingestion_events(events)
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "SUCCESS"
        assert run["connector"] == "demo"
        assert run["assets_processed"] == 12
        assert run["lineage_edges"] == 5
        assert run["warnings"] == []

    def test_completed_run_with_errors_is_partial(self) -> None:
        events = [
            FakeEvent(
                action="INGESTION_COMPLETED",
                payload={
                    "run_id": "run-2",
                    "connector": "postgres",
                    "entities_created": 1,
                    "entities_updated": 0,
                    "lineage_edges_created": 0,
                    "lineage_edges_updated": 0,
                    "errors": ["one column failed to normalise"],
                },
                occurred_at=NOW,
            )
        ]
        runs = group_ingestion_events(events)
        assert runs[0]["status"] == "PARTIAL"
        assert runs[0]["warnings"] == ["one column failed to normalise"]

    def test_failed_run_reports_the_error(self) -> None:
        events = [
            FakeEvent(
                action="INGESTION_STARTED",
                payload={"run_id": "run-3", "connector": "demo"},
                occurred_at=NOW,
            ),
            FakeEvent(
                action="INGESTION_FAILED",
                payload={"run_id": "run-3", "error": "connector unreachable"},
                occurred_at=NOW + timedelta(seconds=1),
            ),
        ]
        runs = group_ingestion_events(events)
        assert runs[0]["status"] == "FAILED"
        assert "connector unreachable" in runs[0]["warnings"]

    def test_started_only_run_is_still_running(self) -> None:
        events = [
            FakeEvent(
                action="INGESTION_STARTED",
                payload={"run_id": "run-4", "connector": "demo"},
                occurred_at=NOW,
            )
        ]
        runs = group_ingestion_events(events)
        assert runs[0]["status"] == "RUNNING"

    def test_events_without_run_id_are_skipped(self) -> None:
        events = [FakeEvent(action="INGESTION_STARTED", payload={"connector": "demo"})]
        assert group_ingestion_events(events) == []

    def test_runs_are_ordered_most_recent_first(self) -> None:
        older = FakeEvent(
            action="INGESTION_STARTED",
            payload={"run_id": "run-old", "connector": "demo"},
            occurred_at=NOW - timedelta(hours=1),
        )
        newer = FakeEvent(
            action="INGESTION_STARTED",
            payload={"run_id": "run-new", "connector": "demo"},
            occurred_at=NOW,
        )
        runs = group_ingestion_events([older, newer])
        assert [run["run_id"] for run in runs] == ["run-new", "run-old"]

    def test_limit_is_respected(self) -> None:
        events = [
            FakeEvent(
                action="INGESTION_STARTED",
                payload={"run_id": f"run-{i}", "connector": "demo"},
                occurred_at=NOW - timedelta(minutes=i),
            )
            for i in range(5)
        ]
        assert len(group_ingestion_events(events, limit=2)) == 2

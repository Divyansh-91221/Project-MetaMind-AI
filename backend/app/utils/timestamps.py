"""Timestamp helpers. Everything in the platform is timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dateutil import parser as _dateutil_parser


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalise a naive or offset datetime to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse a loosely formatted timestamp coming from a source system."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    try:
        return ensure_utc(_dateutil_parser.isoparse(value))
    except (ValueError, TypeError):
        return None


def age_seconds(value: datetime | None, *, reference: datetime | None = None) -> float | None:
    """Seconds elapsed since ``value``."""
    if value is None:
        return None
    return ((reference or utcnow()) - ensure_utc(value)).total_seconds()


def age_hours(value: datetime | None, *, reference: datetime | None = None) -> float | None:
    seconds = age_seconds(value, reference=reference)
    return None if seconds is None else seconds / 3600.0


def is_stale(value: datetime | None, *, sla_hours: float) -> bool:
    """Return ``True`` when the asset has not been refreshed within its SLA."""
    hours = age_hours(value)
    return hours is None or hours > sla_hours


def humanize_age(value: datetime | None) -> str:
    """Short human readable age, used in Copilot answers."""
    seconds = age_seconds(value)
    if seconds is None:
        return "unknown"
    delta = timedelta(seconds=seconds)
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = int(delta.total_seconds() // 3600)
    if hours >= 1:
        return f"{hours}h ago"
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes}m ago" if minutes else "just now"

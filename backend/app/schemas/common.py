"""Shared API schema building blocks."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    """Base for all API contracts."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, use_enum_values=False)


class PaginationParams(APIModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class Page(APIModel, Generic[T]):
    """Envelope for paginated collections."""

    items: list[T]
    total: int = Field(description="Total number of matching records.")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class HealthStatus(APIModel):
    status: str
    version: str
    environment: str
    postgres: bool
    graph: bool
    checked_at: datetime


class OperationResult(APIModel):
    """Generic acknowledgement for mutating endpoints."""

    success: bool = True
    message: str = ""
    affected: int = 0

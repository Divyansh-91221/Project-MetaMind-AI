"""HTTP layer. Routes are thin: validate, delegate to a service, return a schema."""

from app.api.router import api_router

__all__ = ["api_router"]

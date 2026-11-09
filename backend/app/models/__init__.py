"""ORM models. Import every model here so Alembic sees the full metadata."""

from app.models.patient import Patient

__all__ = ["Patient"]

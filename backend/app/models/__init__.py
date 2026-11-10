"""ORM models. Import every model here so Alembic sees the full metadata."""

from app.models.audit import AuditLog
from app.models.consent import ConsentRecord
from app.models.patient import Patient

__all__ = ["AuditLog", "ConsentRecord", "Patient"]

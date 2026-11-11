"""Allow the application role to delete documents (M12 cascade deletion).

Chunks (with embeddings), lab results, medications and citations cascade from documents via
foreign keys; audit_log keeps no foreign key and stays append-only.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT DELETE ON documents TO rakshak_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON documents FROM rakshak_app")

"""Enable pgvector and add chunk embeddings.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Nullable: chunks created before M6 have no embedding until their document is reprocessed.
    op.add_column("chunks", sa.Column("embedding", Vector(768), nullable=True))
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")

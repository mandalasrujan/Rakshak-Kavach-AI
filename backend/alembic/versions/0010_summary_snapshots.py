"""Summary snapshots (M13): versioned, approved snapshots under RLS

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11 11:23:58.406288
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PATIENT_CONTEXT = "NULLIF(current_setting('app.patient_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "summary_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_document_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_summary_snapshots_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_summary_snapshots")),
        sa.UniqueConstraint(
            "patient_id", "version", name="uq_summary_snapshots_patient_id_version"
        ),
    )
    op.create_index(
        op.f("ix_summary_snapshots_patient_id"), "summary_snapshots", ["patient_id"], unique=False
    )

    # No DELETE grant: snapshots are only ever added, approved or invalidated (content purged).
    op.execute("GRANT SELECT, INSERT, UPDATE ON summary_snapshots TO rakshak_app")
    op.execute("ALTER TABLE summary_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY patient_isolation ON summary_snapshots "
        f"USING (patient_id = {PATIENT_CONTEXT}) WITH CHECK (patient_id = {PATIENT_CONTEXT})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_isolation ON summary_snapshots")
    op.execute("REVOKE ALL ON summary_snapshots FROM rakshak_app")
    op.drop_index(op.f("ix_summary_snapshots_patient_id"), table_name="summary_snapshots")
    op.drop_table("summary_snapshots")

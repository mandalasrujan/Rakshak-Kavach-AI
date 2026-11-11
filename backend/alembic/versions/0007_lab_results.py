"""Create lab_results (normalized, with provenance) under RLS.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PATIENT_CONTEXT = "NULLIF(current_setting('app.patient_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "lab_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("raw_unit", sa.Text(), nullable=False),
        sa.Column("raw_reference", sa.Text(), nullable=False),
        sa.Column("test_code", sa.String(length=32), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("canonical_value", sa.Float(), nullable=True),
        sa.Column("canonical_unit", sa.String(length=32), nullable=True),
        sa.Column("ref_low", sa.Float(), nullable=True),
        sa.Column("ref_high", sa.Float(), nullable=True),
        sa.Column("canonical_ref_low", sa.Float(), nullable=True),
        sa.Column("canonical_ref_high", sa.Float(), nullable=True),
        sa.Column("collected_on", sa.Date(), nullable=True),
        sa.Column("reported_on", sa.Date(), nullable=True),
        sa.Column("date_ambiguous", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("dictionary_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_lab_results_chunk_id_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_lab_results_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_lab_results_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lab_results")),
        sa.UniqueConstraint("chunk_id", name=op.f("uq_lab_results_chunk_id")),
    )
    op.create_index(op.f("ix_lab_results_document_id"), "lab_results", ["document_id"])
    op.create_index(
        "ix_lab_results_patient_id_test_code", "lab_results", ["patient_id", "test_code"]
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON lab_results TO rakshak_app")
    op.execute("ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY patient_isolation ON lab_results "
        f"USING (patient_id = {PATIENT_CONTEXT}) WITH CHECK (patient_id = {PATIENT_CONTEXT})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_isolation ON lab_results")
    op.execute("REVOKE ALL ON lab_results FROM rakshak_app")
    op.drop_index("ix_lab_results_patient_id_test_code", table_name="lab_results")
    op.drop_index(op.f("ix_lab_results_document_id"), table_name="lab_results")
    op.drop_table("lab_results")

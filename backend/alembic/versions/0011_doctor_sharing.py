"""Doctor sharing (M14): share grants and doctor sessions under RLS.

A doctor has no patient context until a valid token hash is resolved. Two SECURITY DEFINER
functions do exactly that and nothing else: given a SHA-256 token hash they return the owner's
patient_id (or NULL). Every later read runs under that patient's RLS context.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-11 11:26:40.102822
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PATIENT_CONTEXT = "NULLIF(current_setting('app.patient_id', true), '')::uuid"
TABLES = ("share_grants", "doctor_sessions")
LOOKUPS = {"share_grant_owner": "share_grants", "doctor_session_owner": "doctor_sessions"}


def upgrade() -> None:
    op.create_table(
        "share_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("pin_hash", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_pin_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope IN ('summary_only', 'full_records')", name=op.f("ck_share_grants_scope")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_share_grants_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["summary_snapshots.id"],
            name=op.f("fk_share_grants_snapshot_id_summary_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_grants")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_share_grants_token_hash")),
    )
    op.create_index(
        op.f("ix_share_grants_patient_id"), "share_grants", ["patient_id"], unique=False
    )
    op.create_index(
        op.f("ix_share_grants_snapshot_id"), "share_grants", ["snapshot_id"], unique=False
    )
    op.create_table(
        "doctor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("share_grant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("declared_name", sa.String(length=120), nullable=True),
        sa.Column("declared_reg_no", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_doctor_sessions_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["share_grant_id"],
            ["share_grants.id"],
            name=op.f("fk_doctor_sessions_share_grant_id_share_grants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_doctor_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_doctor_sessions_patient_id"), "doctor_sessions", ["patient_id"], unique=False
    )
    op.create_index(
        op.f("ix_doctor_sessions_share_grant_id"),
        "doctor_sessions",
        ["share_grant_id"],
        unique=False,
    )

    for table in TABLES:  # no DELETE: grants are revoked, sessions are ended
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO rakshak_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY patient_isolation ON {table} "
            f"USING (patient_id = {PATIENT_CONTEXT}) WITH CHECK (patient_id = {PATIENT_CONTEXT})"
        )
    for function, table in LOOKUPS.items():
        op.execute(
            f"""
            CREATE FUNCTION {function}(p_token_hash text) RETURNS uuid
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
                SELECT patient_id FROM {table} WHERE token_hash = p_token_hash
            $$
            """  # noqa: S608 (constant identifiers)
        )
        op.execute(f"REVOKE ALL ON FUNCTION {function}(text) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function}(text) TO rakshak_app")


def downgrade() -> None:
    for function in LOOKUPS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}(text)")
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS patient_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM rakshak_app")
    op.drop_index(op.f("ix_doctor_sessions_share_grant_id"), table_name="doctor_sessions")
    op.drop_index(op.f("ix_doctor_sessions_patient_id"), table_name="doctor_sessions")
    op.drop_table("doctor_sessions")
    op.drop_index(op.f("ix_share_grants_snapshot_id"), table_name="share_grants")
    op.drop_index(op.f("ix_share_grants_patient_id"), table_name="share_grants")
    op.drop_table("share_grants")

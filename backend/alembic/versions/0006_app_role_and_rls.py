"""Non-owner application role, least-privilege grants and row-level security.

The app connects as a LOGIN role that is a member of `rakshak_app` (created by
`python -m app.db.app_role`). That role owns nothing, so the patient_isolation policies apply
to it. Migrations run as the table owner, which bypasses RLS (FORCE is intentionally not set).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_GROUP_ROLE = "rakshak_app"
PATIENT_CONTEXT = "NULLIF(current_setting('app.patient_id', true), '')::uuid"
RLS_TABLES = ("consent_records", "documents", "chunks", "audit_log")
GRANTS = {
    "patients": "SELECT, INSERT, UPDATE",
    "consent_records": "SELECT, INSERT, UPDATE",
    "documents": "SELECT, INSERT, UPDATE",
    "chunks": "SELECT, INSERT, DELETE",
    "audit_log": "SELECT, INSERT",  # append-only by privilege as well as by trigger
}


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_GROUP_ROLE}') THEN
                CREATE ROLE {APP_GROUP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """  # noqa: S608 (constant role name, no user input)
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_GROUP_ROLE}")
    for table, privileges in GRANTS.items():
        op.execute(f"GRANT {privileges} ON {table} TO {APP_GROUP_ROLE}")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY patient_isolation ON {table} "
            f"USING (patient_id = {PATIENT_CONTEXT}) "
            f"WITH CHECK (patient_id = {PATIENT_CONTEXT})"
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS patient_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in GRANTS:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_GROUP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_GROUP_ROLE}")
    # The cluster-wide role is kept: other databases in the cluster may still use it.

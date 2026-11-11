"""Agent chats, RLS-protected LangGraph checkpoints, citations and medications (M10)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11 09:34:16.675962
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PATIENT_CONTEXT = "NULLIF(current_setting('app.patient_id', true), '')::uuid"
GRANTS = {
    "chats": "SELECT, INSERT, DELETE",
    "message_citations": "SELECT, INSERT, DELETE",
    "chat_checkpoints": "SELECT, INSERT, UPDATE, DELETE",
    "chat_checkpoint_writes": "SELECT, INSERT, UPDATE, DELETE",
    "medications": "SELECT, INSERT, DELETE",
}


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_chats_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chats")),
    )
    op.create_index(op.f("ix_chats_patient_id"), "chats", ["patient_id"], unique=False)
    op.create_table(
        "chat_checkpoint_writes",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=255), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_chat_checkpoint_writes_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_chat_checkpoint_writes_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "chat_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
            name=op.f("pk_chat_checkpoint_writes"),
        ),
    )
    op.create_index(
        op.f("ix_chat_checkpoint_writes_patient_id"),
        "chat_checkpoint_writes",
        ["patient_id"],
        unique=False,
    )
    op.create_table(
        "chat_checkpoints",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=255), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_type", sa.String(length=32), nullable=False),
        sa.Column("checkpoint", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_type", sa.String(length=32), nullable=False),
        sa.Column("metadata", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_chat_checkpoints_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_chat_checkpoints_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "chat_id", "checkpoint_ns", "checkpoint_id", name=op.f("pk_chat_checkpoints")
        ),
    )
    op.create_index(
        op.f("ix_chat_checkpoints_patient_id"), "chat_checkpoints", ["patient_id"], unique=False
    )
    op.create_table(
        "message_citations",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_message_citations_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_message_citations_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_message_citations_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("chat_id", "document_id", name=op.f("pk_message_citations")),
    )
    op.create_index(
        op.f("ix_message_citations_document_id"), "message_citations", ["document_id"], unique=False
    )
    op.create_table(
        "medications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("dose", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("duration", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_medications_chunk_id_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_medications_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_medications_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medications")),
    )
    op.create_index(op.f("ix_medications_chunk_id"), "medications", ["chunk_id"], unique=False)
    op.create_index(
        op.f("ix_medications_document_id"), "medications", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_medications_patient_id"), "medications", ["patient_id"], unique=False)

    for table, privileges in GRANTS.items():
        op.execute(f"GRANT {privileges} ON {table} TO rakshak_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY patient_isolation ON {table} "
            f"USING (patient_id = {PATIENT_CONTEXT}) WITH CHECK (patient_id = {PATIENT_CONTEXT})"
        )


def downgrade() -> None:
    for table in GRANTS:
        op.execute(f"DROP POLICY IF EXISTS patient_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM rakshak_app")
    op.drop_index(op.f("ix_medications_patient_id"), table_name="medications")
    op.drop_index(op.f("ix_medications_document_id"), table_name="medications")
    op.drop_index(op.f("ix_medications_chunk_id"), table_name="medications")
    op.drop_table("medications")
    op.drop_index(op.f("ix_message_citations_document_id"), table_name="message_citations")
    op.drop_table("message_citations")
    op.drop_index(op.f("ix_chat_checkpoints_patient_id"), table_name="chat_checkpoints")
    op.drop_table("chat_checkpoints")
    op.drop_index(op.f("ix_chat_checkpoint_writes_patient_id"), table_name="chat_checkpoint_writes")
    op.drop_table("chat_checkpoint_writes")
    op.drop_index(op.f("ix_chats_patient_id"), table_name="chats")
    op.drop_table("chats")

"""Text chunks extracted from documents (PROJECT_SPEC.md section 4: chunks).

`embedding` and `embedding_model` are added with pgvector in M6.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

NARRATIVE = "narrative"
LAB_ROW = "lab_row"


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (CheckConstraint("kind IN ('narrative', 'lab_row')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

"""Imports: Excel or CSV files of people, work, assignments or requests.

- ImportBatch: one uploaded file. It is previewed first (every row is run through the real services
  in a transaction that is then rolled back, so the preview finds exactly the errors a real import
  would), and committed later by the same person. A commit runs the file again, so it reflects any
  change made since the preview. `results` holds the outcome of every row.
- ExternalKey: the ID a record has in the spreadsheet it came from (e.g. "INI-001"), so the same file
  imported again updates the same records, and rows can refer to each other (a milestone's parent).
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel, utcnow
from app.extensions import db

MAX_FILE_BYTES = 5 * 1024 * 1024


class ImportBatch(BaseModel):
    __tablename__ = "import_batches"

    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="add")  # add | update
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary(length=MAX_FILE_BYTES), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="previewed")  # previewed | committed | discarded
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExternalKey(db.Model):
    __tablename__ = "external_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "external_id", name="uq_external_keys_entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

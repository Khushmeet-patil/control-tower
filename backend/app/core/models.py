"""BaseModel: the shared columns every business table inherits."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Columns managed by the platform itself; never accepted from user input and not audited field-by-field.
SYSTEM_FIELDS = frozenset({
    "id", "tenant_id", "created_at", "created_by_id", "updated_at", "updated_by_id",
    "version", "is_deleted", "deleted_at",
})


class BaseModel(db.Model):
    """Abstract base: id, tenant, who/when created/updated, optimistic version, soft delete."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, sort_order=-2)

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("tenants.id"), nullable=False, index=True, sort_order=-1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, sort_order=100)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True, sort_order=100)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False, sort_order=100)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True, sort_order=100)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, sort_order=100)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True, sort_order=100)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, sort_order=100)

    @declared_attr.directive
    def __mapper_args__(cls):
        # SQLAlchemy bumps `version` on every UPDATE and raises StaleDataError on a concurrent edit.
        return {"version_id_col": cls.version}

    # Business columns of this model (excludes system fields).
    @classmethod
    def business_fields(cls) -> list[str]:
        return [c.key for c in cls.__table__.columns if c.key not in SYSTEM_FIELDS]

    def get_value(self, field: str):
        return getattr(self, field)

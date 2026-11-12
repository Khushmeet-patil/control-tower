"""Lookups: the configurable lists behind every coloured value (status, priority, item type, …).

- LookupType: one list (e.g. "Priority"). Built-in lists are `is_system`: they cannot be retired
  and their code never changes, because the platform refers to them by code.
- LookupValue: one entry in a list, with a label, a colour, an order and an active flag.
  Values are never deleted. Retiring a value (is_active = False) hides it from pickers, but old
  records that use it still show its label and colour.

Admins edit these tables as a DRAFT; the rest of the platform reads the published settings
version (see app.modules.config).
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel


class LookupType(BaseModel):
    __tablename__ = "lookup_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_lookup_types_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LookupValue(BaseModel):
    __tablename__ = "lookup_values"
    __table_args__ = (UniqueConstraint("lookup_type_id", "code", name="uq_lookup_values_type_code"),)

    lookup_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_types.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#94A3B8")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Built-in values the platform relies on (e.g. health Red/Amber/Grey/Green): cannot be retired.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

"""Organisation structure.

- Tenant: the organisation using the platform.
- OrgUnitType: configurable unit levels (Company, Division, Department, Team, …).
- OrgUnit: the ADMINISTRATIVE hierarchy (reporting structure). Each unit may have a head.
- Function: the FUNCTIONAL hierarchy (discipline: QA, Development, Finance, …). Each has a lead.
Both trees use closure tables (see app.core.tree).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel, utcnow
from app.core.tree import make_closure_model
from app.extensions import db


class Tenant(db.Model):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OrgUnitType(BaseModel):
    __tablename__ = "org_unit_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_org_unit_types_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class OrgUnit(BaseModel):
    __tablename__ = "org_units"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_org_units_tenant_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_type_id: Mapped[int] = mapped_column(ForeignKey("org_unit_types.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True, index=True)
    head_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_org_units_head_id_users"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    unit_type = relationship(OrgUnitType, lazy="joined")
    head = relationship("User", foreign_keys=[head_id], lazy="joined")


class Function(BaseModel):
    __tablename__ = "functions"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_functions_tenant_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_functions_lead_id_users"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead = relationship("User", foreign_keys=[lead_id], lazy="joined")


OrgUnitClosure = make_closure_model("OrgUnitClosure", "org_unit_closure", "org_units")
FunctionClosure = make_closure_model("FunctionClosure", "function_closure", "functions")

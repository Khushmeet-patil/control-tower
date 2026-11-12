"""Roles and permissions — stored as data, editable by admins.

A Role bundles permission codes (what you may DO) and a scope (what you may SEE):
- all  : the whole organisation
- unit : your own unit and every unit below it
- own  : only yourself and things assigned to you
People get roles through UserRole. Extra visibility comes from the structure itself
(unit heads see their unit tree, functional leads see their function's people, managers
see their reporting line) — see app.modules.access.scope.
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel
from app.extensions import db

SCOPES = ("own", "unit", "all")  # ordered from narrowest to widest


class Role(BaseModel):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_roles_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False, default="own")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Given automatically to new people who are added without any role.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    permission_rows = relationship("RolePermission", cascade="all, delete-orphan", lazy="selectin")

    @property
    def permission_codes(self) -> list[str]:
        return sorted(p.permission_code for p in self.permission_rows)


class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(String(80), primary_key=True)


class UserRole(db.Model):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True, index=True)

"""People (user accounts).

Each person sits in BOTH hierarchies:
- unit_id      → administrative hierarchy (which unit/team they belong to)
- manager_id   → reports-to line manager
- function_id  → functional hierarchy (their discipline)
Roles (app.modules.access) decide what they may do; scope decides what they may see.
"""
from datetime import datetime

from flask import current_app, g, has_request_context
from flask_login import UserMixin
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.models import BaseModel


class User(UserMixin, BaseModel):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employee_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True, index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), nullable=True, index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Values of admin-defined custom fields ({field code: value}); see app.modules.config.custom_fields.
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    unit = relationship("OrgUnit", foreign_keys=[unit_id], lazy="joined")
    function = relationship("Function", foreign_keys=[function_id], lazy="joined")
    manager = relationship("User", remote_side="User.id", foreign_keys=[manager_id], lazy="joined", join_depth=1)

    def set_password(self, raw: str) -> None:
        method = current_app.config.get("PASSWORD_HASH_METHOD", "scrypt")
        self.password_hash = generate_password_hash(raw, method=method)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    # ---- access (cached per request)
    def _access(self):
        from app.modules.access.scope import resolve_access

        if has_request_context():
            cache = g.setdefault("_access_cache", {})
            if self.id not in cache:
                cache[self.id] = resolve_access(self)
            return cache[self.id]
        return resolve_access(self)

    def permission_codes(self) -> set[str]:
        return self._access().permissions

    @property
    def scope(self) -> str:
        return self._access().scope

    @property
    def initials(self) -> str:
        parts = self.full_name.split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"

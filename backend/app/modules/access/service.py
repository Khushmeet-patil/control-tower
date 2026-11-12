"""Roles: which permissions they grant and how far their scope reaches. Edited by admins."""
from sqlalchemy import func, select

from app.core.command import CommandService
from app.core.errors import Conflict, ValidationFailed
from app.extensions import db
from app.modules.access.catalog import PERMISSION_CODES
from app.modules.access.models import SCOPES, Role, RolePermission, UserRole
from app.modules.access.scope import clear_access_cache


class RoleService(CommandService):
    model = Role
    entity_type = "role"
    permissions = {"create": "roles.manage", "update": "roles.manage", "delete": "roles.manage"}
    protected_fields = frozenset({"is_system"})
    extra_fields = frozenset({"permission_codes"})

    def read_value(self, obj, field):
        if field == "permission_codes":
            return sorted(db.session.scalars(
                select(RolePermission.permission_code).where(RolePermission.role_id == obj.id)))
        return super().read_value(obj, field)

    def _validate(self, data, exclude_id=None):
        if "scope" in data and data["scope"] not in SCOPES:
            raise ValidationFailed("Choose a valid scope", {"field": "scope"})
        if "permission_codes" in data:
            data["permission_codes"] = sorted(set(data["permission_codes"] or []))
            unknown = set(data["permission_codes"]) - PERMISSION_CODES
            if unknown:
                raise ValidationFailed("Unknown permission", {"field": "permission_codes", "codes": sorted(unknown)})
        if "code" in data:
            stmt = select(Role.id).where(Role.tenant_id == self.tenant_id, Role.code == data["code"],
                                         Role.is_deleted.is_(False))
            if exclude_id:
                stmt = stmt.where(Role.id != exclude_id)
            if db.session.scalar(stmt):
                raise ValidationFailed("This role code is already used", {"field": "code"})

    def validate_create(self, data):
        self._validate(data)
        if data.get("is_default"):
            self._clear_other_defaults()

    def _clear_other_defaults(self, keep_id=None):
        """Only one default role at a time."""
        for role in db.session.scalars(select(Role).where(
                Role.tenant_id == self.tenant_id, Role.is_default.is_(True), Role.id != (keep_id or 0))):
            role.is_default = False
            self._audit(role.id, "update", field="is_default", old=True, new=False,
                        reason="Another role became the default")

    def validate_update(self, obj, changes):
        if obj.is_system and "code" in changes and changes["code"] != obj.code:
            raise ValidationFailed("The code of a built-in role cannot change", {"field": "code"})
        self._validate(changes, obj.id)
        if changes.get("is_default") and not obj.is_default:
            self._clear_other_defaults(obj.id)

    def validate_delete(self, obj):
        if obj.is_system:
            raise Conflict("Built-in roles cannot be deleted")
        if self.assigned_count(obj.id):
            raise Conflict("Remove this role from everyone who has it first")

    def apply_update(self, obj, changes):
        changes = dict(changes)
        if "permission_codes" in changes:
            obj.permission_rows = [RolePermission(permission_code=c) for c in changes.pop("permission_codes")]
            clear_access_cache()
        super().apply_update(obj, changes)
        if "scope" in changes:
            clear_access_cache()

    @staticmethod
    def assigned_count(role_id):
        return db.session.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id))

    def list_all(self):
        roles = db.session.scalars(self.base_query().order_by(Role.name)).all()
        return [self.serialize(r) for r in roles]

    def serialize(self, r):
        return {
            "id": r.id, "code": r.code, "name": r.name, "description": r.description, "scope": r.scope,
            "is_system": r.is_system, "is_default": r.is_default, "permission_codes": r.permission_codes,
            "people_count": self.assigned_count(r.id), "version": r.version,
        }

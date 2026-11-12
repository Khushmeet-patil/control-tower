"""People: create, edit, place in both hierarchies, assign roles — all within the actor's scope."""
from sqlalchemy import delete, select

from app.core.command import CommandService
from app.core.errors import Forbidden, ValidationFailed
from app.core.filters import apply_filters
from app.core.pagination import paginate
from app.core.permissions import actor_can
from app.core.tree import descendant_ids
from app.extensions import db
from app.modules.access.models import Role, UserRole
from app.modules.access.scope import clear_access_cache, is_global, managed_unit_ids, person_visibility_clause
from app.modules.auth.models import User
from app.modules.config.custom_fields import apply_custom_filters, person_refs
from app.modules.organisation.models import Function, FunctionClosure, OrgUnit, OrgUnitClosure

MIN_PASSWORD = 8

FILTERABLE = {
    "full_name": User.full_name, "email": User.email, "job_title": User.job_title,
    "unit_id": User.unit_id, "function_id": User.function_id, "manager_id": User.manager_id,
    "is_active": User.is_active, "updated_at": User.updated_at,
}
SEARCH = [User.full_name, User.email, User.job_title, User.employee_code]


def _ref(obj, label="name"):
    return {"id": obj.id, label: getattr(obj, label)} if obj else None


class PersonService(CommandService):
    model = User
    entity_type = "person"
    permissions = {"create": "people.manage", "update": "people.manage", "delete": "people.manage"}
    protected_fields = frozenset({"password_hash", "last_login_at"})
    extra_fields = frozenset({"role_ids"})
    custom_entity = "person"

    def _accepted_inputs(self):
        return {"password"}

    # ------------------------------------------------------------------ reads
    def base_query(self):
        stmt = super().base_query()
        clause = person_visibility_clause(self.actor)
        return stmt if clause is None else stmt.where(clause)

    def list(self, params):
        params = dict(params)
        stmt = self.base_query()
        # Include everyone in sub-units/sub-functions when asked (e.g. "all of Engineering").
        if params.pop("include_descendants", "") in ("1", "true"):
            if unit_id := params.pop("unit_id", None):
                stmt = stmt.where(User.unit_id.in_(descendant_ids(OrgUnitClosure, [int(unit_id)])))
            if function_id := params.pop("function_id", None):
                stmt = stmt.where(User.function_id.in_(descendant_ids(FunctionClosure, [int(function_id)])))
        if role_id := params.pop("role_id", None):
            stmt = stmt.where(User.id.in_(select(UserRole.user_id).where(UserRole.role_id == int(role_id))))
        stmt = apply_custom_filters(stmt, User.custom_fields, params, self.tenant_id, self.custom_entity)
        stmt = apply_filters(stmt, params, FILTERABLE, SEARCH, default_sort="full_name")
        return paginate(stmt, params, self.serialize)

    def serialize(self, u: User) -> dict:
        return {
            "id": u.id, "full_name": u.full_name, "initials": u.initials, "email": u.email,
            "job_title": u.job_title, "employee_code": u.employee_code,
            "unit": _ref(u.unit), "unit_id": u.unit_id,
            "function": _ref(u.function), "function_id": u.function_id,
            "manager": _ref(u.manager, "full_name"), "manager_id": u.manager_id,
            "roles": [{"id": r.id, "name": r.name} for r in self._roles_of(u.id)],
            "role_ids": self.read_value(u, "role_ids"),
            "is_admin": u.is_admin, "is_active": u.is_active,
            "custom_fields": u.custom_fields or {},
            "custom_people": person_refs(self.tenant_id, self.custom_entity, u.custom_fields),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "version": u.version,
        }

    @staticmethod
    def _roles_of(user_id):
        return db.session.scalars(select(Role).join(UserRole, UserRole.role_id == Role.id)
                                  .where(UserRole.user_id == user_id).order_by(Role.name)).all()

    def read_value(self, obj, field):
        if field == "role_ids":
            return sorted(db.session.scalars(select(UserRole.role_id).where(UserRole.user_id == obj.id)))
        return super().read_value(obj, field)

    def audit_value(self, field, value):
        return "••••••" if field == "password_hash" else value

    # ------------------------------------------------------------------ validation
    def _check_ref(self, model, ref_id, field):
        if ref_id is None:
            return
        obj = db.session.get(model, ref_id)
        if obj is None or obj.tenant_id != self.tenant_id or obj.is_deleted:
            raise ValidationFailed("Selected value not found", {"field": field})

    def _check_unit_scope(self, unit_id):
        managed = managed_unit_ids(self.actor)
        if managed is not None and unit_id not in managed:
            raise Forbidden("You can only place people in units within your own area")

    def _check_manager(self, person_id, manager_id):
        if manager_id is None:
            return
        if manager_id == person_id:
            raise ValidationFailed("A person cannot report to themselves", {"field": "manager_id"})
        current, seen = manager_id, set()
        while current is not None and current not in seen:  # walk up: no reporting loops
            if current == person_id:
                raise ValidationFailed("This would create a reporting loop", {"field": "manager_id"})
            seen.add(current)
            current = db.session.scalar(select(User.manager_id).where(User.id == current))

    def _check_roles(self, role_ids):
        if not actor_can(self.actor, "roles.manage"):
            raise Forbidden("You do not have permission to assign roles")
        ids = set(role_ids or [])
        found = set(db.session.scalars(select(Role.id).where(
            Role.id.in_(ids), Role.tenant_id == self.tenant_id, Role.is_deleted.is_(False))))
        if found != ids:
            raise ValidationFailed("Unknown role selected", {"field": "role_ids"})

    def _check_admin_flag(self):
        if self.actor is not None and not self.actor.is_admin:
            raise Forbidden("Only administrators can grant administrator access")

    def validate_create(self, data):
        data["email"] = data["email"].strip().lower()
        if db.session.scalar(select(User.id).where(User.email == data["email"])):
            raise ValidationFailed("A person with this email already exists", {"field": "email"})
        if len(data.get("password") or "") < MIN_PASSWORD:
            raise ValidationFailed(f"Password must be at least {MIN_PASSWORD} characters", {"field": "password"})
        self._check_ref(OrgUnit, data.get("unit_id"), "unit_id")
        self._check_ref(Function, data.get("function_id"), "function_id")
        self._check_ref(User, data.get("manager_id"), "manager_id")
        if not is_global(self.actor):
            self._check_unit_scope(data.get("unit_id"))
        if data.get("role_ids"):
            self._check_roles(data["role_ids"])
        else:
            default = db.session.scalar(select(Role.id).where(
                Role.tenant_id == self.tenant_id, Role.is_default.is_(True), Role.is_deleted.is_(False)))
            data["role_ids"] = [default] if default else []
        if data.get("is_admin"):
            self._check_admin_flag()

    def validate_update(self, obj, changes):
        if "email" in changes:
            changes["email"] = changes["email"].strip().lower()
            if db.session.scalar(select(User.id).where(User.email == changes["email"], User.id != obj.id)):
                raise ValidationFailed("A person with this email already exists", {"field": "email"})
        if "unit_id" in changes:
            self._check_ref(OrgUnit, changes["unit_id"], "unit_id")
            if not is_global(self.actor):
                self._check_unit_scope(changes["unit_id"])
        if "function_id" in changes:
            self._check_ref(Function, changes["function_id"], "function_id")
        if "manager_id" in changes:
            self._check_ref(User, changes["manager_id"], "manager_id")
            self._check_manager(obj.id, changes["manager_id"])
        if "role_ids" in changes:
            changes["role_ids"] = sorted(set(changes["role_ids"] or []))
            if changes["role_ids"] != self.read_value(obj, "role_ids"):
                self._check_roles(changes["role_ids"])
        if "is_admin" in changes and changes["is_admin"] != obj.is_admin:
            self._check_admin_flag()
        is_self = self.actor is not None and obj.id == self.actor.id
        if is_self and (changes.get("is_active") is False or changes.get("is_admin") is False):
            raise ValidationFailed("You cannot deactivate yourself or remove your own administrator access")

    # ------------------------------------------------------------------ writes
    def apply_create(self, data):
        password = data.pop("password")
        user = User(**data)
        user.set_password(password)
        return user

    def apply_update(self, obj, changes):
        changes = dict(changes)
        if "role_ids" in changes:
            role_ids = changes.pop("role_ids") or []
            db.session.execute(delete(UserRole).where(UserRole.user_id == obj.id))
            db.session.add_all(UserRole(user_id=obj.id, role_id=r) for r in role_ids)
            clear_access_cache()
        super().apply_update(obj, changes)

    def reset_password(self, person_id: int, new_password: str, reason: str | None = None):
        person = self.get(person_id)
        is_self = self.actor is not None and self.actor.id == person.id
        if not is_self and not actor_can(self.actor, "people.manage"):
            raise Forbidden("You do not have permission to reset this password")
        if len(new_password or "") < MIN_PASSWORD:
            raise ValidationFailed(f"Password must be at least {MIN_PASSWORD} characters", {"field": "password"})
        with self._transaction():
            person.set_password(new_password)
            person.updated_by_id = self._actor_id
            self._audit(person.id, "password_reset", reason=reason)
        return person



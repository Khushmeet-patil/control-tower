"""Administrative units and functions. Both are trees built on app.core.tree.TreeService."""
from sqlalchemy import func, select

from app.core.errors import Conflict, Forbidden, ValidationFailed
from app.core.tree import TreeService, ancestor_ids
from app.extensions import db
from app.modules.access.scope import (
    is_global, managed_unit_ids, person_visibility_clause, unit_visibility_clause, visible_unit_ids)
from app.modules.auth.models import User
from app.modules.organisation.models import Function, FunctionClosure, OrgUnit, OrgUnitClosure, OrgUnitType


def _person_ref(user):
    return {"id": user.id, "full_name": user.full_name, "initials": user.initials} if user else None


def _check_person(tenant_id, person_id, field):
    if person_id is None:
        return
    person = db.session.get(User, person_id)
    if person is None or person.tenant_id != tenant_id or person.is_deleted:
        raise ValidationFailed("Person not found", {"field": field})


def _member_counts(column, ids, actor=None):
    """People per unit/function. With an actor, counts only people that actor may see,
    so numbers always match the lists they lead to."""
    if not ids:
        return {}
    stmt = select(column, func.count()).where(column.in_(ids), User.is_deleted.is_(False))
    if actor is not None and (clause := person_visibility_clause(actor)) is not None:
        stmt = stmt.where(clause)
    return dict(db.session.execute(stmt.group_by(column)).all())


def _check_unique_code(model, tenant_id, code, exclude_id=None):
    if not code:
        return
    stmt = select(model.id).where(model.tenant_id == tenant_id, model.code == code, model.is_deleted.is_(False))
    if exclude_id:
        stmt = stmt.where(model.id != exclude_id)
    if db.session.scalar(stmt):
        raise ValidationFailed("This code is already used", {"field": "code"})


# ---------------------------------------------------------------------- unit types
def list_unit_types(tenant_id):
    stmt = select(OrgUnitType).where(OrgUnitType.tenant_id == tenant_id, OrgUnitType.is_deleted.is_(False))
    return [{"id": t.id, "code": t.code, "name": t.name, "color": t.color, "sort_order": t.sort_order}
            for t in db.session.scalars(stmt.order_by(OrgUnitType.sort_order, OrgUnitType.name))]


# ---------------------------------------------------------------------- administrative units
class UnitService(TreeService):
    model = OrgUnit
    closure = OrgUnitClosure
    entity_type = "org_unit"
    permissions = {"create": "org.manage", "update": "org.manage", "delete": "org.manage"}

    def base_query(self):
        stmt = super().base_query()
        clause = unit_visibility_clause(self.actor)
        return stmt if clause is None else stmt.where(clause)

    # -- scope rules for people who do not see the whole organisation
    def _visible(self):
        return managed_unit_ids(self.actor)

    def _is_scope_root(self, unit):
        """The top unit of the actor's area: they may edit it but not move or delete it."""
        managed = self._visible()
        return managed is not None and unit.parent_id not in managed

    def _check_type(self, type_id):
        t = db.session.get(OrgUnitType, type_id) if type_id else None
        if t is None or t.tenant_id != self.tenant_id or t.is_deleted:
            raise ValidationFailed("Choose a valid unit type", {"field": "unit_type_id"})

    def validate_create(self, data):
        super().validate_create(data)
        self._check_type(data.get("unit_type_id"))
        _check_person(self.tenant_id, data.get("head_id"), "head_id")
        _check_unique_code(OrgUnit, self.tenant_id, data.get("code"))
        visible = self._visible()
        if visible is not None and data.get("parent_id") not in visible:
            raise Forbidden("You can only add units inside your own part of the organisation")

    def validate_update(self, obj, changes):
        super().validate_update(obj, changes)
        managed = self._visible()
        if managed is not None and obj.id not in managed:
            raise Forbidden("You can only edit units within your own area")
        if "unit_type_id" in changes:
            self._check_type(changes["unit_type_id"])
        if "head_id" in changes:
            _check_person(self.tenant_id, changes["head_id"], "head_id")
        if "code" in changes:
            _check_unique_code(OrgUnit, self.tenant_id, changes["code"], obj.id)
        if "parent_id" in changes and changes["parent_id"] != obj.parent_id:
            visible = self._visible()
            if visible is not None and (self._is_scope_root(obj) or changes["parent_id"] not in visible):
                raise Forbidden("You can only move units within your own part of the organisation")
            if changes["parent_id"] is None and not is_global(self.actor):
                raise Forbidden("Only organisation-wide administrators can create top-level units")

    def validate_delete(self, obj):
        managed = self._visible()
        if managed is not None and obj.id not in managed:
            raise Forbidden("You can only delete units within your own area")
        if self._is_scope_root(obj):
            raise Forbidden("You cannot delete the top unit of your own area")
        super().validate_delete(obj)
        if _member_counts(User.unit_id, [obj.id]).get(obj.id):
            raise Conflict("Move the people in this unit to another unit first")

    # -- reads
    def list_all(self):
        units = db.session.scalars(self.base_query().order_by(OrgUnit.name)).all()
        counts = _member_counts(User.unit_id, [u.id for u in units], self.actor)
        return [self.serialize(u, counts.get(u.id, 0)) for u in units]

    def detail(self, unit_id):
        unit = self.get(unit_id)
        path = [db.session.get(OrgUnit, i) for i in ancestor_ids(OrgUnitClosure, unit.id)]
        visible = visible_unit_ids(self.actor)
        data = self.serialize(unit, _member_counts(User.unit_id, [unit.id], self.actor).get(unit.id, 0))
        data["path"] = [{"id": p.id, "name": p.name, "visible": visible is None or p.id in visible} for p in path]
        data["child_count"] = self.child_count(unit)
        managed = self._visible()
        data["can_manage"] = managed is None or unit.id in managed
        data["can_move_or_delete"] = data["can_manage"] and not self._is_scope_root(unit)
        return data

    @staticmethod
    def serialize(u, member_count=0):
        t = u.unit_type
        return {
            "id": u.id, "name": u.name, "code": u.code, "parent_id": u.parent_id,
            "unit_type": {"id": t.id, "name": t.name, "color": t.color} if t else None,
            "unit_type_id": u.unit_type_id,
            "head": _person_ref(u.head), "head_id": u.head_id,
            "description": u.description, "member_count": member_count, "version": u.version,
        }


# ---------------------------------------------------------------------- functions
class FunctionService(TreeService):
    model = Function
    closure = FunctionClosure
    entity_type = "function"
    permissions = {"create": "functions.manage", "update": "functions.manage", "delete": "functions.manage"}

    def validate_create(self, data):
        super().validate_create(data)
        _check_person(self.tenant_id, data.get("lead_id"), "lead_id")
        _check_unique_code(Function, self.tenant_id, data.get("code"))

    def validate_update(self, obj, changes):
        super().validate_update(obj, changes)
        if "lead_id" in changes:
            _check_person(self.tenant_id, changes["lead_id"], "lead_id")
        if "code" in changes:
            _check_unique_code(Function, self.tenant_id, changes["code"], obj.id)

    def validate_delete(self, obj):
        super().validate_delete(obj)
        if _member_counts(User.function_id, [obj.id]).get(obj.id):
            raise Conflict("Move the people in this function to another function first")

    def list_all(self):
        items = db.session.scalars(self.base_query().order_by(Function.name)).all()
        counts = _member_counts(User.function_id, [f.id for f in items], self.actor)
        return [self.serialize(f, counts.get(f.id, 0)) for f in items]

    def detail(self, function_id):
        fn = self.get(function_id)
        path = [db.session.get(Function, i) for i in ancestor_ids(FunctionClosure, fn.id)]
        data = self.serialize(fn, _member_counts(User.function_id, [fn.id], self.actor).get(fn.id, 0))
        data["path"] = [{"id": p.id, "name": p.name, "visible": True} for p in path]
        data["child_count"] = self.child_count(fn)
        data["can_manage"] = True
        data["can_move_or_delete"] = True
        return data

    @staticmethod
    def serialize(f, member_count=0):
        return {
            "id": f.id, "name": f.name, "code": f.code, "parent_id": f.parent_id,
            "lead": _person_ref(f.lead), "lead_id": f.lead_id,
            "description": f.description, "member_count": member_count, "version": f.version,
        }

"""Lookup lists and their values. Edits here change the settings DRAFT; publish to make them live."""
from sqlalchemy import func, select

from app.core.command import CommandService
from app.core.errors import ValidationFailed
from app.extensions import db
from app.modules.lookups.models import LookupType, LookupValue

MANAGE = {"create": "settings.manage", "update": "settings.manage", "delete": "settings.manage"}


def _keep_order_if_empty(changes):
    """An empty "Order" box on an edit form means "leave the order as it is"."""
    if "sort_order" in changes and changes["sort_order"] is None:
        changes.pop("sort_order")


def _no_code_change(obj, changes, *fields):
    for field in fields:
        if field in changes and changes[field] != getattr(obj, field):
            raise ValidationFailed(f"The {field.replace('_id', '').replace('_', ' ')} cannot change after creation",
                                   {"field": field})


class LookupTypeService(CommandService):
    model = LookupType
    entity_type = "lookup_type"
    permissions = MANAGE
    protected_fields = frozenset({"is_system"})

    def validate_create(self, data):
        if data.get("sort_order") is None:
            last = db.session.scalar(select(func.max(LookupType.sort_order)).where(LookupType.tenant_id == self.tenant_id))
            data["sort_order"] = (last or 0) + 10
        if db.session.scalar(select(LookupType.id).where(LookupType.tenant_id == self.tenant_id,
                                                         LookupType.code == data.get("code"))):
            raise ValidationFailed("This list code is already used", {"field": "code"})

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "code")
        _keep_order_if_empty(changes)
        if changes.get("is_active") is False and obj.is_system:
            raise ValidationFailed("Built-in lists cannot be retired", {"field": "is_active"})

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Lists are never deleted; retire them instead")

    def list_all(self):
        types = db.session.scalars(self.base_query().order_by(LookupType.sort_order, LookupType.name)).all()
        values = db.session.scalars(
            select(LookupValue).where(LookupValue.tenant_id == self.tenant_id, LookupValue.is_deleted.is_(False))
            .order_by(LookupValue.sort_order, LookupValue.label)).all()
        by_type = {}
        for v in values:
            by_type.setdefault(v.lookup_type_id, []).append(serialize_value(v))
        return [serialize_type(t, by_type.get(t.id, [])) for t in types]


class LookupValueService(CommandService):
    model = LookupValue
    entity_type = "lookup_value"
    permissions = MANAGE
    protected_fields = frozenset({"is_system"})

    def _check_type(self, type_id):
        t = db.session.get(LookupType, type_id) if type_id else None
        if t is None or t.tenant_id != self.tenant_id or t.is_deleted:
            raise ValidationFailed("Choose a valid list", {"field": "lookup_type_id"})
        return t

    def _clear_other_defaults(self, type_id, keep_id=0):
        """Only one default value per list."""
        for v in db.session.scalars(select(LookupValue).where(
                LookupValue.lookup_type_id == type_id, LookupValue.is_default.is_(True), LookupValue.id != keep_id)):
            v.is_default = False
            self._audit(v.id, "update", field="is_default", old=True, new=False,
                        reason="Another value became the default")

    def validate_create(self, data):
        self._check_type(data.get("lookup_type_id"))
        data["color"] = (data.get("color") or "#94A3B8").upper()
        if db.session.scalar(select(LookupValue.id).where(LookupValue.lookup_type_id == data["lookup_type_id"],
                                                          LookupValue.code == data.get("code"))):
            raise ValidationFailed("This code is already used in the list", {"field": "code"})
        if data.get("sort_order") is None:  # new values go to the end of the list
            last = db.session.scalar(select(func.max(LookupValue.sort_order))
                                     .where(LookupValue.lookup_type_id == data["lookup_type_id"]))
            data["sort_order"] = (last or 0) + 10
        if data.get("is_default"):
            self._clear_other_defaults(data["lookup_type_id"])

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "code", "lookup_type_id")
        _keep_order_if_empty(changes)
        if "color" in changes and changes["color"]:
            changes["color"] = changes["color"].upper()
        if changes.get("is_active") is False and obj.is_system:
            raise ValidationFailed("Built-in values cannot be retired", {"field": "is_active"})
        if changes.get("is_active") is False and obj.is_default:
            changes["is_default"] = False  # a retired value cannot be the default
        if changes.get("is_default") and not obj.is_default:
            if not changes.get("is_active", obj.is_active):
                raise ValidationFailed("A retired value cannot be the default", {"field": "is_default"})
            self._clear_other_defaults(obj.lookup_type_id, obj.id)

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Values are never deleted, so old records keep their label; retire them instead")


def serialize_type(t, values=None):
    return {
        "id": t.id, "code": t.code, "name": t.name, "description": t.description, "sort_order": t.sort_order,
        "is_system": t.is_system, "is_active": t.is_active, "version": t.version,
        **({"values": values} if values is not None else {}),
    }


def serialize_value(v):
    return {
        "id": v.id, "lookup_type_id": v.lookup_type_id, "code": v.code, "label": v.label, "color": v.color,
        "description": v.description, "sort_order": v.sort_order, "is_default": v.is_default,
        "is_system": v.is_system, "is_active": v.is_active, "version": v.version,
    }

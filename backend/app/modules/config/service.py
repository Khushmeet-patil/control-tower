"""Custom field definitions, terminology, and settings versions (publish, discard, roll back)."""
from sqlalchemy import func, select

from app.core.audit import record_event
from app.core.command import CommandService
from app.core.errors import NotFound, ValidationFailed
from app.core.filters import apply_filters
from app.core.models import utcnow
from app.core.pagination import paginate
from app.extensions import db
from app.modules.config.models import (
    ENTITY_TYPES, FIELD_TYPES, LIST_FIELD_TYPES, ConfigVersion, FieldDefinition, Term)
from app.modules.config.versioning import (
    COLLECTIONS, build_snapshot, clear_settings_cache, current_version, diff_snapshots)
from app.modules.lookups.models import LookupType, LookupValue
from app.modules.lookups.service import _keep_order_if_empty, _no_code_change

MANAGE = {"create": "settings.manage", "update": "settings.manage", "delete": "settings.manage"}


# ---------------------------------------------------------------------- custom field definitions
class FieldService(CommandService):
    model = FieldDefinition
    entity_type = "field_definition"
    permissions = MANAGE

    def _check_lookup(self, lookup_type_id):
        t = db.session.get(LookupType, lookup_type_id) if lookup_type_id else None
        if t is None or t.tenant_id != self.tenant_id or t.is_deleted or not t.is_active:
            raise ValidationFailed("Choose the list that supplies the options", {"field": "lookup_type_id"})

    def _check_item_types(self, entity_type, item_type_ids):
        if not item_type_ids:
            return None
        if entity_type != "work_item":
            raise ValidationFailed("Item types apply only to work item fields", {"field": "item_type_ids"})
        ids = sorted(set(item_type_ids))
        found = set(db.session.scalars(
            select(LookupValue.id).join(LookupType, LookupType.id == LookupValue.lookup_type_id)
            .where(LookupType.tenant_id == self.tenant_id, LookupType.code == "item_type", LookupValue.id.in_(ids))))
        if found != set(ids):
            raise ValidationFailed("Unknown item type", {"field": "item_type_ids"})
        return ids

    def validate_create(self, data):
        if data.get("entity_type") not in ENTITY_TYPES:
            raise ValidationFailed("Choose what the field belongs to", {"field": "entity_type"})
        if data.get("field_type") not in FIELD_TYPES:
            raise ValidationFailed("Choose a field type", {"field": "field_type"})
        if db.session.scalar(select(FieldDefinition.id).where(
                FieldDefinition.tenant_id == self.tenant_id, FieldDefinition.entity_type == data["entity_type"],
                FieldDefinition.code == data.get("code"))):
            raise ValidationFailed("This code is already used by another field", {"field": "code"})
        if data["field_type"] in LIST_FIELD_TYPES:
            self._check_lookup(data.get("lookup_type_id"))
        elif data.get("lookup_type_id"):
            raise ValidationFailed("Only select fields use a list", {"field": "lookup_type_id"})
        data["item_type_ids"] = self._check_item_types(data["entity_type"], data.get("item_type_ids"))
        if data.get("sort_order") is None:
            last = db.session.scalar(select(func.max(FieldDefinition.sort_order)).where(
                FieldDefinition.tenant_id == self.tenant_id, FieldDefinition.entity_type == data["entity_type"]))
            data["sort_order"] = (last or 0) + 10

    def validate_update(self, obj, changes):
        # Stored values depend on these, so they are fixed once the field exists.
        _no_code_change(obj, changes, "code", "entity_type", "field_type", "lookup_type_id")
        _keep_order_if_empty(changes)
        if "item_type_ids" in changes:
            changes["item_type_ids"] = self._check_item_types(obj.entity_type, changes["item_type_ids"])

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Fields are never deleted, so stored values stay readable; retire them instead")

    def list_all(self, entity_type=None):
        stmt = self.base_query()
        if entity_type:
            stmt = stmt.where(FieldDefinition.entity_type == entity_type)
        rows = db.session.scalars(stmt.order_by(FieldDefinition.sort_order, FieldDefinition.label)).all()
        return [serialize_field(f) for f in rows]


def serialize_field(f):
    return {
        "id": f.id, "entity_type": f.entity_type, "code": f.code, "label": f.label, "field_type": f.field_type,
        "lookup_type_id": f.lookup_type_id, "help_text": f.help_text, "is_required": f.is_required,
        "is_filterable": f.is_filterable, "show_in_list": f.show_in_list, "sort_order": f.sort_order,
        "item_type_ids": f.item_type_ids or [], "is_active": f.is_active, "version": f.version,
    }


# ---------------------------------------------------------------------- terminology
class TermService(CommandService):
    model = Term
    entity_type = "term"
    permissions = MANAGE

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "key", "default_singular", "default_plural")

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Terms cannot be deleted; reset them to the default instead")

    def list_all(self):
        return [serialize_term(t) for t in db.session.scalars(self.base_query().order_by(Term.default_singular))]


def serialize_term(t):
    return {"id": t.id, "key": t.key, "singular": t.singular, "plural": t.plural,
            "default_singular": t.default_singular, "default_plural": t.default_plural,
            "description": t.description, "version": t.version}


# ---------------------------------------------------------------------- versions
class SettingsService(CommandService):
    """Publish the draft, discard it, or roll back to an earlier version. All audited, all atomic."""

    model = ConfigVersion
    entity_type = "config_version"
    permissions = MANAGE

    def status(self):
        version = current_version(self.tenant_id)
        changes = diff_snapshots(version.snapshot if version else {}, build_snapshot(self.tenant_id))
        return {"current": serialize_version(version) if version else None,
                "has_changes": bool(changes), "changes": changes}

    def publish(self, note=None, *, allow_empty=False):
        self._require("create")
        with self._transaction():
            version = self._publish(note, allow_empty=allow_empty)
        clear_settings_cache()
        return version

    def discard(self, reason=None):
        """Throw away unpublished edits: put the tables back as the current version has them."""
        self._require("update")
        version = current_version(self.tenant_id)
        if version is None:
            raise ValidationFailed("Nothing has been published yet, so there is nothing to go back to")
        with self._transaction():
            count = self._restore(version.snapshot, reason or "Discarded unpublished changes")
        clear_settings_cache()
        return count

    def rollback(self, version_id, reason=None):
        """Make an earlier version live again. It is published as a new version, so history is kept."""
        self._require("update")
        target = db.session.scalar(select(ConfigVersion).where(
            ConfigVersion.id == version_id, ConfigVersion.tenant_id == self.tenant_id))
        if target is None:
            raise NotFound("Settings version not found")
        if target.is_current:
            raise ValidationFailed("This version is already live")
        note = f"Rolled back to version {target.number}" + (f": {reason}" if reason else "")
        with self._transaction():
            self._restore(target.snapshot, note)
            version = self._publish(note, restored_from=target, allow_empty=True)
        clear_settings_cache()
        return version

    def list_versions(self, params):
        stmt = self.base_query()
        stmt = apply_filters(stmt, dict(params), {"number": ConfigVersion.number}, default_sort="-number")
        return paginate(stmt, params, serialize_version)

    # -- internals (run inside a transaction)
    def _require(self, action):
        from app.core.permissions import ensure_can
        ensure_can(self.actor, self.permissions.get(action))

    def _publish(self, note, *, restored_from=None, allow_empty=False):
        previous = current_version(self.tenant_id)
        snapshot = build_snapshot(self.tenant_id)
        changes = diff_snapshots(previous.snapshot if previous else {}, snapshot)
        if not changes and previous is not None and not allow_empty:
            raise ValidationFailed("There are no unpublished changes")
        number = (db.session.scalar(select(func.max(ConfigVersion.number))
                                    .where(ConfigVersion.tenant_id == self.tenant_id)) or 0) + 1
        if previous is not None:
            previous.is_current = False
        version = ConfigVersion(
            tenant_id=self.tenant_id, number=number, is_current=True, note=note, snapshot=snapshot,
            change_count=len(changes), published_at=utcnow(),
            published_by_name=getattr(self.actor, "full_name", None) or "System",
            restored_from_id=restored_from.id if restored_from else None,
            created_by_id=self._actor_id, updated_by_id=self._actor_id)
        db.session.add(version)
        db.session.flush()
        self._audit(version.id, "publish", new={"number": number, "changes": len(changes)}, reason=note)
        return version

    def _restore(self, snapshot, reason):
        """Set every settings record to its value in `snapshot`; records created since are retired."""
        count = 0
        for name, (model, entity_type, fields, _) in COLLECTIONS.items():
            target = {r["id"]: r for r in snapshot.get(name, [])}
            rows = db.session.scalars(select(model).where(model.tenant_id == self.tenant_id,
                                                          model.is_deleted.is_(False))).all()
            for row in rows:
                wanted = target.get(row.id)
                if wanted is None:
                    wanted = {"is_active": False} if hasattr(row, "is_active") else {}
                for field in fields:
                    if field not in wanted or getattr(row, field) == wanted[field]:
                        continue
                    old = getattr(row, field)
                    setattr(row, field, wanted[field])
                    row.updated_by_id = self._actor_id
                    record_event(tenant_id=self.tenant_id, actor=self.actor, entity_type=entity_type,
                                 entity_id=row.id, operation="update", field=field, old=old, new=wanted[field],
                                 reason=reason, source=self.source, correlation_id=self.correlation_id)
                    count += 1
        db.session.flush()
        return count


def serialize_version(v):
    return {
        "id": v.id, "number": v.number, "is_current": v.is_current, "note": v.note,
        "change_count": v.change_count, "published_at": v.published_at.isoformat(),
        "published_by_name": v.published_by_name, "restored_from_id": v.restored_from_id,
    }

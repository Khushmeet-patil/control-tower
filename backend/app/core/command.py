"""CommandService: the ONE write path for every business record.

Every create / update / delete runs:
    tenant check → permission → scope/validation → save → audit rows → single commit
If anything fails, the whole transaction (including audit rows) is rolled back.

Usage — a module's service subclasses this:

    class UnitService(CommandService):
        model = OrgUnit
        entity_type = "org_unit"
        permissions = {"create": "org.manage", "update": "org.manage", "delete": "org.manage"}

        def base_query(self): ...          # narrow reads to the actor's scope
        def validate_create(self, data): ...  # raise ValidationFailed / Forbidden

Fields that are not table columns (e.g. a person's `role_ids`) are declared in
`extra_fields` and handled by overriding `read_value` and `apply_update`; they are then
validated, compared and audited exactly like normal columns.

Admin-defined custom fields: set `custom_entity` (e.g. "person") on a service whose model has a
`custom_fields` JSON column. Input `{"custom_fields": {code: value}}` is then validated against
the published field definitions, and on update each changed field is compared and audited on
its own, as "custom_fields.<code>".
"""
from contextlib import contextmanager

from flask import g, has_request_context

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.core.audit import current_correlation_id, record_event
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.models import SYSTEM_FIELDS, BaseModel, utcnow
from app.core.permissions import ensure_can
from app.extensions import db

CUSTOM_PREFIX = "custom_fields."


def clear_derived_caches() -> None:
    """Forget values calculated earlier in this request (health) because data is about to change."""
    if has_request_context():
        g.pop("_health_cache", None)


class CommandService:
    model: type[BaseModel] = None
    entity_type: str = None
    # Permission code required for each action; None means "any signed-in user".
    permissions: dict[str, str | None] = {"create": None, "update": None, "delete": None}
    # Columns callers may never set through create/update (in addition to system fields).
    protected_fields: frozenset[str] = frozenset()
    # Non-column inputs accepted on create and update (e.g. "role_ids").
    extra_fields: frozenset[str] = frozenset()
    # Entity name for admin-defined custom fields (model needs a `custom_fields` JSON column).
    custom_entity: str | None = None

    def __init__(self, actor=None, *, tenant_id: int | None = None, source: str = "screen",
                 correlation_id: str | None = None):
        self.actor = actor
        self.tenant_id = tenant_id if tenant_id is not None else getattr(actor, "tenant_id", None)
        if self.tenant_id is None:
            raise ValueError("CommandService needs an actor or an explicit tenant_id")
        if source == "screen" and has_request_context() and g.get("api_token_id"):
            source = "api"  # the request came with an API token, not from a screen
        self.source = source
        self.correlation_id = correlation_id or current_correlation_id()

    # ------------------------------------------------------------------ reads
    def base_query(self):
        """Live records of this tenant. Override to narrow further to the actor's scope."""
        return db.select(self.model).where(
            self.model.tenant_id == self.tenant_id,
            self.model.is_deleted.is_(False),
        )

    def get(self, record_id: int):
        obj = db.session.scalar(self.base_query().where(self.model.id == record_id))
        if obj is None:
            raise NotFound(f"{self.entity_type.replace('_', ' ').capitalize()} not found")
        return obj

    # ------------------------------------------------------------------ hooks (override in modules)
    def validate_create(self, data: dict) -> None:
        """Raise ValidationFailed/Forbidden for bad input. `data` may be modified in place."""

    def validate_update(self, obj, changes: dict) -> None:
        """Raise ValidationFailed/Forbidden for bad changes. `changes` may be modified in place."""

    def validate_delete(self, obj) -> None:
        """Raise ValidationFailed/Conflict/Forbidden if the record must not be deleted."""

    def apply_create(self, data: dict):
        """Build the new object from column values. Extra fields are applied afterwards."""
        return self.model(**data)

    def after_create(self, obj, data: dict) -> None:
        """Runs after the new object has an id (e.g. to link closure rows)."""

    def apply_update(self, obj, changes: dict) -> None:
        """Apply changed values. Override to handle extra fields, then call super() for columns."""
        custom = {f[len(CUSTOM_PREFIX):]: v for f, v in changes.items() if f.startswith(CUSTOM_PREFIX)}
        if custom:
            values = dict(obj.custom_fields or {})  # a new dict, so SQLAlchemy sees the JSON change
            for code, value in custom.items():
                if value is None:
                    values.pop(code, None)
                else:
                    values[code] = value
            obj.custom_fields = values
        for field, value in changes.items():
            if field.startswith(CUSTOM_PREFIX):
                continue
            if field in self.extra_fields:
                raise NotImplementedError(f"{type(self).__name__} must apply extra field '{field}'")
            setattr(obj, field, value)

    def read_value(self, obj, field: str):
        """Current value of a field, used for change detection and audit."""
        if field.startswith(CUSTOM_PREFIX):
            return (obj.custom_fields or {}).get(field[len(CUSTOM_PREFIX):])
        return getattr(obj, field)

    def audit_value(self, field: str, value):
        """Override to hide sensitive values (e.g. password hashes) in the audit log."""
        return value

    # ------------------------------------------------------------------ writes
    def create(self, data: dict, reason: str | None = None):
        ensure_can(self.actor, self.permissions.get("create"))
        data = self._clean(data)
        with self._transaction():
            if self.custom_entity:
                data["custom_fields"] = self._clean_custom(data.get("custom_fields"), None, creating=True,
                                                           context=data)
            self.validate_create(data)
            columns = {k: v for k, v in data.items() if k not in self.extra_fields}
            extras = {k: v for k, v in data.items() if k in self.extra_fields}
            obj = self.apply_create(columns)
            obj.tenant_id = self.tenant_id
            obj.created_by_id = obj.updated_by_id = self._actor_id
            db.session.add(obj)
            db.session.flush()  # assigns obj.id
            if extras:
                self.apply_update(obj, extras)
            self.after_create(obj, data)
            db.session.flush()
            fields = self.model.business_fields() + sorted(extras)
            snapshot = {f: self.audit_value(f, self.read_value(obj, f)) for f in fields}
            self._audit(obj.id, "create", new=snapshot, reason=reason)
        return obj

    def update(self, record_id: int, changes: dict, *, expected_version: int | None = None,
               reason: str | None = None):
        obj = self.get(record_id)
        ensure_can(self.actor, self.permissions.get("update"))
        if expected_version is not None and obj.version != expected_version:
            raise Conflict("This record was changed by someone else. Reload and try again.",
                           {"current_version": obj.version})
        changes = self._clean(changes)
        with self._transaction():
            if self.custom_entity and "custom_fields" in changes:
                incoming = self._clean_custom(changes.pop("custom_fields"), obj.custom_fields, creating=False,
                                              context=obj)
                changes.update({f"{CUSTOM_PREFIX}{code}": value for code, value in incoming.items()})
            self.validate_update(obj, changes)
            before = {f: self.read_value(obj, f) for f in changes}
            changed = {f: v for f, v in changes.items() if before[f] != v}
            if not changed:
                return obj
            self.apply_update(obj, changed)
            obj.updated_by_id = self._actor_id
            if set(changed) <= self.extra_fields:
                # Only linked rows changed: still bump the record's version so concurrent edits are detected.
                obj.updated_at = utcnow()
            db.session.flush()
            for field in changed:
                self._audit(obj.id, "update", field=field,
                            old=self.audit_value(field, before[field]),
                            new=self.audit_value(field, self.read_value(obj, field)), reason=reason)
        return obj

    def delete(self, record_id: int, *, reason: str | None = None):
        """Soft delete: the row stays for history but disappears from normal queries."""
        obj = self.get(record_id)
        ensure_can(self.actor, self.permissions.get("delete"))
        with self._transaction():
            self.validate_delete(obj)
            obj.is_deleted = True
            obj.deleted_at = utcnow()
            obj.updated_by_id = self._actor_id
            db.session.flush()
            self._audit(obj.id, "delete", reason=reason)
        return obj

    # ------------------------------------------------------------------ helpers
    @property
    def _actor_id(self):
        return getattr(self.actor, "id", None)

    def _clean(self, data: dict) -> dict:
        columns = set(self.model.business_fields())
        allowed = (columns - self.protected_fields) | set(self.extra_fields) | self._accepted_inputs()
        blocked = (set(data) & SYSTEM_FIELDS) | (set(data) - allowed)
        if blocked:
            raise ValidationFailed("Some fields cannot be set", {"fields": sorted(blocked)})
        return dict(data)

    def custom_field_scope(self, context) -> dict:
        """Extra arguments for custom field validation. `context` is the create data or the record.
        Work items return {"item_type_id": …} so fields limited to other item types are left out."""
        return {}

    def _clean_custom(self, incoming, existing, *, creating, context=None):
        from app.modules.config.custom_fields import clean_custom_values

        # Required fields are not enforced for system jobs (seed data), only for people and imports.
        return clean_custom_values(self.tenant_id, self.custom_entity, incoming, existing, creating=creating,
                                   check_required=self.source != "system", **self.custom_field_scope(context))

    def _accepted_inputs(self) -> set[str]:
        """Create-only inputs that are consumed by validate/apply_create (e.g. 'password')."""
        return set()

    def _audit(self, entity_id, operation, *, field=None, old=None, new=None, reason=None):
        record_event(
            tenant_id=self.tenant_id, actor=self.actor, entity_type=self.entity_type,
            entity_id=entity_id, operation=operation, field=field, old=old, new=new,
            reason=reason, source=self.source, correlation_id=self.correlation_id,
        )

    def transaction(self):
        """Public form of _transaction(), for commands made of several writes."""
        return self._transaction()

    @contextmanager
    def _transaction(self):
        """One transaction per command. Commands may call other commands inside `with svc.transaction():`
        (e.g. accepting a request creates a work item); the inner ones join the outer transaction and only
        the outermost commits, so either everything is saved and audited, or nothing is."""
        clear_derived_caches()  # a write is coming: health worked out earlier in this request may change
        depth = db.session.info.get("ct_tx_depth", 0)
        if depth:
            db.session.info["ct_tx_depth"] = depth + 1
            try:
                yield
            finally:
                db.session.info["ct_tx_depth"] = depth
            return
        db.session.info["ct_tx_depth"] = 1
        try:
            yield
            db.session.commit()
        except StaleDataError as exc:
            db.session.rollback()
            raise Conflict("This record was changed by someone else. Reload and try again.") from exc
        except IntegrityError as exc:
            db.session.rollback()
            raise Conflict("This change conflicts with an existing record (duplicate or missing link).") from exc
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.info["ct_tx_depth"] = 0

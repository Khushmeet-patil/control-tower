"""Settings snapshots: build the draft, compare it with the published version, and read published settings.

A snapshot is plain JSON: {collection: [row, ...]}, one row per settings record, keyed by id.
Record ids are kept, so work that refers to a lookup value keeps pointing at the same value
in every version.
"""
from flask import g, has_request_context
from sqlalchemy import select

from app.extensions import db
from app.modules.config.models import ENTITY_TYPES, FIELD_TYPES, ConfigVersion, FieldDefinition, Term
from app.modules.lookups.models import LookupType, LookupValue

# collection → (model, audit entity type, snapshot fields, how to name a row in a change list)
COLLECTIONS = {
    "lookup_types": (LookupType, "lookup_type",
                     ["code", "name", "description", "sort_order", "is_system", "is_active"],
                     lambda r, s: f"List “{r['name']}”"),
    "lookup_values": (LookupValue, "lookup_value",
                      ["lookup_type_id", "code", "label", "color", "description", "sort_order", "is_default",
                       "is_system", "is_active"],
                      lambda r, s: f"Value “{r['label']}” in {_type_name(s, r['lookup_type_id'])}"),
    "fields": (FieldDefinition, "field_definition",
               ["entity_type", "code", "label", "field_type", "lookup_type_id", "help_text", "is_required",
                "is_filterable", "show_in_list", "sort_order", "item_type_ids", "is_active"],
               lambda r, s: f"Field “{r['label']}” on {ENTITY_TYPES.get(r['entity_type'], r['entity_type'])}"),
    "terms": (Term, "term",
              ["key", "singular", "plural", "default_singular", "default_plural", "description"],
              lambda r, s: f"Term “{r['default_singular']}”"),
}


def _type_name(snapshot, type_id):
    for t in snapshot.get("lookup_types", []):
        if t["id"] == type_id:
            return t["name"]
    return "a list"


def build_snapshot(tenant_id: int) -> dict:
    """The current DRAFT: what the settings tables hold right now."""
    snapshot = {}
    for name, (model, _, fields, _) in COLLECTIONS.items():
        rows = db.session.scalars(select(model).where(model.tenant_id == tenant_id, model.is_deleted.is_(False))
                                  .order_by(model.id)).all()
        snapshot[name] = [{"id": r.id, **{f: getattr(r, f) for f in fields}} for r in rows]
    return snapshot


def _is_inactive(row) -> bool:
    return row.get("is_active") is False


def diff_snapshots(old: dict, new: dict) -> list[dict]:
    """What changed from `old` to `new`, as a readable list (used for 'unpublished changes')."""
    changes = []
    for name, (_, _, fields, describe) in COLLECTIONS.items():
        before = {r["id"]: r for r in old.get(name, [])}
        after = {r["id"]: r for r in new.get(name, [])}
        for rid, row in after.items():
            prev = before.get(rid)
            if prev is None:
                if not _is_inactive(row):  # a retired record that was never published is no change
                    changes.append({"collection": name, "id": rid, "change": "added", "name": describe(row, new)})
                continue
            changed = [{"field": f, "old": prev.get(f), "new": row.get(f)} for f in fields if prev.get(f) != row.get(f)]
            if changed:
                kind = ("retired" if row.get("is_active") is False and prev.get("is_active") is not False
                        else "restored" if prev.get("is_active") is False and row.get("is_active") is not False
                        else "changed")
                changes.append({"collection": name, "id": rid, "change": kind, "name": describe(row, new),
                                "fields": changed})
        for rid, row in before.items():
            if rid not in after and not _is_inactive(row):
                changes.append({"collection": name, "id": rid, "change": "removed", "name": describe(row, old)})
    return changes


def current_version(tenant_id: int) -> ConfigVersion | None:
    return db.session.scalar(select(ConfigVersion).where(
        ConfigVersion.tenant_id == tenant_id, ConfigVersion.is_current.is_(True), ConfigVersion.is_deleted.is_(False)))


def clear_settings_cache() -> None:
    if has_request_context():
        g.pop("_settings_cache", None)


def published_snapshot(tenant_id: int) -> tuple[dict, ConfigVersion | None]:
    """The settings everyone uses. Falls back to the draft only if nothing was ever published."""
    def load():
        version = current_version(tenant_id)
        return (version.snapshot if version else build_snapshot(tenant_id)), version

    if not has_request_context():
        return load()
    cache = g.setdefault("_settings_cache", {})
    if tenant_id not in cache:
        cache[tenant_id] = load()
    return cache[tenant_id]


def _by_order(rows, label):
    return sorted(rows, key=lambda r: (r.get("sort_order") or 0, (r.get(label) or "").lower()))


def settings_payload(tenant_id: int) -> dict:
    """Published settings shaped for the frontend: lookups by code, fields by entity, terms by key."""
    snapshot, version = published_snapshot(tenant_id)
    values_by_type = {}
    for v in _by_order(snapshot.get("lookup_values", []), "label"):
        values_by_type.setdefault(v["lookup_type_id"], []).append(
            {k: v[k] for k in ("id", "code", "label", "color", "description", "is_default", "is_active")})
    type_code = {t["id"]: t["code"] for t in snapshot.get("lookup_types", [])}
    lookups = {
        t["code"]: {"id": t["id"], "code": t["code"], "name": t["name"], "is_active": t["is_active"],
                    "values": values_by_type.get(t["id"], [])}
        for t in _by_order(snapshot.get("lookup_types", []), "name")
    }
    fields = {entity: [] for entity in ENTITY_TYPES}
    for f in _by_order(snapshot.get("fields", []), "label"):
        if f["is_active"]:
            fields.setdefault(f["entity_type"], []).append({**f, "lookup": type_code.get(f["lookup_type_id"])})
    terms = {t["key"]: {"singular": t["singular"], "plural": t["plural"]} for t in snapshot.get("terms", [])}
    return {
        "version": version.number if version else None,
        "published_at": version.published_at.isoformat() if version else None,
        "lookups": lookups, "fields": fields, "terms": terms,
        "entity_types": ENTITY_TYPES, "field_types": FIELD_TYPES,
    }


def published_fields(tenant_id: int, entity_type: str) -> list[dict]:
    snapshot, _ = published_snapshot(tenant_id)
    return [f for f in snapshot.get("fields", []) if f["entity_type"] == entity_type and f["is_active"]]


def published_values(tenant_id: int, lookup_type_id: int) -> dict[int, dict]:
    snapshot, _ = published_snapshot(tenant_id)
    return {v["id"]: v for v in snapshot.get("lookup_values", []) if v["lookup_type_id"] == lookup_type_id}

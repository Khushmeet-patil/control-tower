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
from app.modules.rules.models import HealthRule
from app.modules.workflows.models import ApprovalChain, ApprovalStep, StatusTransition

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
    "approval_chains": (ApprovalChain, "approval_chain",
                        ["code", "name", "description", "item_type_ids", "unit_id", "sort_order", "is_active"],
                        lambda r, s: f"Approval chain “{r['name']}”"),
    "approval_steps": (ApprovalStep, "approval_step",
                       ["chain_id", "name", "sort_order", "approver_kind", "approver_role_id", "approver_person_id",
                        "when_missing", "checklist", "require_evidence", "require_comment", "is_active"],
                       lambda r, s: f"Step “{r['name']}” in {_chain_name(s, r['chain_id'])}"),
    "health_rules": (HealthRule, "health_rule",
                     ["code", "name", "kind", "rule_type", "params", "outcome", "item_type_ids", "score",
                      "recommended_action", "escalate_to", "description", "sort_order", "is_active"],
                     lambda r, s: f"Rule “{r['name']}”"),
    "status_transitions": (StatusTransition, "status_transition",
                           ["item_type_id", "from_status_id", "to_status_ids", "is_active"],
                           lambda r, s: f"Status flow from {_value_label(s, r['from_status_id'])}"
                                        + (f" for {_value_label(s, r['item_type_id'])}" if r.get("item_type_id") else "")),
}


def _value_label(snapshot, value_id):
    for v in snapshot.get("lookup_values", []):
        if v["id"] == value_id:
            return f"“{v['label']}”"
    return "a value"


def _chain_name(snapshot, chain_id):
    for c in snapshot.get("approval_chains", []):
        if c["id"] == chain_id:
            return f"“{c['name']}”"
    return "a chain"


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
        "status_transitions": [{k: r[k] for k in ("item_type_id", "from_status_id", "to_status_ids")}
                               for r in snapshot.get("status_transitions", []) if r["is_active"]],
        "entity_types": ENTITY_TYPES, "field_types": FIELD_TYPES,
    }


def published_fields(tenant_id: int, entity_type: str) -> list[dict]:
    snapshot, _ = published_snapshot(tenant_id)
    return [f for f in snapshot.get("fields", []) if f["entity_type"] == entity_type and f["is_active"]]


def published_values(tenant_id: int, lookup_type_id: int) -> dict[int, dict]:
    snapshot, _ = published_snapshot(tenant_id)
    return {v["id"]: v for v in snapshot.get("lookup_values", []) if v["lookup_type_id"] == lookup_type_id}


def published_list(tenant_id: int, type_code: str) -> dict[int, dict]:
    """Published values of the lookup list with this code, by id ({} if the list does not exist).
    Cached for the request, next to the settings themselves (cleared with them)."""
    if has_request_context():
        cache = g.setdefault("_settings_cache", {})
        key = (tenant_id, "list", type_code)
        if key not in cache:
            cache[key] = _published_list(tenant_id, type_code)
        return cache[key]
    return _published_list(tenant_id, type_code)


def _published_list(tenant_id: int, type_code: str) -> dict[int, dict]:
    snapshot, _ = published_snapshot(tenant_id)
    type_id = next((t["id"] for t in snapshot.get("lookup_types", []) if t["code"] == type_code), None)
    return published_values(tenant_id, type_id) if type_id else {}


def published_value_id(tenant_id: int, type_code: str, value_code: str) -> int | None:
    """Id of one published lookup value, found by list code and value code (e.g. "status", "done")."""
    return next((v["id"] for v in published_list(tenant_id, type_code).values() if v["code"] == value_code), None)


def published_chains(tenant_id: int) -> list[dict]:
    """Active published approval chains, each with its active steps in order (key "steps")."""
    snapshot, _ = published_snapshot(tenant_id)
    steps = {}
    for st in snapshot.get("approval_steps", []):
        if st["is_active"]:
            steps.setdefault(st["chain_id"], []).append(st)
    return [{**c, "steps": sorted(steps.get(c["id"], []), key=lambda x: (x["sort_order"], x["id"]))}
            for c in snapshot.get("approval_chains", []) if c["is_active"]]


def published_transitions(tenant_id: int, item_type_id: int | None) -> dict[int, set[int]] | None:
    """{from status id: allowed next status ids} for an item type, or None when its statuses change freely.
    Rows for the type win; otherwise the rows that apply to every type."""
    snapshot, _ = published_snapshot(tenant_id)
    rows = [r for r in snapshot.get("status_transitions", []) if r["is_active"]]
    typed = [r for r in rows if r["item_type_id"] == item_type_id and item_type_id is not None]
    chosen = typed or [r for r in rows if r["item_type_id"] is None]
    if not chosen:
        return None
    return {r["from_status_id"]: set(r["to_status_ids"] or []) for r in chosen}

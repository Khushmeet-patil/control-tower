"""Custom field values: validation on save, display helpers and list filters.

Values are stored in a record's `custom_fields` JSON column as {field code: value}:
    text / url → "string"      number → 12.5          date → "2026-03-31"
    select     → lookup value id       multi_select → [lookup value ids]
    person     → user id
Only set values are stored; clearing a field removes its key. Validation always uses the
PUBLISHED field definitions and lookup values.
"""
from datetime import date

from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.core.json_query import json_array_contains_any, json_scalar
from app.extensions import db
from app.modules.config.versioning import published_fields, published_values

PREFIX = "custom_fields."
MAX_TEXT = 2000
FILTER_PREFIX = "cf."


def _fail(code, message):
    raise ValidationFailed(message, {"field": f"{PREFIX}{code}"})


def _lookup_id(tenant_id, field, raw, previous):
    if isinstance(raw, bool) or not isinstance(raw, int):
        _fail(field["code"], "Choose one of the listed options")
    value = published_values(tenant_id, field["lookup_type_id"]).get(raw)
    if value is None:
        _fail(field["code"], "Choose one of the listed options")
    if not value["is_active"] and raw not in previous:
        _fail(field["code"], f"“{value['label']}” has been retired; choose another option")
    return raw


def _clean_value(tenant_id, field, raw, existing):
    """Return the value to store (None = clear), or raise ValidationFailed."""
    code, kind = field["code"], field["field_type"]
    if raw is None or raw == "" or raw == []:
        return None
    if kind in ("text", "url"):
        if not isinstance(raw, str):
            _fail(code, "Enter text")
        raw = raw.strip()
        if len(raw) > MAX_TEXT:
            _fail(code, f"Use at most {MAX_TEXT} characters")
        if kind == "url" and not raw.lower().startswith(("http://", "https://")):
            _fail(code, "Enter a link starting with http:// or https://")
        return raw or None
    if kind == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            _fail(code, "Enter a number")
        return raw
    if kind == "date":
        try:
            return date.fromisoformat(str(raw)[:10]).isoformat()
        except ValueError:
            _fail(code, "Enter a valid date")
    if kind == "select":
        previous = {existing} if existing is not None else set()
        return _lookup_id(tenant_id, field, raw, previous)
    if kind == "multi_select":
        if not isinstance(raw, list):
            _fail(code, "Choose one or more of the listed options")
        previous = set(existing or [])
        return sorted({_lookup_id(tenant_id, field, v, previous) for v in raw}) or None
    if kind == "person":
        from app.modules.auth.models import User

        if isinstance(raw, bool) or not isinstance(raw, int):
            _fail(code, "Choose a person")
        found = db.session.scalar(select(User.id).where(User.id == raw, User.tenant_id == tenant_id,
                                                        User.is_deleted.is_(False)))
        if not found:
            _fail(code, "Choose a person")
        return raw
    _fail(code, "Unsupported field type")


def applicable_fields(tenant_id: int, entity_type: str, item_type_id: int | None = None) -> list[dict]:
    """Published fields of an entity; for work items, only those that apply to `item_type_id`."""
    return [f for f in published_fields(tenant_id, entity_type)
            if item_type_id is None or not f.get("item_type_ids") or item_type_id in f["item_type_ids"]]


def clean_custom_values(tenant_id: int, entity_type: str, incoming: dict | None, existing: dict | None, *,
                        creating: bool, check_required: bool = True, item_type_id: int | None = None) -> dict:
    """Validate `incoming` (all or some fields) and return the cleaned values that were sent.

    On create, the result is the full set of values; on update it holds only the fields sent,
    with None meaning "clear this field".
    """
    if incoming is None:
        incoming = {}
    if not isinstance(incoming, dict):
        raise ValidationFailed("Custom fields must be an object", {"field": "custom_fields"})
    existing = existing or {}
    fields = {f["code"]: f for f in applicable_fields(tenant_id, entity_type, item_type_id)}
    unknown = set(incoming) - set(fields)
    if unknown:
        raise ValidationFailed("Unknown custom field", {"field": "custom_fields", "codes": sorted(unknown)})

    cleaned = {code: _clean_value(tenant_id, fields[code], raw, existing.get(code)) for code, raw in incoming.items()}
    if check_required:
        for code, field in fields.items():
            if not field["is_required"]:
                continue
            missing = (code in cleaned and cleaned[code] is None) or (creating and cleaned.get(code) is None)
            if missing:
                _fail(code, f"{field['label']} is required")
    if creating:
        cleaned = {k: v for k, v in cleaned.items() if v is not None}
    return cleaned


def person_refs(tenant_id: int, entity_type: str, values: dict | None) -> dict:
    """{field code: {id, full_name, initials}} for person-type custom fields, so screens can show names."""
    from app.modules.auth.models import User

    values = values or {}
    codes = {f["code"] for f in published_fields(tenant_id, entity_type) if f["field_type"] == "person"}
    ids = {values[c] for c in codes if values.get(c)}
    if not ids:
        return {}
    people = {u.id: u for u in db.session.scalars(select(User).where(User.id.in_(ids)))}
    return {c: {"id": values[c], "full_name": people[values[c]].full_name, "initials": people[values[c]].initials}
            for c in codes if values.get(c) in people}


def apply_custom_filters(stmt, column, params: dict, tenant_id: int, entity_type: str):
    """Filter a list by custom fields. Query keys look like the normal filters, prefixed with 'cf.':

        cf.business_impact=12          select/person: equals; multi_select: contains
        cf.business_impact__in=12,13   any of
        cf.budget__gte=1000            number/date: __gte, __lte
        cf.vendor__contains=acme       text/url: contains
    Custom keys are removed from `params`, so the remaining keys go to app.core.filters.
    """
    fields = {f["code"]: f for f in published_fields(tenant_id, entity_type) if f["is_filterable"]}
    for key in [k for k in params if k.startswith(FILTER_PREFIX)]:
        raw = params.pop(key)
        if raw in (None, ""):
            continue
        code, _, op = key[len(FILTER_PREFIX):].partition("__")
        field = fields.get(code)
        if field is None:
            raise ValidationFailed(f"Unknown filter '{key}'")
        kind = field["field_type"]
        try:
            if kind in ("select", "multi_select", "person"):
                if op not in ("", "in"):
                    raise ValueError
                ids = [int(v) for v in str(raw).split(",") if v]
                if kind == "multi_select":
                    stmt = stmt.where(json_array_contains_any(column, code, ids))
                else:
                    stmt = stmt.where(json_scalar(column, code, "integer").in_(ids))
            elif kind in ("number", "date"):
                value = float(raw) if kind == "number" else date.fromisoformat(raw).isoformat()
                expr = json_scalar(column, code, "float" if kind == "number" else "string")
                ops = {"": expr == value, "gte": expr >= value, "lte": expr <= value}
                if op not in ops:
                    raise ValueError
                stmt = stmt.where(ops[op])
            else:
                expr = json_scalar(column, code, "string")
                if op not in ("", "contains"):
                    raise ValueError
                stmt = stmt.where(expr.ilike(f"%{raw}%") if op == "contains" else expr == raw)
        except ValueError as exc:
            raise ValidationFailed(f"Invalid filter '{key}={raw}'") from exc
    return stmt

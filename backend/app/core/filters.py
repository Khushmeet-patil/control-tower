"""Generic list filtering and sorting, shared by every list endpoint.

Query-string syntax (only for fields the endpoint allows):
    status=open              equals
    status__in=open,blocked  one of
    target_date__gte=2026-01-01 / __lte / __gt / __lt
    name__contains=report    case-insensitive contains
    q=text                   search across the endpoint's search fields
    sort=-updated_at,name    sort; '-' for descending
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, or_

from app.core.errors import ValidationFailed

OPERATORS = ("in", "gte", "lte", "gt", "lt", "contains")
RESERVED = {"page", "per_page", "sort", "q"}


def _convert(column, raw: str):
    col_type = column.type
    try:
        if isinstance(col_type, Boolean):
            return raw.lower() in ("1", "true", "yes")
        if isinstance(col_type, Integer):
            return int(raw)
        if isinstance(col_type, Numeric):
            return float(raw)
        if isinstance(col_type, DateTime):
            return datetime.fromisoformat(raw)
        if isinstance(col_type, Date):
            return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationFailed(f"Invalid value '{raw}' for filter {column.key}") from exc
    return raw


def apply_filters(stmt, params, allowed: dict, search_fields: list | None = None, default_sort: str | None = None):
    """
    stmt: a SQLAlchemy select
    params: request.args (MultiDict) or dict
    allowed: {"public_name": Column} — only these can be filtered/sorted
    """
    for key, raw in params.items():
        if key in RESERVED or raw in (None, ""):
            continue
        name, _, op = key.partition("__")
        if name not in allowed or (op and op not in OPERATORS):
            raise ValidationFailed(f"Unknown filter '{key}'")
        column = allowed[name]
        if op == "in":
            stmt = stmt.where(column.in_([_convert(column, v) for v in raw.split(",") if v]))
        elif op == "contains":
            stmt = stmt.where(column.ilike(f"%{raw}%"))
        elif op == "gte":
            stmt = stmt.where(column >= _convert(column, raw))
        elif op == "lte":
            stmt = stmt.where(column <= _convert(column, raw))
        elif op == "gt":
            stmt = stmt.where(column > _convert(column, raw))
        elif op == "lt":
            stmt = stmt.where(column < _convert(column, raw))
        else:
            stmt = stmt.where(column == _convert(column, raw))

    q = (params.get("q") or "").strip()
    if q and search_fields:
        stmt = stmt.where(or_(*[f.ilike(f"%{q}%") for f in search_fields]))

    sort = params.get("sort") or default_sort
    if sort:
        for part in sort.split(","):
            desc = part.startswith("-")
            name = part.lstrip("-")
            if name not in allowed:
                raise ValidationFailed(f"Cannot sort by '{name}'")
            stmt = stmt.order_by(allowed[name].desc() if desc else allowed[name].asc())
    return stmt

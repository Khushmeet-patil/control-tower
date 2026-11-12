"""Portable queries on values inside JSON columns (MySQL JSON and SQLite JSON1).

Scalar reads use SQLAlchemy's JSON indexing, which renders correctly on both databases.
Only "does this JSON array contain any of these values" differs, so that one helper
switches on the database in use; nothing else in the code should need to.
"""
from sqlalchemy import exists, func, literal, or_, select

from app.extensions import db


def json_scalar(column, key: str, kind: str = "string"):
    expr = column[key]
    return {"integer": expr.as_integer, "float": expr.as_float}.get(kind, expr.as_string)()


def json_array_contains_any(column, key: str, values: list[int]):
    """True when the JSON array at `key` holds at least one of `values` (integers)."""
    values = [int(v) for v in values]
    path = f'$."{key}"'  # keys are validated as [a-z0-9_] where they are defined
    if db.session.get_bind().dialect.name == "mysql":
        return or_(*[func.json_contains(column, str(v), path) == 1 for v in values])
    items = func.json_each(column, path).table_valued("value")
    return exists(select(literal(1)).select_from(items).where(items.c.value.in_(values)))

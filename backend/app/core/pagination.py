"""Shared pagination: every list endpoint returns {items, page, per_page, total, pages}."""
from flask import current_app
from sqlalchemy import func, select

from app.extensions import db


def page_args(params) -> tuple[int, int]:
    default = current_app.config["DEFAULT_PAGE_SIZE"]
    maximum = current_app.config["MAX_PAGE_SIZE"]
    try:
        page = max(int(params.get("page", 1)), 1)
        per_page = min(max(int(params.get("per_page", default)), 1), maximum)
    except (TypeError, ValueError):
        page, per_page = 1, default
    return page, per_page


def paginate(stmt, params, serialize):
    """Run `stmt` one page at a time and serialise each row with `serialize(obj) -> dict`."""
    page, per_page = page_args(params)
    total = db.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.session.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).all()
    return {
        "items": [serialize(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }

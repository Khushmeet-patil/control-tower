from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.views.service import SavedViewService

bp = Blueprint("views", __name__, url_prefix="/api/v1/views")


class ViewCreateIn(InputSchema):
    name: str = Field(min_length=1, max_length=100)
    page: str = "work"
    filters: dict = {}
    layout: str = "list"
    is_shared: bool = False


class ViewUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    filters: dict | None = None
    layout: str | None = None
    is_shared: bool | None = None
    version: int | None = None
    reason: str | None = None


@bp.get("")
@require_permission("work.view")
def list_views():
    return {"items": SavedViewService(current_user).list_for(request.args.get("page", "work"))}


@bp.post("")
@require_permission("work.view")
def create_view():
    data, _, reason = parse_body(ViewCreateIn, request.get_json())
    svc = SavedViewService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/<int:view_id>")
@require_permission("work.view")
def update_view(view_id):
    data, version, reason = parse_body(ViewUpdateIn, request.get_json())
    svc = SavedViewService(current_user)
    return svc.serialize(svc.update(view_id, data, expected_version=version, reason=reason))


@bp.delete("/<int:view_id>")
@require_permission("work.view")
def delete_view(view_id):
    SavedViewService(current_user).delete(view_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}

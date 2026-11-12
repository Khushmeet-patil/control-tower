from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import login_required, require_permission
from app.core.schemas import parse_body
from app.modules.access.catalog import catalog
from app.modules.access.models import SCOPES
from app.modules.access.schemas import RoleCreateIn, RoleUpdateIn
from app.modules.access.service import RoleService

bp = Blueprint("access", __name__, url_prefix="/api/v1")


@bp.get("/permissions")
@login_required
def permissions():
    return {"items": catalog(), "scopes": list(SCOPES)}


@bp.get("/roles")
@login_required
def list_roles():
    return {"items": RoleService(current_user).list_all()}


@bp.post("/roles")
@require_permission("roles.manage")
def create_role():
    data, _, reason = parse_body(RoleCreateIn, request.get_json())
    svc = RoleService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/roles/<int:role_id>")
@require_permission("roles.manage")
def update_role(role_id):
    data, version, reason = parse_body(RoleUpdateIn, request.get_json())
    svc = RoleService(current_user)
    return svc.serialize(svc.update(role_id, data, expected_version=version, reason=reason))


@bp.delete("/roles/<int:role_id>")
@require_permission("roles.manage")
def delete_role(role_id):
    RoleService(current_user).delete(role_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}

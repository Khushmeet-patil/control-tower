from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import require_permission
from app.core.schemas import parse_body
from app.modules.organisation import service
from app.modules.organisation.schemas import FunctionCreateIn, FunctionUpdateIn, UnitCreateIn, UnitUpdateIn

bp = Blueprint("organisation", __name__, url_prefix="/api/v1")


# ---- unit types
@bp.get("/unit-types")
@require_permission("org.view")
def unit_types():
    return {"items": service.list_unit_types(current_user.tenant_id)}


# ---- administrative units
@bp.get("/units")
@require_permission("org.view")
def list_units():
    return {"items": service.UnitService(current_user).list_all()}


@bp.get("/units/<int:unit_id>")
@require_permission("org.view")
def get_unit(unit_id):
    return service.UnitService(current_user).detail(unit_id)


@bp.post("/units")
@require_permission("org.manage")
def create_unit():
    data, _, reason = parse_body(UnitCreateIn, request.get_json())
    svc = service.UnitService(current_user)
    unit = svc.create(data, reason=reason)
    return svc.detail(unit.id), 201


@bp.patch("/units/<int:unit_id>")
@require_permission("org.manage")
def update_unit(unit_id):
    data, version, reason = parse_body(UnitUpdateIn, request.get_json())
    svc = service.UnitService(current_user)
    svc.update(unit_id, data, expected_version=version, reason=reason)
    return svc.detail(unit_id)


@bp.delete("/units/<int:unit_id>")
@require_permission("org.manage")
def delete_unit(unit_id):
    service.UnitService(current_user).delete(unit_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


# ---- functions
@bp.get("/functions")
@require_permission("functions.view")
def list_functions():
    return {"items": service.FunctionService(current_user).list_all()}


@bp.get("/functions/<int:function_id>")
@require_permission("functions.view")
def get_function(function_id):
    return service.FunctionService(current_user).detail(function_id)


@bp.post("/functions")
@require_permission("functions.manage")
def create_function():
    data, _, reason = parse_body(FunctionCreateIn, request.get_json())
    svc = service.FunctionService(current_user)
    fn = svc.create(data, reason=reason)
    return svc.detail(fn.id), 201


@bp.patch("/functions/<int:function_id>")
@require_permission("functions.manage")
def update_function(function_id):
    data, version, reason = parse_body(FunctionUpdateIn, request.get_json())
    svc = service.FunctionService(current_user)
    svc.update(function_id, data, expected_version=version, reason=reason)
    return svc.detail(function_id)


@bp.delete("/functions/<int:function_id>")
@require_permission("functions.manage")
def delete_function(function_id):
    service.FunctionService(current_user).delete(
        function_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}

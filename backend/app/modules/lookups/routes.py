"""Admin endpoints for the lookup DRAFT. Everyone else reads published lookups from GET /settings."""
from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import require_permission
from app.core.schemas import parse_body
from app.modules.lookups.schemas import (
    LookupTypeCreateIn, LookupTypeUpdateIn, LookupValueCreateIn, LookupValueUpdateIn)
from app.modules.lookups.service import LookupTypeService, LookupValueService, serialize_type, serialize_value

bp = Blueprint("lookups", __name__, url_prefix="/api/v1")


@bp.get("/lookup-types")
@require_permission("settings.manage")
def list_types():
    return {"items": LookupTypeService(current_user).list_all()}


@bp.post("/lookup-types")
@require_permission("settings.manage")
def create_type():
    data, _, reason = parse_body(LookupTypeCreateIn, request.get_json())
    return serialize_type(LookupTypeService(current_user).create(data, reason=reason), []), 201


@bp.patch("/lookup-types/<int:type_id>")
@require_permission("settings.manage")
def update_type(type_id):
    data, version, reason = parse_body(LookupTypeUpdateIn, request.get_json())
    return serialize_type(LookupTypeService(current_user).update(type_id, data, expected_version=version, reason=reason))


@bp.post("/lookup-values")
@require_permission("settings.manage")
def create_value():
    data, _, reason = parse_body(LookupValueCreateIn, request.get_json())
    return serialize_value(LookupValueService(current_user).create(data, reason=reason)), 201


@bp.patch("/lookup-values/<int:value_id>")
@require_permission("settings.manage")
def update_value(value_id):
    data, version, reason = parse_body(LookupValueUpdateIn, request.get_json())
    return serialize_value(
        LookupValueService(current_user).update(value_id, data, expected_version=version, reason=reason))

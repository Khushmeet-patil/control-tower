"""Settings: published settings for everyone, plus the admin draft (fields, terms) and versions."""
from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import login_required, require_permission
from app.core.schemas import parse_body
from app.modules.config.schemas import FieldCreateIn, FieldUpdateIn, PublishIn, ReasonIn, TermUpdateIn
from app.modules.config.service import (
    FieldService, SettingsService, TermService, serialize_field, serialize_term, serialize_version)
from app.modules.config.versioning import settings_payload

bp = Blueprint("config", __name__, url_prefix="/api/v1")


# ---- published settings: what every screen uses (lookups + colours, custom fields, terms)
@bp.get("/settings")
@login_required
def published():
    return settings_payload(current_user.tenant_id)


# ---- draft status and versions
@bp.get("/settings/status")
@require_permission("settings.manage")
def status():
    return SettingsService(current_user).status()


@bp.post("/settings/publish")
@require_permission("settings.manage")
def publish():
    body = PublishIn.model_validate(request.get_json() or {})
    return serialize_version(SettingsService(current_user).publish(body.note)), 201


@bp.post("/settings/discard")
@require_permission("settings.manage")
def discard():
    body = ReasonIn.model_validate(request.get_json() or {})
    return {"ok": True, "reverted": SettingsService(current_user).discard(body.reason)}


@bp.get("/settings/versions")
@require_permission("settings.manage")
def versions():
    return SettingsService(current_user).list_versions(request.args)


@bp.post("/settings/versions/<int:version_id>/rollback")
@require_permission("settings.manage")
def rollback(version_id):
    body = ReasonIn.model_validate(request.get_json() or {})
    return serialize_version(SettingsService(current_user).rollback(version_id, body.reason)), 201


# ---- custom field definitions (draft)
@bp.get("/field-definitions")
@require_permission("settings.manage")
def list_fields():
    return {"items": FieldService(current_user).list_all(request.args.get("entity_type"))}


@bp.post("/field-definitions")
@require_permission("settings.manage")
def create_field():
    data, _, reason = parse_body(FieldCreateIn, request.get_json())
    return serialize_field(FieldService(current_user).create(data, reason=reason)), 201


@bp.patch("/field-definitions/<int:field_id>")
@require_permission("settings.manage")
def update_field(field_id):
    data, version, reason = parse_body(FieldUpdateIn, request.get_json())
    return serialize_field(FieldService(current_user).update(field_id, data, expected_version=version, reason=reason))


# ---- terminology (draft)
@bp.get("/terms")
@require_permission("settings.manage")
def list_terms():
    return {"items": TermService(current_user).list_all()}


@bp.patch("/terms/<int:term_id>")
@require_permission("settings.manage")
def update_term(term_id):
    data, version, reason = parse_body(TermUpdateIn, request.get_json())
    return serialize_term(TermService(current_user).update(term_id, data, expected_version=version, reason=reason))

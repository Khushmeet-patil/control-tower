from datetime import date

from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.templates.service import TemplateService

bp = Blueprint("templates", __name__, url_prefix="/api/v1/templates")


class TemplateIn(InputSchema):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    is_shared: bool = False
    structure: list
    reason: str | None = None


class TemplateUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    is_shared: bool | None = None
    structure: list | None = None
    version: int | None = None
    reason: str | None = None


class FromItemIn(InputSchema):
    work_item_id: int
    name: str | None = Field(default=None, max_length=160)
    description: str | None = None
    is_shared: bool = False


class UseIn(InputSchema):
    start_date: date | None = None
    parent_id: int | None = None
    unit_id: int | None = None
    accountable_id: int | None = None
    title: str | None = Field(default=None, max_length=300)
    reason: str | None = None


@bp.get("")
@require_permission("work.view")
def list_templates():
    return TemplateService(current_user).list(request.args)


@bp.get("/<int:template_id>")
@require_permission("work.view")
def get_template(template_id):
    svc = TemplateService(current_user)
    return svc.serialize(svc.get(template_id), detail=True)


@bp.post("")
@require_permission("work.view")
def create_template():
    data, _, reason = parse_body(TemplateIn, request.get_json())
    svc = TemplateService(current_user)
    return svc.serialize(svc.create(data, reason=reason), detail=True), 201


@bp.post("/from-item")
@require_permission("work.view")
def from_item():
    body = FromItemIn.model_validate(request.get_json() or {})
    svc = TemplateService(current_user)
    t = svc.from_item(body.work_item_id, body.name, body.description, body.is_shared)
    return svc.serialize(t, detail=True), 201


@bp.patch("/<int:template_id>")
@require_permission("work.view")
def update_template(template_id):
    data, version, reason = parse_body(TemplateUpdateIn, request.get_json())
    svc = TemplateService(current_user)
    return svc.serialize(svc.update(template_id, data, expected_version=version, reason=reason), detail=True)


@bp.delete("/<int:template_id>")
@require_permission("work.view")
def delete_template(template_id):
    TemplateService(current_user).delete(template_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/<int:template_id>/use")
@require_permission("work.view")
def use_template(template_id):
    body = UseIn.model_validate(request.get_json() or {})
    made = TemplateService(current_user).instantiate(template_id, **body.model_dump())
    return {"items": [{"id": w.id, "code": w.code, "title": w.title} for w in made]}, 201

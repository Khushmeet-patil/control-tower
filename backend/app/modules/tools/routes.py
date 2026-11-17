from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.access.service import RoleService
from app.modules.tools.service import ToolService

bp = Blueprint("tools", __name__, url_prefix="/api/v1/tools")


class _Fields(InputSchema):
    description: str | None = None
    icon: str | None = Field(default=None, max_length=16)
    kind: str | None = None
    url: str | None = Field(default=None, max_length=500)
    work_item_ids: list[int] | None = None
    work_item_codes: list[str] | None = None
    unit_ids: list[int] | None = None
    role_ids: list[int] | None = None
    item_type_ids: list[int] | None = None
    definition: dict | None = None
    context_params: dict | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    reason: str | None = None


class ToolCreateIn(_Fields):
    name: str = Field(min_length=1, max_length=120)


class ToolUpdateIn(_Fields):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    version: int | None = None


class OpenIn(InputSchema):
    work_item_id: int | None = None


class SubmitIn(InputSchema):
    work_item_id: int
    values: dict = Field(default_factory=dict)
    version: int | None = None
    reason: str | None = Field(default=None, max_length=2000)


class ChecklistIn(InputSchema):
    work_item_id: int
    answers: dict[str, bool] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)
    version: int | None = None
    reason: str | None = Field(default=None, max_length=2000)


@bp.get("")
@require_permission("work.view")
def list_tools():
    """Tools you may use (?work_item_id= for one item); ?manage=1 lists the whole registry (tools.manage)."""
    return ToolService(current_user).list(request.args)


@bp.get("/options")
@require_permission("tools.manage")
def options():
    """Choices for the registry form: work item fields a form tool may contain, and roles."""
    return {"form_fields": ToolService(current_user).form_field_options(),
            "roles": [{"id": r["id"], "name": r["name"]} for r in RoleService(current_user).list_all()]}


@bp.get("/<int:tool_id>")
@require_permission("work.view")
def get_tool(tool_id):
    return ToolService(current_user).detail(tool_id)


@bp.post("")
@require_permission("tools.manage")
def create_tool():
    data, _, reason = parse_body(ToolCreateIn, request.get_json())
    svc = ToolService(current_user)
    return svc.serialize(svc.create({k: v for k, v in data.items() if v is not None}, reason=reason), manage=True), 201


@bp.patch("/<int:tool_id>")
@require_permission("tools.manage")
def update_tool(tool_id):
    data, version, reason = parse_body(ToolUpdateIn, request.get_json())
    svc = ToolService(current_user)
    return svc.serialize(svc.update(tool_id, data, expected_version=version, reason=reason), manage=True)


@bp.delete("/<int:tool_id>")
@require_permission("tools.manage")
def delete_tool(tool_id):
    ToolService(current_user).delete(tool_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/<int:tool_id>/open")
@require_permission("work.view")
def open_tool(tool_id):
    """Checks access and logs the opening; returns {"url"} to open."""
    body = OpenIn.model_validate(request.get_json() or {})
    return ToolService(current_user).open(tool_id, body.work_item_id)


@bp.post("/<int:tool_id>/submit")
@require_permission("work.view")
def submit_form(tool_id):
    """Form tools: save the fields to the work item (item permissions and audit apply)."""
    body = SubmitIn.model_validate(request.get_json() or {})
    return ToolService(current_user).submit_form(tool_id, body.work_item_id, body.values,
                                                 expected_version=body.version, reason=body.reason)


@bp.get("/<int:tool_id>/response")
@require_permission("work.view")
def get_response(tool_id):
    return {"response": ToolService(current_user).get_response(tool_id, request.args.get("work_item_id", type=int))}


@bp.put("/<int:tool_id>/response")
@require_permission("work.view")
def save_response(tool_id):
    """Checklist tools: save the answers for one work item."""
    body = ChecklistIn.model_validate(request.get_json() or {})
    return ToolService(current_user).save_checklist(tool_id, body.work_item_id, body.answers, body.notes,
                                                    expected_version=body.version, reason=body.reason)


@bp.get("/<int:tool_id>/responses")
@require_permission("work.view")
def list_responses(tool_id):
    """Checklist results across the work items you can see."""
    return ToolService(current_user).responses(tool_id, request.args)

from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.scenarios.service import ScenarioService

bp = Blueprint("scenarios", __name__, url_prefix="/api/v1/scenarios")


class ScenarioIn(InputSchema):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    reason: str | None = None


class ScenarioUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    version: int | None = None
    reason: str | None = None


class ChangeIn(InputSchema):
    kind: str
    target_id: int | None = None
    work_item_id: int | None = None
    changes: dict | None = None
    note: str | None = Field(default=None, max_length=500)


class ChangeUpdateIn(InputSchema):
    changes: dict | None = None
    note: str | None = Field(default=None, max_length=500)


@bp.get("")
@require_permission("scenarios.use")
def list_scenarios():
    return ScenarioService(current_user).list(request.args)


@bp.post("")
@require_permission("scenarios.use")
def create_scenario():
    data, _, reason = parse_body(ScenarioIn, request.get_json())
    svc = ScenarioService(current_user)
    return svc.serialize(svc.create(data, reason=reason), detail=True), 201


@bp.get("/<int:scenario_id>")
@require_permission("scenarios.use")
def get_scenario(scenario_id):
    svc = ScenarioService(current_user)
    return svc.serialize(svc.get(scenario_id), detail=True)


@bp.patch("/<int:scenario_id>")
@require_permission("scenarios.use")
def update_scenario(scenario_id):
    data, version, reason = parse_body(ScenarioUpdateIn, request.get_json())
    svc = ScenarioService(current_user)
    return svc.serialize(svc.update(scenario_id, data, expected_version=version, reason=reason), detail=True)


@bp.delete("/<int:scenario_id>")
@require_permission("scenarios.use")
def delete_scenario(scenario_id):
    ScenarioService(current_user).delete(scenario_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/<int:scenario_id>/changes")
@require_permission("scenarios.use")
def add_change(scenario_id):
    body = ChangeIn.model_validate(request.get_json() or {})
    svc = ScenarioService(current_user)
    return svc.serialize_change(svc.add_change(scenario_id, body.model_dump())), 201


@bp.patch("/<int:scenario_id>/changes/<int:change_id>")
@require_permission("scenarios.use")
def update_change(scenario_id, change_id):
    body = ChangeUpdateIn.model_validate(request.get_json() or {})
    svc = ScenarioService(current_user)
    return svc.serialize_change(svc.update_change(scenario_id, change_id, body.model_dump(exclude_unset=True)))


@bp.delete("/<int:scenario_id>/changes/<int:change_id>")
@require_permission("scenarios.use")
def remove_change(scenario_id, change_id):
    ScenarioService(current_user).remove_change(scenario_id, change_id)
    return {"ok": True}


@bp.get("/<int:scenario_id>/impact")
@require_permission("scenarios.use")
def impact(scenario_id):
    return ScenarioService(current_user).impact(scenario_id, request.args.get("weeks", 12))


@bp.post("/<int:scenario_id>/apply")
@require_permission("scenarios.use")
def apply(scenario_id):
    return ScenarioService(current_user).apply(scenario_id, reason=(request.get_json(silent=True) or {}).get("reason"))


@bp.post("/<int:scenario_id>/discard")
@require_permission("scenarios.use")
def discard(scenario_id):
    return ScenarioService(current_user).discard(scenario_id, reason=(request.get_json(silent=True) or {}).get("reason"))


@bp.post("/<int:scenario_id>/duplicate")
@require_permission("scenarios.use")
def duplicate(scenario_id):
    svc = ScenarioService(current_user)
    return svc.serialize(svc.duplicate(scenario_id), detail=True), 201

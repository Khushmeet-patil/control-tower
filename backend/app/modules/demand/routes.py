from datetime import date

from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.demand.service import DemandService

bp = Blueprint("demand", __name__, url_prefix="/api/v1/demand")


class _Fields(InputSchema):
    description: str | None = None
    requester_id: int | None = None
    sponsor: str | None = Field(default=None, max_length=200)
    business_value: str | None = None
    urgency_id: int | None = None
    priority_id: int | None = None
    effort_pct: int | None = Field(default=None, ge=0, le=100000)
    requested_on: date | None = None
    needed_by: date | None = None
    dependencies: str | None = None
    remarks: str | None = None
    unit_id: int | None = None
    reason: str | None = None


class DemandCreateIn(_Fields):
    title: str = Field(min_length=1, max_length=300)


class DemandUpdateIn(_Fields):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    version: int | None = None


class InitiativeIn(InputSchema):
    title: str | None = Field(default=None, max_length=300)
    item_type_id: int
    accountable_id: int | None = None
    unit_id: int | None = None


class DecideIn(InputSchema):
    decision_id: int
    note: str | None = Field(default=None, max_length=2000)
    initiative: InitiativeIn | None = None


@bp.get("")
@require_permission("work.view")
def list_requests():
    return DemandService(current_user).list(request.args)


@bp.get("/<int:request_id>")
@require_permission("work.view")
def get_request(request_id):
    svc = DemandService(current_user)
    return svc.serialize(svc.get(request_id))


@bp.post("")
@require_permission("work.view")
def create_request():
    data, _, reason = parse_body(DemandCreateIn, request.get_json())
    svc = DemandService(current_user)
    return svc.serialize(svc.create({k: v for k, v in data.items() if v is not None}, reason=reason)), 201


@bp.patch("/<int:request_id>")
@require_permission("work.view")
def update_request(request_id):
    data, version, reason = parse_body(DemandUpdateIn, request.get_json())
    svc = DemandService(current_user)
    return svc.serialize(svc.update(request_id, data, expected_version=version, reason=reason))


@bp.delete("/<int:request_id>")
@require_permission("work.view")
def delete_request(request_id):
    DemandService(current_user).delete(request_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.get("/<int:request_id>/assessment")
@require_permission("work.view")
def assess_request(request_id):
    """Free capacity of the delivering unit, any shortfall, and lower-priority work that could be deferred."""
    return DemandService(current_user).assessment(request_id)


@bp.post("/<int:request_id>/decide")
@require_permission("work.view")
def decide_request(request_id):
    body = DecideIn.model_validate(request.get_json() or {})
    svc = DemandService(current_user)
    r = svc.decide(request_id, body.decision_id, note=body.note,
                   initiative=body.initiative.model_dump() if body.initiative else None)
    return svc.serialize(r)

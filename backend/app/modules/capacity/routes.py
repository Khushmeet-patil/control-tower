from datetime import date

from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.capacity.service import HolidayService, TimeOffService, find_people, suggestions, timeline

bp = Blueprint("capacity", __name__, url_prefix="/api/v1")


class TimeOffIn(InputSchema):
    person_id: int | None = None
    start_date: date
    end_date: date
    kind_id: int | None = None
    note: str | None = Field(default=None, max_length=300)
    reason: str | None = None


class TimeOffUpdateIn(InputSchema):
    start_date: date | None = None
    end_date: date | None = None
    kind_id: int | None = None
    note: str | None = Field(default=None, max_length=300)
    version: int | None = None
    reason: str | None = None


@bp.get("/capacity/people")
@require_permission("people.view")
def capacity_people():
    """Find people by skill with their free capacity (?skill_ids=1,2&unit_id=&q=)."""
    return find_people(current_user, request.args)


@bp.get("/capacity/timeline")
@require_permission("people.view")
def capacity_timeline():
    """Week-by-week load of a unit's people (?unit_id=&weeks=8)."""
    return timeline(current_user, request.args.get("unit_id"), request.args.get("weeks"))


@bp.get("/work-items/<int:item_id>/assignment-suggestions")
@require_permission("work.view")
def assignment_suggestions(item_id):
    """People in the item's unit who are not on it yet, most free capacity first (?skill_ids=)."""
    return suggestions(current_user, item_id, request.args)


@bp.get("/time-off")
@require_permission("people.view")
def list_time_off():
    return TimeOffService(current_user).list(request.args)


@bp.post("/time-off")
@require_permission("people.view")
def create_time_off():
    data, _, reason = parse_body(TimeOffIn, request.get_json())
    if data.get("person_id") is None:
        data.pop("person_id", None)
    svc = TimeOffService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/time-off/<int:record_id>")
@require_permission("people.view")
def update_time_off(record_id):
    data, version, reason = parse_body(TimeOffUpdateIn, request.get_json())
    svc = TimeOffService(current_user)
    return svc.serialize(svc.update(record_id, data, expected_version=version, reason=reason))


@bp.delete("/time-off/<int:record_id>")
@require_permission("people.view")
def delete_time_off(record_id):
    TimeOffService(current_user).delete(record_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


class HolidayIn(InputSchema):
    holiday_date: date
    name: str = Field(min_length=1, max_length=120)
    unit_id: int | None = None
    reason: str | None = None


class HolidayUpdateIn(InputSchema):
    holiday_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    unit_id: int | None = None
    version: int | None = None
    reason: str | None = None


@bp.get("/holidays")
@require_permission("people.view")
def list_holidays():
    return HolidayService(current_user).list(request.args)


@bp.post("/holidays")
@require_permission("people.view")
def create_holiday():
    data, _, reason = parse_body(HolidayIn, request.get_json())
    svc = HolidayService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/holidays/<int:record_id>")
@require_permission("people.view")
def update_holiday(record_id):
    data, version, reason = parse_body(HolidayUpdateIn, request.get_json())
    svc = HolidayService(current_user)
    return svc.serialize(svc.update(record_id, data, expected_version=version, reason=reason))


@bp.delete("/holidays/<int:record_id>")
@require_permission("people.view")
def delete_holiday(record_id):
    HolidayService(current_user).delete(record_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}

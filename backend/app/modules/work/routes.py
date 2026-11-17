from flask import Blueprint, request
from flask_login import current_user

from app.core.errors import ValidationFailed
from app.core.permissions import require_permission
from app.core.schemas import parse_body
from app.modules.work.schemas import (
    AssignmentCreateIn, AssignmentUpdateIn, CompleteIn, WorkItemCreateIn, WorkItemUpdateIn)
from app.modules.work.service import AssignmentService, WorkItemService, allocation_load, unit_rollup

bp = Blueprint("work", __name__, url_prefix="/api/v1")


def _reason():
    return (request.get_json(silent=True) or {}).get("reason")


# ---- work items
@bp.get("/work-items")
@require_permission("work.view")
def list_items():
    return WorkItemService(current_user).list(request.args)


@bp.get("/work-items/<int:item_id>")
@require_permission("work.view")
def get_item(item_id):
    return WorkItemService(current_user).detail(item_id)


@bp.post("/work-items")
@require_permission("work.view")
def create_item():
    data, _, reason = parse_body(WorkItemCreateIn, request.get_json())
    svc = WorkItemService(current_user)
    return svc.detail(svc.create(data, reason=reason).id), 201


@bp.patch("/work-items/<int:item_id>")
@require_permission("work.view")
def update_item(item_id):
    data, version, reason = parse_body(WorkItemUpdateIn, request.get_json())
    svc = WorkItemService(current_user)
    svc.update(item_id, data, expected_version=version, reason=reason)
    return WorkItemService(current_user).detail(item_id)


@bp.delete("/work-items/<int:item_id>")
@require_permission("work.view")
def delete_item(item_id):
    WorkItemService(current_user).delete(item_id, reason=_reason())
    return {"ok": True}


@bp.post("/work-items/<int:item_id>/complete")
@require_permission("work.view")
def complete_item(item_id):
    """"I have finished this": status Done (+ actual finish date), which starts approval when one is configured."""
    body = CompleteIn.model_validate(request.get_json() or {})
    WorkItemService(current_user).complete(item_id, evidence_url=body.evidence_url, actual_end=body.actual_end,
                                           remarks=body.remarks, reason=body.reason)
    return WorkItemService(current_user).detail(item_id)


@bp.get("/work-items/dependencies")
@require_permission("work.view")
def dependencies():
    """Dependency links among the given items (?ids=1,2,3), for the Gantt chart. Only links whose two
    ends the viewer may see are returned."""
    try:
        ids = [int(i) for i in (request.args.get("ids") or "").split(",") if i][:500]
    except ValueError as exc:
        raise ValidationFailed("ids must be numbers", {"field": "ids"}) from exc
    return {"items": WorkItemService(current_user).dependency_links(ids)}


@bp.get("/work-items/rollup")
@require_permission("work.view")
def rollup():
    """Progress and counts for a unit and everything below it (?unit_id=…), limited to visible work."""
    try:
        unit_id = int(request.args.get("unit_id", ""))
    except ValueError as exc:
        raise ValidationFailed("unit_id is required") from exc
    return unit_rollup(current_user, unit_id)


@bp.get("/work-items/<int:item_id>/history")
@require_permission("work.view")
def item_history(item_id):
    return WorkItemService(current_user).history(item_id, request.args)


# ---- assignments
@bp.get("/work-items/<int:item_id>/assignments")
@require_permission("work.view")
def list_assignments(item_id):
    return AssignmentService(current_user).list_for(item_id)


@bp.post("/work-items/<int:item_id>/assignments")
@require_permission("work.view")
def create_assignment(item_id):
    data, _, reason = parse_body(AssignmentCreateIn, request.get_json())
    svc = AssignmentService(current_user)
    return svc.serialize(svc.create({**data, "work_item_id": item_id}, reason=reason)), 201


@bp.patch("/assignments/<int:assignment_id>")
@require_permission("work.view")
def update_assignment(assignment_id):
    data, version, reason = parse_body(AssignmentUpdateIn, request.get_json())
    svc = AssignmentService(current_user)
    return svc.serialize(svc.update(assignment_id, data, expected_version=version, reason=reason))


@bp.delete("/assignments/<int:assignment_id>")
@require_permission("work.view")
def delete_assignment(assignment_id):
    AssignmentService(current_user).delete(assignment_id, reason=_reason())
    return {"ok": True}


@bp.get("/assignments/load")
@require_permission("work.view")
def assignment_load():
    """Current allocation % per person, e.g. ?person_ids=4,7 — shown while assigning people."""
    try:
        ids = [int(p) for p in request.args.get("person_ids", "").split(",") if p][:100]
    except ValueError as exc:
        raise ValidationFailed("person_ids must be numbers") from exc
    return {"items": {str(k): v for k, v in allocation_load(current_user.tenant_id, ids).items()}}

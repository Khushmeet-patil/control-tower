from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import require_permission
from app.core.schemas import parse_body
from app.modules.workflows.models import APPROVER_KINDS, WHEN_MISSING
from app.modules.workflows.schemas import (
    ChainCreateIn, ChainUpdateIn, DecisionIn, ReasonIn, StepCreateIn, StepUpdateIn)
from app.modules.workflows.service import (
    ApprovalService, ChainService, StepService, serialize_chain, serialize_step)

bp = Blueprint("workflows", __name__, url_prefix="/api/v1")


# ---- approval chains (settings draft; used once published)
@bp.get("/approval-chains")
@require_permission("settings.manage")
def list_chains():
    return {"items": ChainService(current_user).list_all(), "approver_kinds": APPROVER_KINDS,
            "when_missing": WHEN_MISSING}


@bp.post("/approval-chains")
@require_permission("settings.manage")
def create_chain():
    data, _, reason = parse_body(ChainCreateIn, request.get_json())
    return serialize_chain(ChainService(current_user).create(data, reason=reason), []), 201


@bp.patch("/approval-chains/<int:chain_id>")
@require_permission("settings.manage")
def update_chain(chain_id):
    data, version, reason = parse_body(ChainUpdateIn, request.get_json())
    return serialize_chain(ChainService(current_user).update(chain_id, data, expected_version=version, reason=reason))


@bp.post("/approval-steps")
@require_permission("settings.manage")
def create_step():
    data, _, reason = parse_body(StepCreateIn, request.get_json())
    return serialize_step(StepService(current_user).create(data, reason=reason)), 201


@bp.patch("/approval-steps/<int:step_id>")
@require_permission("settings.manage")
def update_step(step_id):
    data, version, reason = parse_body(StepUpdateIn, request.get_json())
    return serialize_step(StepService(current_user).update(step_id, data, expected_version=version, reason=reason))


# ---- approvals inbox and decisions
@bp.get("/approvals")
@require_permission("work.view")
def list_approvals():
    """?box=mine (waiting for me) | submitted | decided | blocked | all | item&work_item_id=…"""
    return ApprovalService(current_user).inbox(request.args)


@bp.get("/approvals/counts")
@require_permission("work.view")
def approval_counts():
    return ApprovalService(current_user).counts()


@bp.get("/approvals/<int:request_id>")
@require_permission("work.view")
def get_approval(request_id):
    return ApprovalService(current_user).detail(request_id)


def _decide(request_id, approve):
    body = DecisionIn.model_validate(request.get_json() or {})
    svc = ApprovalService(current_user)
    svc.decide(request_id, approve=approve, comment=body.comment, checklist=body.checklist,
               expected_version=body.version)
    return ApprovalService(current_user).detail(request_id)


@bp.post("/approvals/<int:request_id>/approve")
@require_permission("work.view")
def approve(request_id):
    return _decide(request_id, True)


@bp.post("/approvals/<int:request_id>/reject")
@require_permission("work.view")
def reject(request_id):
    return _decide(request_id, False)


@bp.post("/approvals/<int:request_id>/withdraw")
@require_permission("work.view")
def withdraw(request_id):
    body = ReasonIn.model_validate(request.get_json() or {})
    ApprovalService(current_user).withdraw(request_id, body.reason)
    return ApprovalService(current_user).detail(request_id)


@bp.post("/approvals/<int:request_id>/retry")
@require_permission("work.view")
def retry(request_id):
    ApprovalService(current_user).retry(request_id)
    return ApprovalService(current_user).detail(request_id)

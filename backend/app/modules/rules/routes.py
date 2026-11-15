from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.rules.catalog import CHOICES, catalog
from app.modules.rules.models import ESCALATE_TO, OUTCOMES, RULE_KINDS
from app.modules.rules.service import HealthRuleService, action_centre, serialize_rule

bp = Blueprint("rules", __name__, url_prefix="/api/v1")


class RuleCreateIn(InputSchema):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    kind: str = "health"
    rule_type: str
    params: dict | None = None
    outcome: str = "amber"
    item_type_ids: list[int] | None = None
    score: int = Field(default=50, ge=0, le=100)
    recommended_action: str | None = None
    escalate_to: str = "accountable"
    description: str | None = None
    sort_order: int | None = None
    is_active: bool = True
    reason: str | None = None


class RuleUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: str | None = None
    rule_type: str | None = None
    params: dict | None = None
    outcome: str | None = None
    item_type_ids: list[int] | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    recommended_action: str | None = None
    escalate_to: str | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    version: int | None = None
    reason: str | None = None


@bp.get("/health-rules")
@require_permission("settings.manage")
def list_rules():
    return {"items": HealthRuleService(current_user).list_all(), "types": catalog(), "choices": CHOICES,
            "kinds": RULE_KINDS, "outcomes": OUTCOMES, "escalate_to": ESCALATE_TO}


@bp.post("/health-rules")
@require_permission("settings.manage")
def create_rule():
    data, _, reason = parse_body(RuleCreateIn, request.get_json())
    return serialize_rule(HealthRuleService(current_user).create(data, reason=reason)), 201


@bp.patch("/health-rules/<int:rule_id>")
@require_permission("settings.manage")
def update_rule(rule_id):
    data, version, reason = parse_body(RuleUpdateIn, request.get_json())
    return serialize_rule(HealthRuleService(current_user).update(rule_id, data, expected_version=version, reason=reason))


@bp.get("/action-centre")
@require_permission("work.view")
def get_action_centre():
    return action_centre(current_user)

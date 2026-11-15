from flask import Blueprint, request
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.dashboards.models import CHARTS, GROUP_BY, WIDGET_TYPES
from app.modules.dashboards.service import DashboardService
from app.modules.dashboards.team import team_view

bp = Blueprint("dashboards", __name__, url_prefix="/api/v1")


class DashboardCreateIn(InputSchema):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_shared: bool = False
    widgets: list[dict] = []
    reason: str | None = None


class DashboardUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_shared: bool | None = None
    widgets: list[dict] | None = None
    version: int | None = None
    reason: str | None = None


@bp.get("/dashboards")
@require_permission("work.view")
def list_dashboards():
    return {"items": DashboardService(current_user).list_all(),
            "widget_types": WIDGET_TYPES, "group_by": GROUP_BY, "charts": CHARTS}


@bp.get("/dashboards/<int:dashboard_id>")
@require_permission("work.view")
def get_dashboard(dashboard_id):
    svc = DashboardService(current_user)
    return svc.serialize(svc.get(dashboard_id))


@bp.get("/dashboards/<int:dashboard_id>/data")
@require_permission("work.view")
def dashboard_data(dashboard_id):
    """Every widget's numbers for the person looking, limited to the work they may see."""
    return DashboardService(current_user).data(dashboard_id)


@bp.post("/dashboards")
@require_permission("work.view")
def create_dashboard():
    data, _, reason = parse_body(DashboardCreateIn, request.get_json())
    svc = DashboardService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/dashboards/<int:dashboard_id>")
@require_permission("work.view")
def update_dashboard(dashboard_id):
    data, version, reason = parse_body(DashboardUpdateIn, request.get_json())
    svc = DashboardService(current_user)
    return svc.serialize(svc.update(dashboard_id, data, expected_version=version, reason=reason))


@bp.delete("/dashboards/<int:dashboard_id>")
@require_permission("work.view")
def delete_dashboard(dashboard_id):
    DashboardService(current_user).delete(dashboard_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.get("/team")
@require_permission("work.view")
def team():
    """A unit the viewer manages (?unit_id=…, default their own): people, load, progress and exceptions."""
    return team_view(current_user, request.args.get("unit_id"))

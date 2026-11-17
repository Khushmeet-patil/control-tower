from io import BytesIO

from flask import Blueprint, request, send_file
from flask_login import current_user
from pydantic import Field

from app.core.dates import today
from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.snapshots.exports import XLSX, snapshot_xlsx, work_csv, work_table, work_xlsx
from app.modules.snapshots.service import SnapshotService

bp = Blueprint("snapshots", __name__, url_prefix="/api/v1/snapshots")
exports_bp = Blueprint("exports", __name__, url_prefix="/api/v1/exports")
CONTROL = {"limit", "snapshot", "page", "per_page"}


class TakeIn(InputSchema):
    label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    reason: str | None = None


class SnapshotUpdateIn(InputSchema):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    version: int | None = None
    reason: str | None = None


def _filters():
    return {k: v for k, v in request.args.items() if k not in CONTROL}


def xlsx_response(data: bytes, name: str):
    return send_file(BytesIO(data), mimetype=XLSX, as_attachment=True, download_name=name)


@bp.get("")
@require_permission("work.view")
def list_snapshots():
    return SnapshotService(current_user).list(request.args)


@bp.post("")
@require_permission("snapshots.manage")
def take_snapshot():
    data, _, reason = parse_body(TakeIn, request.get_json())
    svc = SnapshotService(current_user)
    return svc.serialize(svc.take(label=data.get("label"), notes=data.get("notes"), reason=reason)), 201


@bp.get("/trend")
@require_permission("work.view")
def trend():
    """Headline figures from each snapshot (?limit=12 plus Portfolio filters)."""
    return SnapshotService(current_user).trend(_filters(), limit=min(request.args.get("limit", 12, type=int), 104))


@bp.get("/compare")
@require_permission("work.view")
def compare():
    """Work in a snapshot (?snapshot=baseline|latest|<id>) against now."""
    return SnapshotService(current_user).compare(request.args.get("snapshot") or "baseline", _filters())


@bp.get("/<ref>")
@require_permission("work.view")
def get_snapshot(ref):
    svc = SnapshotService(current_user)
    return svc.serialize(svc.resolve(ref))


@bp.patch("/<int:snapshot_id>")
@require_permission("snapshots.manage")
def update_snapshot(snapshot_id):
    data, version, reason = parse_body(SnapshotUpdateIn, request.get_json())
    svc = SnapshotService(current_user)
    return svc.serialize(svc.update(snapshot_id, data, expected_version=version, reason=reason))


@bp.delete("/<int:snapshot_id>")
@require_permission("snapshots.manage")
def delete_snapshot(snapshot_id):
    SnapshotService(current_user).delete(snapshot_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/<int:snapshot_id>/approve")
@require_permission("snapshots.approve")
def approve(snapshot_id):
    svc = SnapshotService(current_user)
    return svc.serialize(svc.approve(snapshot_id, reason=(request.get_json(silent=True) or {}).get("reason")))


@bp.post("/<int:snapshot_id>/baseline")
@require_permission("snapshots.approve")
def set_baseline(snapshot_id):
    svc = SnapshotService(current_user)
    return svc.serialize(svc.set_baseline(snapshot_id, reason=(request.get_json(silent=True) or {}).get("reason")))


@bp.get("/<ref>/items")
@require_permission("work.view")
def snapshot_items(ref):
    return SnapshotService(current_user).items(ref, request.args)


@bp.get("/<ref>/export.xlsx")
@require_permission("work.view")
def export_snapshot(ref):
    s = SnapshotService(current_user).resolve(ref)
    return xlsx_response(snapshot_xlsx(current_user, s, _filters()), f"snapshot-{s.as_of.isoformat()}.xlsx")


@exports_bp.get("/work-items.csv")
@require_permission("work.view")
def export_work_csv():
    return send_file(BytesIO(work_csv(current_user, _filters())), mimetype="text/csv", as_attachment=True,
                     download_name=f"work-{today().isoformat()}.csv")


@exports_bp.get("/work-items.json")
@require_permission("work.view")
def export_work_json():
    return {"exported_at": today().isoformat(), "filters": _filters(), "items": work_table(current_user, _filters())}


@exports_bp.get("/work-items.xlsx")
@require_permission("work.view")
def export_work():
    """The Portfolio list (same filters as its URL) as an Excel file."""
    return xlsx_response(work_xlsx(current_user, _filters()), f"work-{today().isoformat()}.xlsx")

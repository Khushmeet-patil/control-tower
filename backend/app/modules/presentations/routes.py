import re
from io import BytesIO

from flask import Blueprint, request, send_file
from flask_login import current_user
from pydantic import Field

from app.core.errors import NotFound
from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.presentations import exports
from app.modules.presentations.service import PresentationService
from app.modules.snapshots.exports import XLSX

bp = Blueprint("presentations", __name__, url_prefix="/api/v1/presentations")
FORMATS = {"pptx": (exports.to_pptx, exports.PPTX), "pdf": (exports.to_pdf, exports.PDF), "xlsx": (exports.to_xlsx, XLSX)}


class _Fields(InputSchema):
    description: str | None = None
    is_shared: bool | None = None
    mode: str | None = None
    snapshot_id: int | None = None
    pages: list[dict] | None = None
    reason: str | None = None


class PresentationCreateIn(_Fields):
    name: str = Field(min_length=1, max_length=120)


class PresentationUpdateIn(_Fields):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    version: int | None = None


@bp.get("")
@require_permission("work.view")
def list_presentations():
    return PresentationService(current_user).list_all()


@bp.get("/<int:presentation_id>")
@require_permission("work.view")
def get_presentation(presentation_id):
    svc = PresentationService(current_user)
    return svc.serialize(svc.get(presentation_id))


@bp.post("")
@require_permission("work.view")
def create_presentation():
    data, _, reason = parse_body(PresentationCreateIn, request.get_json())
    svc = PresentationService(current_user)
    return svc.serialize(svc.create({k: v for k, v in data.items() if v is not None}, reason=reason)), 201


@bp.patch("/<int:presentation_id>")
@require_permission("work.view")
def update_presentation(presentation_id):
    data, version, reason = parse_body(PresentationUpdateIn, request.get_json())
    svc = PresentationService(current_user)
    return svc.serialize(svc.update(presentation_id, data, expected_version=version, reason=reason))


@bp.delete("/<int:presentation_id>")
@require_permission("work.view")
def delete_presentation(presentation_id):
    PresentationService(current_user).delete(presentation_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/<int:presentation_id>/publish")
@require_permission("work.view")
def publish(presentation_id):
    svc = PresentationService(current_user)
    return svc.serialize(svc.publish(presentation_id, reason=(request.get_json(silent=True) or {}).get("reason")))


@bp.post("/<int:presentation_id>/duplicate")
@require_permission("work.view")
def duplicate(presentation_id):
    svc = PresentationService(current_user)
    return svc.serialize(svc.duplicate(presentation_id)), 201


@bp.get("/<int:presentation_id>/pages/<page_id>/data")
@require_permission("work.view")
def page_data(presentation_id, page_id):
    return PresentationService(current_user).page_data(presentation_id, page_id)


@bp.get("/<int:presentation_id>/export.<fmt>")
@require_permission("work.view")
def export(presentation_id, fmt):
    if fmt not in FORMATS:
        raise NotFound("Export as pptx, pdf or xlsx")
    build, mimetype = FORMATS[fmt]
    pack = PresentationService(current_user).pack(presentation_id)
    name = re.sub(r"[^A-Za-z0-9 _-]", "", pack["presentation"]["name"]).strip().replace(" ", "-") or "review"
    return send_file(BytesIO(build(current_user, pack)), mimetype=mimetype, as_attachment=True,
                     download_name=f"{name}.{fmt}")

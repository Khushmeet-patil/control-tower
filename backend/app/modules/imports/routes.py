from io import BytesIO

from flask import Blueprint, request, send_file
from flask_login import current_user
from pydantic import Field

from app.core.permissions import require_permission
from app.core.schemas import InputSchema
from app.modules.imports.service import ImportService, entity_catalog, template_xlsx
from app.modules.snapshots.exports import XLSX

bp = Blueprint("imports", __name__, url_prefix="/api/v1/imports")


class UploadIn(InputSchema):
    entity: str
    mode: str = "add"
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=8 * 1024 * 1024)  # base64 (JSON only, so no form posts)


@bp.get("/entities")
@require_permission("imports.run")
def entities():
    """What can be imported, with each template's columns."""
    return {"items": entity_catalog(current_user.tenant_id)}


@bp.get("/templates/<entity>.xlsx")
@require_permission("imports.run")
def template(entity):
    return send_file(BytesIO(template_xlsx(current_user.tenant_id, entity)), mimetype=XLSX, as_attachment=True,
                     download_name=f"control-tower-{entity.replace('_', '-')}-template.xlsx")


@bp.get("")
@require_permission("imports.run")
def list_batches():
    return ImportService(current_user).list(request.args)


@bp.post("")
@require_permission("imports.run")
def preview():
    """Upload a file and preview it: nothing is saved yet, every row's outcome is reported."""
    body = UploadIn.model_validate(request.get_json() or {})
    svc = ImportService(current_user)
    return svc.serialize(svc.preview(body.entity, body.mode, body.filename, body.content)), 201


@bp.get("/<int:batch_id>")
@require_permission("imports.run")
def get_batch(batch_id):
    svc = ImportService(current_user)
    return svc.serialize(svc.get(batch_id))


@bp.post("/<int:batch_id>/commit")
@require_permission("imports.run")
def commit(batch_id):
    svc = ImportService(current_user)
    return svc.serialize(svc.commit(batch_id))


@bp.post("/<int:batch_id>/discard")
@require_permission("imports.run")
def discard(batch_id):
    svc = ImportService(current_user)
    return svc.serialize(svc.discard(batch_id))

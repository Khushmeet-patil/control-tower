from flask import Blueprint, request
from flask_login import current_user

from app.core.audit import AuditEvent
from app.core.permissions import require_permission
from app.modules.audit import service

bp = Blueprint("audit", __name__, url_prefix="/api/v1/audit-events")


@bp.get("")
@require_permission("audit.view")
def list_events():
    return service.list_events(current_user.tenant_id, request.args)


@bp.get("/facets")
@require_permission("audit.view")
def facets():
    """Values for the filter dropdowns on the Audit log screen."""
    tid = current_user.tenant_id
    return {
        "entity_type": service.distinct_values(tid, AuditEvent.entity_type),
        "operation": service.distinct_values(tid, AuditEvent.operation),
        "source": service.distinct_values(tid, AuditEvent.source),
    }

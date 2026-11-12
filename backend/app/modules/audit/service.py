"""Read-only access to the audit trail (Audit Explorer). Audit rows are never edited or deleted."""
import json

from app.core.audit import AuditEvent
from app.core.filters import apply_filters
from app.core.pagination import paginate
from app.extensions import db

FILTERABLE = {
    "occurred_at": AuditEvent.occurred_at,
    "entity_type": AuditEvent.entity_type,
    "entity_id": AuditEvent.entity_id,
    "operation": AuditEvent.operation,
    "actor_id": AuditEvent.actor_id,
    "source": AuditEvent.source,
    "field": AuditEvent.field,
    "correlation_id": AuditEvent.correlation_id,
}
SEARCH = [AuditEvent.actor_name, AuditEvent.field, AuditEvent.reason, AuditEvent.entity_type]


def _load(text):
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def serialize(e: AuditEvent) -> dict:
    return {
        "id": e.id,
        "occurred_at": e.occurred_at.isoformat(),
        "actor_id": e.actor_id,
        "actor_name": e.actor_name,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "operation": e.operation,
        "field": e.field,
        "old_value": _load(e.old_value),
        "new_value": _load(e.new_value),
        "reason": e.reason,
        "source": e.source,
        "correlation_id": e.correlation_id,
    }


def list_events(tenant_id: int, params) -> dict:
    stmt = db.select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    stmt = apply_filters(stmt, params, FILTERABLE, SEARCH, default_sort="-occurred_at")
    stmt = stmt.order_by(AuditEvent.id.desc())
    return paginate(stmt, params, serialize)


def distinct_values(tenant_id: int, column) -> list[str]:
    stmt = db.select(column).where(AuditEvent.tenant_id == tenant_id).distinct().order_by(column)
    return [v for v in db.session.scalars(stmt) if v]

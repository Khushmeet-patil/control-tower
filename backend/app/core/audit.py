"""Append-only audit trail. Written only by CommandService, inside the same transaction as the change."""
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from flask import g, has_request_context
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import utcnow
from app.extensions import db

AUDIT_SOURCES = ("screen", "api", "import", "integration", "tool", "system")


class AuditEvent(db.Model):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="screen")
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def to_audit_text(value) -> str | None:
    """Store values as JSON text so numbers, dates and lists keep their shape."""
    if value is None:
        return None
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def current_correlation_id() -> str:
    """One ID per HTTP request (or per call outside a request), linking all events of one action."""
    if has_request_context():
        if "correlation_id" not in g:
            g.correlation_id = uuid.uuid4().hex
        return g.correlation_id
    return uuid.uuid4().hex


def record_event(*, tenant_id: int, actor, entity_type: str, entity_id: int | None, operation: str,
                 field: str | None = None, old=None, new=None, reason: str | None = None,
                 source: str = "screen", correlation_id: str | None = None) -> AuditEvent:
    """Add an audit row to the current session. The caller's transaction commits or discards it."""
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "full_name", None) or "System",
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        field=field,
        old_value=to_audit_text(old),
        new_value=to_audit_text(new),
        reason=reason,
        source=source if source in AUDIT_SOURCES else "api",
        correlation_id=correlation_id or current_correlation_id(),
    )
    db.session.add(event)
    # Webhooks subscribed to this kind of change are queued in the same transaction (outbox).
    from app.modules.integrations.events import on_audit

    on_audit(event)
    return event

"""Turning changes and alerts into webhook deliveries (the outbox pattern).

`on_audit` is called for every audit row (app.core.audit.record_event) and `enqueue_alert` for every
notification event. Both only add Delivery rows to the current session, so a webhook is called only
for changes that were really saved. `flask --app run notify --deliver` sends them.

Only business records are sent (WEBHOOK_ENTITIES); people, roles, tokens and settings never leave
through webhooks.
"""
import json
import secrets as _secrets

from flask import g, has_request_context
from sqlalchemy import select

from app.core.models import utcnow
from app.extensions import db

WEBHOOK_ENTITIES = {
    "work_item": "Work items", "assignment": "Assignments", "approval_request": "Approvals",
    "demand_request": "Requests", "time_off": "Time off", "snapshot": "Snapshots", "scenario": "Scenarios",
    "tool_response": "Checklist answers",
}
CACHE_KEY = "_webhook_cache"


def new_secret() -> str:
    return _secrets.token_urlsafe(32)


def _cache() -> dict:
    """Per request; outside a request (CLI jobs, seeding), per database session."""
    if has_request_context():
        return g.setdefault(CACHE_KEY, {})
    return db.session.info.setdefault(CACHE_KEY, {})


def active_webhooks(tenant_id: int) -> list[dict]:
    """Active webhooks of a tenant (cached; cleared whenever a webhook changes)."""
    cache = _cache()
    if tenant_id in cache:
        return cache[tenant_id]
    from app.modules.integrations.models import Webhook

    rows = [{"id": w.id, "url": w.url, "events": list(w.events or []), "unit_id": w.unit_id}
            for w in db.session.scalars(select(Webhook).where(
                Webhook.tenant_id == tenant_id, Webhook.is_deleted.is_(False), Webhook.is_active.is_(True)))]
    cache[tenant_id] = rows
    return rows


def forget_webhooks() -> None:
    if has_request_context():
        g.pop(CACHE_KEY, None)
    db.session.info.pop(CACHE_KEY, None)


def _wants(hook: dict, event: str) -> bool:
    entity = event.split(".", 1)[0]
    return event in hook["events"] or f"{entity}.*" in hook["events"]


def _unit_of(entity_type: str | None, entity_id: int | None):
    """The unit a record's work belongs to, for webhooks limited to a unit. None = unknown."""
    if not entity_id:
        return None
    from app.modules.work.models import Assignment, WorkItem

    if entity_type == "work_item":
        return db.session.scalar(select(WorkItem.unit_id).where(WorkItem.id == entity_id))
    if entity_type == "assignment":
        return db.session.scalar(select(WorkItem.unit_id).join(Assignment, Assignment.work_item_id == WorkItem.id)
                                 .where(Assignment.id == entity_id))
    if entity_type == "approval_request":
        from app.modules.workflows.models import ApprovalRequest

        return db.session.scalar(select(WorkItem.unit_id).join(ApprovalRequest, ApprovalRequest.work_item_id == WorkItem.id)
                                 .where(ApprovalRequest.id == entity_id))
    if entity_type == "demand_request":
        from app.modules.demand.models import DemandRequest

        return db.session.scalar(select(DemandRequest.unit_id).where(DemandRequest.id == entity_id))
    return None


def _in_unit(hook: dict, entity_type, entity_id) -> bool:
    if not hook["unit_id"]:
        return True
    from app.core.tree import descendant_ids
    from app.modules.organisation.models import OrgUnitClosure

    unit = _unit_of(entity_type, entity_id)
    return unit is not None and unit in descendant_ids(OrgUnitClosure, [hook["unit_id"]])


def _queue(tenant_id, hook, event, payload, subject):
    from app.modules.notifications.models import Delivery

    now = utcnow()
    db.session.add(Delivery(tenant_id=tenant_id, channel="webhook", target=hook["url"], webhook_id=hook["id"],
                            event=event, subject=subject[:300] if subject else None, payload=payload,
                            status="pending", attempts=0, next_attempt_at=now, created_at=now))


def _loads(text):
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _describe(entity_type, entity_id):
    """A readable name and a link for a record, for the message text."""
    from app.modules.notifications.service import app_url
    from app.modules.work.models import Assignment, WorkItem

    item = None
    if entity_type == "work_item":
        item = db.session.get(WorkItem, entity_id)
    elif entity_type == "assignment":
        a = db.session.get(Assignment, entity_id)
        item = db.session.get(WorkItem, a.work_item_id) if a else None
    if item is not None:
        return f"{item.code} {item.title}", app_url(f"/pages/item.html?id={item.id}")
    return f"{WEBHOOK_ENTITIES.get(entity_type, entity_type)} #{entity_id}", None


def on_audit(event) -> None:
    if event.entity_type not in WEBHOOK_ENTITIES:
        return
    hooks = active_webhooks(event.tenant_id)
    if not hooks:
        return
    name = f"{event.entity_type}.{event.operation}"
    matching = [h for h in hooks if _wants(h, name) and _in_unit(h, event.entity_type, event.entity_id)]
    if not matching:
        return
    label, link = _describe(event.entity_type, event.entity_id)
    change = f"{event.field}: {_loads(event.old_value)} → {_loads(event.new_value)}" if event.field else event.operation
    title = f"{event.actor_name or 'System'} · {event.operation} · {label}"
    data = {"entity_type": event.entity_type, "entity_id": event.entity_id, "operation": event.operation,
            "field": event.field, "old": _loads(event.old_value), "new": _loads(event.new_value),
            "reason": event.reason, "actor": {"id": event.actor_id, "name": event.actor_name},
            "source": event.source, "correlation_id": event.correlation_id,
            "title": title, "text": change + (f" (reason: {event.reason})" if event.reason else ""), "link": link}
    payload = {"event": name, "occurred_at": utcnow().isoformat(), "data": data}
    for hook in matching:
        _queue(event.tenant_id, hook, name, payload, title)


def enqueue_alert(tenant_id, kind, *, title, body=None, link=None, entity=None, people=()):
    hooks = active_webhooks(tenant_id)
    if not hooks:
        return
    name = f"alert.{kind}"
    entity_type, entity_id = entity or (None, None)
    matching = [h for h in hooks if name in h["events"] and _in_unit(h, entity_type, entity_id)]
    if not matching:
        return
    text = body or ""
    if people:
        text = (text + "\n\n" if text else "") + "For: " + ", ".join(sorted(people))
    payload = {"event": name, "occurred_at": utcnow().isoformat(),
               "data": {"kind": kind, "title": title, "text": text, "link": link,
                        "entity_type": entity_type, "entity_id": entity_id, "people": sorted(people)}}
    for hook in matching:
        _queue(tenant_id, hook, name, payload, title)

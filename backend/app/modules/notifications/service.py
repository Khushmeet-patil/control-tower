"""Notifications: raise them (`notify`), read them (the bell), choose how to get them (preferences),
and the daily checks that find work turning Red, coming due or going overdue.

`notify()` only adds rows to the current session. The caller's transaction saves them together with
the change that caused them, or discards them if that change fails. Rules:
- nobody is told about their own action (the actor is left out), and set-up jobs (source "system",
  e.g. seeding) tell nobody;
- inactive or deleted people are left out;
- a `dedupe_key` is used at most once per person (the daily checks rely on it);
- in-app is on unless the person turned that kind off; email follows their preference (default per kind)
  and is queued only when the server has email configured (MAIL_SERVER);
- webhooks subscribed to "alert.<kind>" (e.g. a Microsoft Teams channel) get one message per event.
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy import or_, select, update

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import ValidationFailed
from app.core.models import utcnow
from app.core.pagination import paginate
from app.extensions import db
from app.modules.auth.models import User
from app.modules.notifications.models import KINDS, Delivery, HealthWatch, Notification


# ---------------------------------------------------------------------- preferences
def default_prefs() -> dict:
    return {k: {"in_app": True, "email": email} for k, (_, _, email) in KINDS.items()}


def prefs_of(user) -> dict:
    out = default_prefs()
    for kind, chosen in (user.notification_prefs or {}).items():
        if kind in out and isinstance(chosen, dict):
            out[kind].update({c: bool(v) for c, v in chosen.items() if c in ("in_app", "email")})
    return out


def email_enabled() -> bool:
    return bool(current_app.config.get("MAIL_SERVER"))


def app_url(path: str | None) -> str | None:
    if not path:
        return None
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    return f"{base}{path}" if base else path


# ---------------------------------------------------------------------- raising
def notify(tenant_id: int, user_ids, kind: str, title: str, *, body: str | None = None, link: str | None = None,
           entity: tuple[str, int] | None = None, actor=None, dedupe_key: str | None = None,
           include_actor: bool = False, source: str | None = None) -> list[Notification]:
    if kind not in KINDS:
        raise ValueError(f"Unknown notification kind {kind}")
    if source == "system":  # seeding and other set-up jobs tell nobody
        return []
    ids = {int(u) for u in user_ids if u}
    actor_id = getattr(actor, "id", None)
    if actor_id in ids and not include_actor:
        ids.discard(actor_id)
    if not ids:
        return []
    people = db.session.scalars(select(User).where(User.id.in_(ids), User.tenant_id == tenant_id,
                                                   User.is_active.is_(True), User.is_deleted.is_(False))).all()
    if dedupe_key:
        seen = set(db.session.scalars(select(Notification.user_id).where(
            Notification.tenant_id == tenant_id, Notification.dedupe_key == dedupe_key,
            Notification.user_id.in_([p.id for p in people] or [0]))))
        people = [p for p in people if p.id not in seen]
    entity_type, entity_id = entity or (None, None)
    made, now, mail = [], utcnow(), email_enabled()
    for person in people:
        prefs = prefs_of(person)[kind]
        row = Notification(tenant_id=tenant_id, user_id=person.id, kind=kind, title=title[:300], body=body,
                           link=link, entity_type=entity_type, entity_id=entity_id, actor_id=actor_id,
                           dedupe_key=dedupe_key, created_by_id=actor_id, updated_by_id=actor_id,
                           # turned off in-app: kept for the record (and email), but already read
                           read_at=None if prefs["in_app"] else now)
        db.session.add(row)
        made.append(row)
        if mail and prefs["email"]:
            db.session.flush()
            db.session.add(Delivery(
                tenant_id=tenant_id, channel="email", target=person.email, notification_id=row.id, event=kind,
                subject=title[:300], payload={"title": title, "body": body, "link": app_url(link),
                                              "name": person.full_name, "kind": KINDS[kind][0]},
                status="pending", attempts=0, next_attempt_at=now, created_at=now))
    if people:
        from app.modules.integrations.events import enqueue_alert

        enqueue_alert(tenant_id, kind, title=title, body=body, link=app_url(link), entity=entity,
                      people=[p.full_name for p in people])
    return made


def work_people(item) -> set[int]:
    """The accountable owner and the responsible owners of an item."""
    from app.modules.work.models import WorkItemResponsible

    ids = set(db.session.scalars(select(WorkItemResponsible.user_id).where(
        WorkItemResponsible.work_item_id == item.id)))
    ids.add(item.accountable_id)
    return ids


def item_link(item) -> str:
    return f"/pages/item.html?id={item.id}"


# ---------------------------------------------------------------------- reading (the bell)
class NotificationService(CommandService):
    """A person's own notifications. Reading and marking as read are personal and not audited;
    changing preferences is audited on the person."""

    model = Notification
    entity_type = "notification"

    def base_query(self):
        return super().base_query().where(Notification.user_id == self.actor.id)

    def list(self, params):
        params = dict(params)
        stmt = self.base_query()
        if params.get("unread") in ("1", "true"):
            stmt = stmt.where(Notification.read_at.is_(None))
        if kind := params.get("kind"):
            stmt = stmt.where(Notification.kind == kind)
        stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        return paginate(stmt, params, self.serialize)

    def unread_count(self) -> int:
        from sqlalchemy import func

        return db.session.scalar(select(func.count()).select_from(
            self.base_query().where(Notification.read_at.is_(None)).subquery())) or 0

    @staticmethod
    def serialize(n: Notification) -> dict:
        return {"id": n.id, "kind": n.kind, "kind_label": KINDS.get(n.kind, (n.kind,))[0], "title": n.title,
                "body": n.body, "link": n.link, "entity_type": n.entity_type, "entity_id": n.entity_id,
                "read": n.read_at is not None, "created_at": n.created_at.isoformat()}

    def mark_read(self, ids=None, *, all_=False) -> int:
        stmt = update(Notification).where(Notification.tenant_id == self.tenant_id,
                                          Notification.user_id == self.actor.id, Notification.read_at.is_(None))
        if not all_:
            ids = [int(i) for i in ids or []]
            if not ids:
                return 0
            stmt = stmt.where(Notification.id.in_(ids))
        result = db.session.execute(stmt.values(read_at=utcnow()).execution_options(synchronize_session=False))
        db.session.commit()
        return result.rowcount or 0

    # ---- preferences
    def preferences(self) -> dict:
        prefs = prefs_of(self.actor)
        return {"email_available": email_enabled(),
                "kinds": [{"kind": k, "label": label, "description": desc, **prefs[k]}
                          for k, (label, desc, _) in KINDS.items()]}

    def set_preferences(self, chosen: dict) -> dict:
        if not isinstance(chosen, dict):
            raise ValidationFailed("Send {kind: {in_app, email}}")
        bad = [k for k in chosen if k not in KINDS]
        if bad:
            raise ValidationFailed(f"Unknown kinds: {', '.join(bad)}", {"field": "kinds"})
        current, defaults = prefs_of(self.actor), default_prefs()
        for kind, values in chosen.items():
            if not isinstance(values, dict):
                raise ValidationFailed("Each kind takes {in_app, email}", {"field": kind})
            current[kind].update({c: bool(v) for c, v in values.items() if c in ("in_app", "email")})
        # store only what differs from the defaults, so new defaults reach people who never chose
        stored = {k: {c: v for c, v in vals.items() if v != defaults[k][c]} for k, vals in current.items()}
        stored = {k: v for k, v in stored.items() if v} or None
        user = db.session.get(User, self.actor.id)
        old = user.notification_prefs
        if stored != old:
            with self.transaction():
                user.notification_prefs = stored
                from app.core.audit import record_event

                record_event(tenant_id=self.tenant_id, actor=self.actor, entity_type="person", entity_id=user.id,
                             operation="update", field="notification_prefs", old=old, new=stored,
                             reason="Notification preferences", source=self.source,
                             correlation_id=self.correlation_id)
        return self.preferences()


# ---------------------------------------------------------------------- daily checks
def run_checks(tenant_id: int) -> dict:
    """Deadline coming up, overdue, and turned Red. Safe to run more than once a day (deduplicated)."""
    from app.modules.rules import engine
    from app.modules.work.models import WorkItem
    from app.modules.work.service import closed_status_ids

    days = int(current_app.config.get("NOTIFY_DUE_DAYS", 3))
    day = today()
    closed = closed_status_ids(tenant_id)
    stmt = select(WorkItem).where(WorkItem.tenant_id == tenant_id, WorkItem.is_deleted.is_(False))
    if closed:
        stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
    items = db.session.scalars(stmt).all()
    counts = {"due_soon": 0, "overdue": 0, "item_red": 0}
    svc = CommandService(None, tenant_id=tenant_id, source="system")
    with svc.transaction():
        for w in items:
            if w.planned_end is None:
                continue
            if day <= w.planned_end <= day + timedelta(days=days):
                left = (w.planned_end - day).days
                when = "today" if left == 0 else "tomorrow" if left == 1 else f"in {left} days"
                counts["due_soon"] += len(notify(
                    tenant_id, work_people(w), "due_soon", f"{w.code} {w.title} is due {when}",
                    body=f"Planned finish {w.planned_end.isoformat()}.", link=item_link(w),
                    entity=("work_item", w.id), dedupe_key=f"due:{w.id}:{w.planned_end.isoformat()}"))
            elif w.planned_end < day:
                counts["overdue"] += len(notify(
                    tenant_id, work_people(w), "overdue", f"{w.code} {w.title} is overdue",
                    body=f"It was planned to finish on {w.planned_end.isoformat()}. Update the date or finish it.",
                    link=item_link(w), entity=("work_item", w.id),
                    dedupe_key=f"overdue:{w.id}:{w.planned_end.isoformat()}"))
        by_id = {w.id: w for w in items}
        results = engine.evaluate(tenant_id, list(by_id)) if by_id else {}
        watched = {h.work_item_id: h for h in db.session.scalars(
            select(HealthWatch).where(HealthWatch.tenant_id == tenant_id))}
        now = utcnow()
        for item_id, w in by_id.items():
            result = results.get(item_id)
            health = result.health if result else None
            seen = watched.get(item_id)
            if health == "red" and (seen is None or seen.health != "red"):
                top = result.top
                counts["item_red"] += len(notify(
                    tenant_id, work_people(w), "item_red", f"{w.code} {w.title} turned Red",
                    body=(top.reason + (f" Recommended: {top.action}" if top.action else "")) if top else None,
                    link=item_link(w), entity=("work_item", w.id), dedupe_key=f"red:{w.id}:{day.isoformat()}"))
            if seen is None:
                db.session.add(HealthWatch(work_item_id=item_id, tenant_id=tenant_id, health=health, seen_at=now))
            elif seen.health != health:
                seen.health, seen.seen_at = health, now
    return counts

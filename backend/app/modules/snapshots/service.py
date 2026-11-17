"""Snapshots: take them (weekly or on demand), approve them, pick the baseline, and read them.

- Taking a snapshot needs `snapshots.manage` (weekly ones are taken by `flask snapshot --weekly`).
  The figures cover all work; reading them is limited to what each viewer may see (frozen.py).
- Approving and choosing the baseline need `snapshots.approve`. Only an approved snapshot can be the
  baseline or be used by a published review pack.
- A snapshot can be deleted only while it is a draft, not the baseline, and not used by a presentation.
- Trend: the same figures (open, overdue, red/amber/green, weighted progress) from each snapshot.
- Compare: top-level work in the baseline (or any snapshot) against now: slipped dates, progress, health.
"""
from datetime import date

from sqlalchemy import func, select

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.filters import apply_filters
from app.core.models import utcnow
from app.core.pagination import paginate
from app.core.permissions import actor_can, ensure_can
from app.extensions import db
from app.modules.auth.models import User
from app.modules.snapshots import frozen
from app.modules.snapshots.models import Snapshot, SnapshotItem, SnapshotPerson
from app.modules.work.service import WorkItemService, person_ref, portfolio_params

FILTERABLE = {"label": Snapshot.label, "kind": Snapshot.kind, "status": Snapshot.status, "as_of": Snapshot.as_of,
              "taken_at": Snapshot.taken_at, "is_baseline": Snapshot.is_baseline}
EDITABLE = frozenset({"label", "notes"})


def iso_period(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


class SnapshotService(CommandService):
    model = Snapshot
    entity_type = "snapshot"
    permissions = {"create": "snapshots.manage", "update": "snapshots.manage", "delete": "snapshots.manage"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._internal = False  # set while the service itself writes approval or baseline fields
        self._rows = []

    # ------------------------------------------------------------------ taking
    def take(self, *, kind="on_demand", label=None, notes=None, reason=None):
        """Capture every work item's figures now. Weekly snapshots are taken once per ISO week."""
        if kind not in ("weekly", "on_demand"):
            raise ValidationFailed("Unknown kind of snapshot", {"field": "kind"})
        now, day = utcnow(), today()
        period = iso_period(day) if kind == "weekly" else None
        if period and (existing := db.session.scalar(self.base_query().where(Snapshot.period == period))):
            return existing
        self._rows = frozen.capture(self.tenant_id)
        self._people = frozen.capture_people(self.tenant_id)
        default = f"Week {day.isocalendar()[1]}, {day.isocalendar()[0]}" if period else f"Snapshot {day:%d %b %Y} {now:%H:%M}"
        self._internal = True
        try:
            return self.create({"label": (label or "").strip() or default, "kind": kind, "period": period, "as_of": day,
                                "taken_at": now, "taken_by_id": getattr(self.actor, "id", None),
                                "item_count": len(self._rows), "notes": notes, "status": "draft"},
                               reason=reason or ("Weekly snapshot" if period else "Snapshot taken"))
        finally:
            self._internal = False

    def after_create(self, obj, data):
        db.session.add_all(SnapshotItem(tenant_id=self.tenant_id, snapshot_id=obj.id, **row) for row in self._rows)
        db.session.add_all(SnapshotPerson(tenant_id=self.tenant_id, snapshot_id=obj.id, **row)
                           for row in getattr(self, "_people", []))
        self._rows, self._people = [], []

    def validate_update(self, obj, changes):
        if not self._internal and set(changes) - EDITABLE:
            raise ValidationFailed("Only the label and notes of a snapshot can be changed; its figures never change",
                                   {"fields": sorted(set(changes) - EDITABLE)})
        if "label" in changes and not (changes["label"] or "").strip():
            raise ValidationFailed("Give the snapshot a label", {"field": "label"})

    def _internal_update(self, obj_id, changes, reason):
        self._internal = True
        try:
            return self.update(obj_id, changes, reason=reason)
        finally:
            self._internal = False

    def approve(self, snapshot_id, *, reason=None):
        ensure_can(self.actor, "snapshots.approve", "You cannot approve snapshots")
        s = self.get(snapshot_id)
        if s.status == "approved":
            return s
        return self._internal_update(s.id, {"status": "approved", "approved_by_id": getattr(self.actor, "id", None),
                                            "approved_at": utcnow()}, reason or "Approved for reporting")

    def set_baseline(self, snapshot_id, *, reason=None):
        ensure_can(self.actor, "snapshots.approve", "You cannot choose the baseline")
        s = self.get(snapshot_id)
        if s.status != "approved":
            raise ValidationFailed("Approve the snapshot before making it the baseline")
        with self.transaction():
            for other in db.session.scalars(self.base_query().where(Snapshot.is_baseline.is_(True), Snapshot.id != s.id)):
                self._internal_update(other.id, {"is_baseline": False}, reason or f"Baseline moved to {s.label}")
            self._internal_update(s.id, {"is_baseline": True}, reason or "Set as baseline")
        return self.get(s.id)

    def _uses(self, snapshot_id) -> int:
        from app.modules.presentations.models import Presentation

        return db.session.scalar(select(func.count()).select_from(Presentation).where(
            Presentation.snapshot_id == snapshot_id, Presentation.is_deleted.is_(False))) or 0

    def validate_delete(self, obj):
        if obj.status == "approved" or obj.is_baseline:
            raise Conflict("Approved snapshots and the baseline are kept for the record")
        if self._uses(obj.id):
            raise Conflict("A presentation uses this snapshot")

    # ------------------------------------------------------------------ reads
    def baseline(self):
        return db.session.scalar(self.base_query().where(Snapshot.is_baseline.is_(True)))

    def resolve(self, ref):
        """A snapshot by id, or "baseline" / "latest"."""
        if ref in ("baseline", "latest"):
            s = self.baseline() if ref == "baseline" else db.session.scalar(
                self.base_query().order_by(Snapshot.as_of.desc(), Snapshot.taken_at.desc()).limit(1))
            if s is None:
                raise NotFound("There is no baseline yet" if ref == "baseline" else "No snapshots yet")
            return s
        try:
            return self.get(int(ref))
        except (TypeError, ValueError) as exc:
            raise NotFound("Snapshot not found") from exc

    def list(self, params):
        stmt = apply_filters(self.base_query(), dict(params), FILTERABLE, [Snapshot.label, Snapshot.notes],
                             default_sort="-as_of,-taken_at")
        return paginate(stmt, params, self.serialize)

    def serialize(self, s: Snapshot) -> dict:
        taken_by = db.session.get(User, s.taken_by_id) if s.taken_by_id else None
        approved_by = db.session.get(User, s.approved_by_id) if s.approved_by_id else None
        uses = self._uses(s.id)
        return {
            "id": s.id, "label": s.label, "kind": s.kind, "period": s.period, "as_of": s.as_of.isoformat(),
            "taken_at": s.taken_at.isoformat(), "taken_by": person_ref(taken_by), "item_count": s.item_count,
            "notes": s.notes, "status": s.status, "approved_by": person_ref(approved_by),
            "approved_at": s.approved_at.isoformat() if s.approved_at else None, "is_baseline": s.is_baseline,
            "used_by": uses,
            "permissions": {
                "can_edit": actor_can(self.actor, "snapshots.manage"),
                "can_approve": s.status == "draft" and actor_can(self.actor, "snapshots.approve"),
                "can_set_baseline": s.status == "approved" and not s.is_baseline and actor_can(self.actor, "snapshots.approve"),
                "can_delete": s.status == "draft" and not s.is_baseline and not uses and actor_can(self.actor, "snapshots.manage"),
            },
            "version": s.version,
        }

    def items(self, snapshot_ref, params):
        """The snapshot's rows you may see, with the Portfolio's filters (level, units, health…)."""
        s = self.resolve(snapshot_ref)
        params = dict(params)
        page = max(int(params.pop("page", 1) or 1), 1)
        per_page = min(max(int(params.pop("per_page", 25) or 25), 1), 500)
        rows = frozen.FrozenSet(self.actor, s).select(portfolio_params(params))
        return {"items": [frozen.row_out(r) for r in rows[(page - 1) * per_page: page * per_page]], "page": page,
                "per_page": per_page, "total": len(rows), "pages": max(1, -(-len(rows) // per_page)),
                "snapshot": self.serialize(s)}

    def trend(self, filters, limit=12):
        """The headline figures from each of the last `limit` snapshots, oldest first."""
        snaps = list(reversed(db.session.scalars(
            self.base_query().order_by(Snapshot.as_of.desc(), Snapshot.taken_at.desc()).limit(limit)).all()))
        params = portfolio_params(filters)
        points = []
        for s in snaps:
            rows = frozen.FrozenSet(self.actor, s).select(params)
            in_set = {r.work_item_id for r in rows}
            points.append({
                "snapshot_id": s.id, "label": s.label, "as_of": s.as_of.isoformat(), "status": s.status,
                "is_baseline": s.is_baseline, "total": len(rows), "open": sum(r.is_open for r in rows),
                "overdue": sum(r.is_overdue for r in rows),
                **{h: sum(1 for r in rows if r.health == h) for h in ("red", "amber", "green", "grey")},
                "progress": frozen.weighted([r for r in rows if r.parent_id not in in_set]),
            })
        return {"filters": filters, "points": points}

    def compare(self, snapshot_ref, filters):
        """Work in a snapshot (default: the baseline) against now, for the viewer's scope."""
        from app.modules.rules import engine
        from app.modules.work.progress import progress_map

        s = self.resolve(snapshot_ref or "baseline")
        params = portfolio_params(filters)
        then = {r.work_item_id: r for r in frozen.FrozenSet(self.actor, s).select(params)}
        work = WorkItemService(self.actor, tenant_id=self.tenant_id)
        live = {w.id: w for w in work.rows(params)}
        ids = list(live)
        progress = progress_map(self.tenant_id, ids)
        health = engine.evaluate(self.tenant_id, ids)
        out = []
        for item_id in sorted(set(then) | set(live), key=lambda i: (then.get(i) or live.get(i)).code):
            a, b = then.get(item_id), live.get(item_id)
            now = {"planned_end": b.planned_end.isoformat() if b and b.planned_end else None,
                   "progress": progress.get(item_id, 0) if b else None,
                   "health": (health.get(item_id).health if health.get(item_id) else None) if b else None,
                   "status_id": b.status_id if b else None} if b else None
            was = {"planned_end": a.planned_end.isoformat() if a.planned_end else None, "progress": a.progress,
                   "health": a.health, "status_id": a.status_id} if a else None
            slip = (b.planned_end - a.planned_end).days if a and b and a.planned_end and b.planned_end else None
            change = "added" if not a else "removed" if not b else "changed" if (
                slip or now["progress"] != was["progress"] or now["health"] != was["health"]
                or now["status_id"] != was["status_id"]) else "same"
            ref = b or a
            out.append({"id": item_id, "code": ref.code, "title": ref.title, "was": was, "now": now,
                        "slip_days": slip, "progress_delta": (now["progress"] - was["progress"]) if a and b else None,
                        "change": change})
        out.sort(key=lambda e: (-(e["slip_days"] or 0), e["code"]))
        return {"snapshot": self.serialize(s), "items": out,
                "summary": {"slipped": sum(1 for e in out if (e["slip_days"] or 0) > 0),
                            "pulled_in": sum(1 for e in out if (e["slip_days"] or 0) < 0),
                            "added": sum(1 for e in out if e["change"] == "added"),
                            "removed": sum(1 for e in out if e["change"] == "removed")}}

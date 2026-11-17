"""Presentations: dashboard pages with speaker notes, shown full screen on live data or from a snapshot.

Who sees one: its owner, and everyone when it is shared (sharing needs `dashboards.share`). Only the
owner (or an administrator) changes it. Page figures are always calculated for the person viewing,
so a shared review never shows more than they may see.

Publishing turns a draft into a review pack that cannot change: snapshot mode with an approved
snapshot is required, every page's widgets are copied with their filters written out, and afterwards
the pack cannot be edited or deleted. "Duplicate" makes an editable draft from it.
"""
import secrets

from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.models import utcnow
from app.core.permissions import ensure_can
from app.extensions import db
from app.modules.auth.models import User
from app.modules.dashboards.models import Dashboard
from app.modules.dashboards.service import DashboardService, effective_filters, widget_data
from app.modules.presentations.models import MODES, Presentation
from app.modules.snapshots import frozen
from app.modules.snapshots.models import Snapshot
from app.modules.snapshots.service import SnapshotService
from app.modules.work.service import person_ref

MAX_PAGES, MAX_NOTES = 40, 10000
PUBLISH_FIELDS = frozenset({"status", "published_at", "published_by_id", "pages"})


class PresentationService(CommandService):
    model = Presentation
    entity_type = "presentation"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"owner_id", "status", "published_at", "published_by_id"})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._publishing = False

    def base_query(self):
        stmt = super().base_query()
        if self.actor is None:
            return stmt
        return stmt.where(or_(Presentation.owner_id == self.actor.id, Presentation.is_shared.is_(True)))

    def _can_edit(self, p):
        return self.actor is None or self.actor.is_admin or p.owner_id == self.actor.id

    # ------------------------------------------------------------------ reads
    def list_all(self):
        rows = db.session.scalars(self.base_query().order_by(Presentation.updated_at.desc())).all()
        return {"items": [self.serialize(p) for p in rows]}

    def _snapshot(self, p):
        return db.session.get(Snapshot, p.snapshot_id) if p.snapshot_id else None

    def serialize(self, p: Presentation) -> dict:
        snap = self._snapshot(p)
        published = p.status == "published"
        dashboards = {d.id: d.name for d in db.session.scalars(select(Dashboard).where(
            Dashboard.id.in_([pg.get("dashboard_id") for pg in p.pages or []])))}
        return {
            "id": p.id, "name": p.name, "description": p.description, "is_shared": p.is_shared, "mode": p.mode,
            "owner": {"id": p.owner.id, "full_name": p.owner.full_name} if p.owner else None,
            "snapshot": {"id": snap.id, "label": snap.label, "as_of": snap.as_of.isoformat(), "status": snap.status}
            if snap else None, "snapshot_id": p.snapshot_id,
            "pages": [{"id": pg["id"], "dashboard_id": pg.get("dashboard_id"), "title": pg.get("title"),
                       "notes": pg.get("notes"),
                       "dashboard_name": pg.get("dashboard_name") or dashboards.get(pg.get("dashboard_id"))}
                      for pg in p.pages or []],
            "status": p.status, "published_at": p.published_at.isoformat() if p.published_at else None,
            "published_by": person_ref(db.session.get(User, p.published_by_id)) if p.published_by_id else None,
            "can_edit": self._can_edit(p) and not published,
            "can_publish": self._can_edit(p) and not published and p.mode == "snapshot" and bool(snap)
            and snap.status == "approved",
            "version": p.version,
        }

    # ------------------------------------------------------------------ validation
    def _check(self, data, obj=None):
        if data.get("is_shared"):
            ensure_can(self.actor, "dashboards.share", "You cannot share presentations")
        mode = data.get("mode", getattr(obj, "mode", "live"))
        if mode not in MODES:
            raise ValidationFailed("Choose live or snapshot", {"field": "mode"})
        snapshot_id = data.get("snapshot_id", getattr(obj, "snapshot_id", None))
        if "snapshot_id" in data and snapshot_id is not None:
            SnapshotService(self.actor, tenant_id=self.tenant_id).get(snapshot_id)
        if mode == "snapshot" and not snapshot_id:
            raise ValidationFailed("Choose the snapshot to show", {"field": "snapshot_id"})
        if "pages" in data:
            data["pages"] = self._check_pages(data["pages"])

    def _check_pages(self, pages):
        if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
            raise ValidationFailed(f"A presentation has 1 to {MAX_PAGES} pages", {"field": "pages"})
        dashboards = DashboardService(self.actor, tenant_id=self.tenant_id)
        used, out = set(), []
        for pg in pages:
            if not isinstance(pg, dict):
                raise ValidationFailed("Each page needs a dashboard", {"field": "pages"})
            try:
                d = dashboards.get(int(pg.get("dashboard_id")))
            except (TypeError, ValueError, NotFound) as exc:
                raise ValidationFailed("Each page needs a dashboard you can open", {"field": "pages"}) from exc
            pid = str(pg.get("id") or "")
            if not pid or pid in used:
                pid = f"p{secrets.token_hex(3)}"
            used.add(pid)
            notes = (pg.get("notes") or "").strip()
            if len(notes) > MAX_NOTES:
                raise ValidationFailed("Speaker notes are too long", {"field": "pages"})
            out.append({"id": pid, "dashboard_id": d.id, "title": (str(pg.get("title") or "").strip() or d.name)[:120],
                        "notes": notes or None})
        return out

    def validate_create(self, data):
        if self.actor is not None:
            data["owner_id"] = self.actor.id
        if not data.get("owner_id"):
            raise ValidationFailed("A presentation needs an owner")
        data.setdefault("pages", [])
        self._check(data)

    def apply_create(self, data):
        data.setdefault("status", "draft")
        return super().apply_create(data)

    def _clean(self, data):
        if self._publishing:  # publish() writes the protected publishing fields itself
            return dict(data)
        if self.actor is None:  # system jobs (seed) name the owner
            owner = data.get("owner_id")
            cleaned = super()._clean({k: v for k, v in data.items() if k != "owner_id"})
            return {**cleaned, "owner_id": owner} if owner else cleaned
        return super()._clean(data)

    def validate_update(self, obj, changes):
        if obj.status == "published":
            raise Conflict("A published review pack cannot be changed. Duplicate it to make a new version.")
        if not self._can_edit(obj):
            raise Forbidden("Only the person who made this presentation can change it")
        if not self._publishing:
            self._check(changes, obj)

    def validate_delete(self, obj):
        if obj.status == "published":
            raise Conflict("A published review pack is kept for the record")
        if not self._can_edit(obj):
            raise Forbidden("Only the person who made this presentation can delete it")

    # ------------------------------------------------------------------ publish and duplicate
    def publish(self, presentation_id, *, reason=None):
        p = self.get(presentation_id)
        if not self._can_edit(p):
            raise Forbidden("Only the person who made this presentation can publish it")
        if p.status == "published":
            raise Conflict("It is already published")
        snap = self._snapshot(p)
        if p.mode != "snapshot" or snap is None or snap.status != "approved":
            raise ValidationFailed("Publishing locks the review to an approved snapshot: choose one first",
                                   {"field": "snapshot_id"})
        pages = []
        for pg in p.pages:
            d = db.session.get(Dashboard, pg["dashboard_id"])
            if d is None or d.is_deleted:
                raise ValidationFailed(f"The dashboard on page “{pg['title']}” no longer exists", {"field": "pages"})
            widgets = [{**{k: v for k, v in w.items() if k != "view_id"}, "filters": effective_filters(w), "frozen": True}
                       for w in d.widgets or []]
            pages.append({**pg, "dashboard_name": d.name, "widgets": widgets})
        self._publishing = True
        try:
            return self.update(p.id, {"pages": pages, "status": "published", "published_at": utcnow(),
                                      "published_by_id": getattr(self.actor, "id", None)},
                               reason=reason or f"Published as a review pack on {snap.label}")
        finally:
            self._publishing = False

    def duplicate(self, presentation_id):
        p = self.get(presentation_id)
        pages = [{"dashboard_id": pg["dashboard_id"], "title": pg.get("title"), "notes": pg.get("notes")} for pg in p.pages]
        return self.create({"name": f"{p.name} (copy)"[:120], "description": p.description, "mode": p.mode,
                            "snapshot_id": p.snapshot_id, "pages": pages, "is_shared": False},
                           reason=f"Copied from “{p.name}”")

    # ------------------------------------------------------------------ figures
    def _page(self, p, page_id):
        pg = next((x for x in p.pages or [] if x["id"] == page_id), None)
        if pg is None:
            raise NotFound("Page not found")
        return pg

    def _widgets(self, p, pg):
        if pg.get("widgets") is not None:  # published: the frozen copy
            return pg["widgets"]
        d = db.session.get(Dashboard, pg["dashboard_id"])
        if d is None or d.is_deleted or d.tenant_id != self.tenant_id:
            raise NotFound("The dashboard on this page has been deleted")
        return d.widgets or []

    def page_data(self, presentation_id, page_id, *, fs=None):
        p = self.get(presentation_id)
        pg = self._page(p, page_id)
        snap = self._snapshot(p) if p.mode == "snapshot" else None
        if p.mode == "snapshot" and snap is None:
            raise NotFound("The snapshot of this presentation has been deleted")
        if snap is not None and fs is None:
            fs = frozen.FrozenSet(self.actor, snap)
        try:
            widgets = self._widgets(p, pg)
        except NotFound as exc:
            return {"page": {**pg, "widgets": None}, "widgets": [], "data": {}, "error": exc.message}
        data = {}
        for w in widgets:
            try:
                data[w["id"]] = frozen.widget_data(fs, w) if fs is not None else widget_data(self.actor, w)
            except AppError as exc:
                data[w["id"]] = {"error": exc.message}
        return {"page": {k: v for k, v in pg.items() if k != "widgets"}, "widgets": widgets, "data": data,
                "mode": p.mode, "as_of": snap.as_of.isoformat() if snap else None}

    def pack(self, presentation_id) -> dict:
        """Every page with its figures (for exports)."""
        p = self.get(presentation_id)
        snap = self._snapshot(p) if p.mode == "snapshot" else None
        fs = frozen.FrozenSet(self.actor, snap) if snap else None
        return {"presentation": self.serialize(p),
                "pages": [self.page_data(p.id, pg["id"], fs=fs) for pg in p.pages or []]}


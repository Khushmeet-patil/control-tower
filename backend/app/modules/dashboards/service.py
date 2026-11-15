"""Dashboards: personal ones for everyone, shared ones for people with `dashboards.share`.

Widget data is worked out for the person looking, through WorkItemService (their scope), with the
same filters the widget's drill-down link opens in the Portfolio. That is what makes a KPI equal to
the list it drills into, and keeps every viewer inside their own units.
"""
import secrets

from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.errors import AppError, Forbidden, ValidationFailed
from app.core.permissions import actor_can
from app.extensions import db
from app.modules.dashboards.models import CHARTS, GROUP_BY, WIDGET_TYPES, Dashboard
from app.modules.views.models import SavedView
from app.modules.work.progress import progress_map, weighted_average
from app.modules.work.service import WorkItemService, person_ref, portfolio_params

MAX_WIDGETS, MAX_FILTERS, MAX_LIMIT = 24, 30, 50
DEFAULT_LIMIT = {"table": 8, "progress": 10, "timeline": 20}


def _clean_filters(filters, where):
    filters = filters or {}
    if not isinstance(filters, dict) or len(filters) > MAX_FILTERS or not all(
            isinstance(k, str) and isinstance(v, (str, int)) for k, v in filters.items()):
        raise ValidationFailed("Filters must be simple name/value pairs", {"field": where})
    return {k: str(v) for k, v in filters.items() if str(v) != ""}


class DashboardService(CommandService):
    model = Dashboard
    entity_type = "dashboard"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"owner_id"})

    def base_query(self):
        """Your own dashboards and everyone's shared ones."""
        stmt = super().base_query()
        if self.actor is None:
            return stmt
        return stmt.where(or_(Dashboard.owner_id == self.actor.id, Dashboard.is_shared.is_(True)))

    # ------------------------------------------------------------------ reads
    def list_all(self):
        rows = db.session.scalars(self.base_query().order_by(Dashboard.is_shared.desc(), Dashboard.name)).all()
        return [self.serialize(d, brief=True) for d in rows]

    def serialize(self, d, brief=False):
        out = {
            "id": d.id, "name": d.name, "description": d.description, "is_shared": d.is_shared,
            "owner": {"id": d.owner.id, "full_name": d.owner.full_name} if d.owner else None,
            "can_edit": self._can_edit(d), "widget_count": len(d.widgets or []), "version": d.version,
        }
        if not brief:
            out["widgets"] = d.widgets or []
        return out

    def _can_edit(self, d):
        return self.actor is None or self.actor.is_admin or d.owner_id == self.actor.id

    # ------------------------------------------------------------------ validation
    def _view(self, view_id):
        """A saved Portfolio view the author can use (their own or a shared one)."""
        stmt = select(SavedView).where(SavedView.id == view_id, SavedView.tenant_id == self.tenant_id,
                                       SavedView.is_deleted.is_(False), SavedView.page == "work")
        if self.actor is not None:
            stmt = stmt.where(or_(SavedView.owner_id == self.actor.id, SavedView.is_shared.is_(True)))
        return db.session.scalar(stmt)

    def _check_widgets(self, widgets):
        if not isinstance(widgets, list) or len(widgets) > MAX_WIDGETS:
            raise ValidationFailed(f"A dashboard holds up to {MAX_WIDGETS} widgets", {"field": "widgets"})
        clean, seen = [], set()
        for n, w in enumerate(widgets):
            where = f"widgets.{n}"
            if not isinstance(w, dict) or w.get("type") not in WIDGET_TYPES:
                raise ValidationFailed("Choose a widget type", {"field": f"{where}.type"})
            title = str(w.get("title") or "").strip()[:100] or WIDGET_TYPES[w["type"]]
            wid = str(w.get("id") or "")[:20]
            if not wid.isalnum() or wid in seen:
                wid = secrets.token_hex(4)
            seen.add(wid)
            out = {"id": wid, "type": w["type"], "title": title, "width": 2 if w.get("width") in (2, "2") else 1}
            if w["type"] != "actions":
                view_id = w.get("view_id") or None
                filters = _clean_filters(w.get("filters"), f"{where}.filters")
                if view_id is not None:
                    view = self._view(int(view_id))
                    if view is None:
                        raise ValidationFailed("Choose one of your saved views or a shared one", {"field": f"{where}.view_id"})
                    filters = dict(view.filters or {})  # a copy, used if the view is deleted later
                out.update(view_id=int(view_id) if view_id else None, filters=filters)
                try:  # the filters must be ones the work list understands
                    WorkItemService(self.actor, tenant_id=self.tenant_id).count(portfolio_params(filters))
                except ValidationFailed as exc:
                    raise ValidationFailed(f"“{title}”: {exc.message}", {"field": f"{where}.filters"}) from exc
            if w["type"] == "chart":
                if w.get("group_by") not in GROUP_BY:
                    raise ValidationFailed("Choose what the chart groups by", {"field": f"{where}.group_by"})
                out["group_by"] = w["group_by"]
                out["chart"] = w.get("chart") if w.get("chart") in CHARTS else "bar"
            if w["type"] in DEFAULT_LIMIT:
                try:
                    limit = int(w.get("limit") or DEFAULT_LIMIT[w["type"]])
                except (TypeError, ValueError) as exc:
                    raise ValidationFailed("Rows shown must be a number", {"field": f"{where}.limit"}) from exc
                out["limit"] = max(1, min(MAX_LIMIT, limit))
            clean.append(out)
        return clean

    def _check(self, data):
        if "widgets" in data:
            data["widgets"] = self._check_widgets(data["widgets"] or [])
        if data.get("is_shared") and not actor_can(self.actor, "dashboards.share"):
            raise Forbidden("You do not have permission to share dashboards")

    def validate_create(self, data):
        data.setdefault("widgets", [])
        data.setdefault("is_shared", False)
        self._check(data)
        data["owner_id"] = getattr(self.actor, "id", None) or data.get("owner_id")
        if data["owner_id"] is None:
            raise ValidationFailed("A dashboard needs an owner")

    def apply_create(self, data):
        return Dashboard(**data)

    def _clean(self, data):
        owner = data.pop("owner_id", None)
        clean = super()._clean(data)
        if owner is not None and self.actor is None:  # system seeding only
            clean["owner_id"] = owner
        return clean

    def validate_update(self, obj, changes):
        if not self._can_edit(obj):
            raise Forbidden("Only the person who made this dashboard can change it")
        self._check(changes)

    def validate_delete(self, obj):
        if not self._can_edit(obj):
            raise Forbidden("Only the person who made this dashboard can delete it")

    # ------------------------------------------------------------------ widget data
    def data(self, dashboard_id):
        d = self.get(dashboard_id)
        out = {}
        for w in d.widgets or []:
            try:
                out[w["id"]] = widget_data(self.actor, w)
            except AppError as exc:  # one broken widget (e.g. a retired field) must not hide the others
                out[w["id"]] = {"error": exc.message}
        return {"widgets": out}


def effective_filters(widget) -> dict:
    """The widget's saved view's current filters, or its own copy if the view is gone."""
    if widget.get("view_id"):
        view = db.session.scalar(select(SavedView).where(SavedView.id == widget["view_id"],
                                                         SavedView.is_deleted.is_(False)))
        if view is not None:
            return dict(view.filters or {})
    return dict(widget.get("filters") or {})


def widget_data(actor, widget) -> dict:
    kind = widget["type"]
    if kind == "actions":
        from app.modules.rules.service import action_centre

        return {"entries": action_centre(actor)["top"]}
    filters = effective_filters(widget)
    params = portfolio_params(filters)
    work = WorkItemService(actor)
    base = {"filters": filters, "total": work.count(params)}
    if kind == "kpi":
        return {**base, "value": base["total"]}
    if kind == "table":
        page = work.list({**params, "per_page": str(widget.get("limit") or 8), "sort": filters.get("sort") or "planned_end"})
        return {**base, "items": page["items"]}
    if kind == "chart":
        return {**base, "group_by": widget["group_by"], "groups": _groups(actor, work, params, filters, widget["group_by"])}
    rows = work.rows(params)
    if kind == "progress":
        in_set = {r.id for r in rows}
        tops = [r for r in rows if r.parent_id not in in_set]
        progress = progress_map(actor.tenant_id, [r.id for r in tops])
        shown = sorted(tops, key=lambda r: (progress.get(r.id, 0), r.code))[: widget.get("limit") or 10]
        return {**base, "average": weighted_average(tops, progress), "counted": len(tops),
                "items": [{"id": r.id, "code": r.code, "title": r.title, "progress": progress.get(r.id, 0),
                           "status_id": r.status_id} for r in shown]}
    if kind == "timeline":
        dated = sorted((r for r in rows if r.planned_end), key=lambda r: (r.planned_end, r.code))[: widget.get("limit") or 20]
        return {**base, "items": [{
            "id": r.id, "code": r.code, "title": r.title, "status_id": r.status_id,
            "planned_start": r.planned_start.isoformat() if r.planned_start else None,
            "planned_end": r.planned_end.isoformat(), "is_overdue": work.is_overdue(r)} for r in dated]}
    raise ValidationFailed("Unknown widget type")


def _groups(actor, work, params, filters, group_by):
    """Counts per value of `group_by`; each group's filters list exactly the items it counts."""
    rows = work.rows(params)
    if group_by == "health":
        from app.modules.rules import engine

        results = engine.evaluate(actor.tenant_id, [r.id for r in rows])
        value_of = lambda r: (results.get(r.id).health if results.get(r.id) else None) or "na"  # noqa: E731
    else:
        value_of = lambda r: getattr(r, group_by)  # noqa: E731
    counts = {}
    for r in rows:
        v = value_of(r)
        counts[v] = counts.get(v, 0) + 1
    people = {}
    if group_by == "accountable_id":
        from app.modules.auth.models import User

        people = {u.id: person_ref(u) for u in db.session.scalars(select(User).where(User.id.in_([k for k in counts if k])))}
    out = []
    for value, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        drill = {**filters, group_by: str(value)} if value is not None else None
        out.append({"value": value, "count": count, "filters": drill,
                    "person": people.get(value) if group_by == "accountable_id" else None})
    return out

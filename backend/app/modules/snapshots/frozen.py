"""Capturing work figures into a snapshot, and calculating lists and dashboard widgets from them.

capture(tenant_id)
    The figures of every live work item now: lookups, owners, the unit path, progress (validated and
    weighted, from app.modules.work.progress), health (from the rules engine), open/overdue.

FrozenSet(actor, snapshot)
    The snapshot's rows that `actor` may see, and `select(params)` applying the same filters as the
    Portfolio list (see WorkItemService.query): level, units below, mine, involves, open, overdue,
    due within N days (counted from the snapshot date), health, search, custom fields and the plain
    column filters. Filters that cannot be answered from stored figures raise ValidationFailed rather
    than giving a wrong number.

widget_data(actor, fs, widget)
    The same output as app.modules.dashboards.service.widget_data, but from the snapshot. A review
    calculated from a snapshot therefore reads exactly as it did, whatever has been corrected since.

Who sees which rows follows the viewer's access now (a person who has left a team no longer sees its
work in old snapshots); the figures themselves never change.
"""
import operator
from datetime import date, timedelta

from sqlalchemy import select

from app.core.dates import today
from app.core.errors import ValidationFailed
from app.extensions import db
from app.modules.access.scope import is_global
from app.modules.auth.models import User
from app.modules.config.versioning import published_value_id
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from app.modules.snapshots.models import SnapshotItem
from app.modules.work.models import Assignment, WorkItem, WorkItemResponsible
from app.modules.work.service import closed_status_ids, portfolio_params, work_visibility_clause

# Plain column filters a snapshot can answer (name → type), as in the work list's FILTERABLE.
FIELDS = {
    "code": str, "title": str, "item_type_id": int, "status_id": int, "priority_id": int, "category_id": int,
    "action_type_id": int, "severity_id": int, "unit_id": int, "function_id": int, "accountable_id": int,
    "parent_id": int, "planned_start": date, "planned_end": date, "actual_end": date, "approval_status": str,
}
IGNORED = {"page", "per_page", "view", "layout"}
COMPARE = {"gte": operator.ge, "lte": operator.le, "gt": operator.gt, "lt": operator.lt}
TRUE = ("1", "true")
LIVE_ONLY = {"actions": "Top actions are personal and live; they are not kept in snapshots."}


def _initials(name):
    parts = (name or "").split()
    return "".join(p[0] for p in parts[:2]).upper() or "?"


# ---------------------------------------------------------------------- capture
def capture(tenant_id: int) -> list[dict]:
    from app.modules.rules import engine
    from app.modules.work.progress import progress_map

    items = db.session.scalars(select(WorkItem).where(WorkItem.tenant_id == tenant_id, WorkItem.is_deleted.is_(False))
                               .order_by(WorkItem.id)).all()
    ids = [w.id for w in items]
    if not ids:
        return []
    progress = progress_map(tenant_id, ids)
    results = engine.evaluate(tenant_id, ids)
    health_ids = engine.health_value_ids(tenant_id)
    responsible, assigned = {}, {}
    for item_id, user_id in db.session.execute(select(WorkItemResponsible.work_item_id, WorkItemResponsible.user_id)
                                               .where(WorkItemResponsible.work_item_id.in_(ids))):
        responsible.setdefault(item_id, []).append(user_id)
    for item_id, user_id in db.session.execute(select(Assignment.work_item_id, Assignment.person_id).where(
            Assignment.work_item_id.in_(ids), Assignment.is_deleted.is_(False))):
        assigned.setdefault(item_id, []).append(user_id)
    unit_ids = {w.unit_id for w in items if w.unit_id}
    paths = {}
    for desc, anc, depth in db.session.execute(select(OrgUnitClosure.descendant_id, OrgUnitClosure.ancestor_id,
                                                      OrgUnitClosure.depth).where(OrgUnitClosure.descendant_id.in_(unit_ids))):
        paths.setdefault(desc, []).append((depth, anc))
    unit_names = dict(db.session.execute(select(OrgUnit.id, OrgUnit.name).where(OrgUnit.id.in_(unit_ids))).all())
    people = dict(db.session.execute(select(User.id, User.full_name).where(
        User.id.in_({w.accountable_id for w in items if w.accountable_id}))).all())
    closed = set(closed_status_ids(tenant_id))
    now = today()

    rows = []
    for w in items:
        result = results.get(w.id)
        top = result.top if result else None
        if result is None or result.health is None:
            reason = "Not assessed (not in delivery)"
        elif top is None:
            reason = "No issues found"
        elif top.via_child_id:  # never name a child item: the viewer may not be allowed to open it
            reason = f"A child item is {engine.HEALTH_LABEL.get(top.outcome, top.outcome)}"
        else:
            reason = top.reason
        is_open = w.status_id not in closed
        rows.append({
            "work_item_id": w.id, "parent_id": w.parent_id, "code": w.code, "title": w.title,
            "item_type_id": w.item_type_id, "status_id": w.status_id, "priority_id": w.priority_id,
            "category_id": w.category_id, "action_type_id": w.action_type_id, "severity_id": w.severity_id,
            "unit_id": w.unit_id, "unit_name": unit_names.get(w.unit_id),
            "unit_path": [a for _, a in sorted(paths.get(w.unit_id, []), reverse=True)] or None,
            "function_id": w.function_id, "accountable_id": w.accountable_id,
            "accountable_name": people.get(w.accountable_id),
            "responsible_ids": sorted(responsible.get(w.id, [])) or None,
            "assignee_ids": sorted(set(assigned.get(w.id, []))) or None,
            "planned_start": w.planned_start, "planned_end": w.planned_end, "actual_end": w.actual_end,
            "progress": progress.get(w.id, 0), "weight": w.weight if w.weight is not None else 1,
            "health": result.health if result else None,
            "health_value_id": health_ids.get(result.health) if result and result.health else None,
            "health_reason": reason, "is_open": is_open,
            "is_overdue": bool(is_open and w.planned_end and w.planned_end < now),
            "approval_status": w.approval_status, "custom_fields": w.custom_fields or None,
        })
    return rows


def capture_people(tenant_id: int) -> list[dict]:
    """Every active person's capacity figures now (the Team capacity widget, frozen)."""
    from app.modules.capacity.engine import people_now
    from app.modules.rules.engine import capacity_buffer

    people = db.session.scalars(select(User).where(User.tenant_id == tenant_id, User.is_deleted.is_(False),
                                                   User.is_active.is_(True))).all()
    if not people:
        return []
    buffer = capacity_buffer(tenant_id)
    figures = people_now(tenant_id, [p.id for p in people], buffer)
    paths = {}
    for anc, desc, depth in db.session.execute(select(OrgUnitClosure.ancestor_id, OrgUnitClosure.descendant_id,
                                                      OrgUnitClosure.depth)):
        paths.setdefault(desc, []).append((depth, anc))
    out = []
    for p in people:
        f = figures[p.id]
        out.append({"person_id": p.id, "full_name": p.full_name, "job_title": p.job_title, "unit_id": p.unit_id,
                    "unit_name": p.unit.name if p.unit else None,
                    "unit_path": [a for _, a in sorted(paths.get(p.unit_id, []))] or None,
                    "function_name": p.function.name if p.function else None, "skill_ids": p.skill_ids or None,
                    "capacity_pct": f["capacity_pct"], "available_pct": f["available_pct"],
                    "usable_pct": f["usable_pct"], "load_pct": f["load_pct"], "free_pct": f["free_pct"],
                    "status": f["status"], "allocated_items": f["allocated_items"], "buffer_pct": buffer})
    return out


def people_rows(actor, snapshot, unit_id=None) -> list:
    """The snapshot's people the viewer may see now, optionally within a unit (and below)."""
    from app.modules.access.scope import person_visibility_clause
    from app.modules.snapshots.models import SnapshotPerson

    rows = db.session.scalars(select(SnapshotPerson).where(SnapshotPerson.snapshot_id == snapshot.id)).all()
    if actor is not None and (clause := person_visibility_clause(actor)) is not None:
        seen = set(db.session.scalars(select(User.id).where(User.id.in_([r.person_id for r in rows] or [0]), clause)))
        rows = [r for r in rows if r.person_id in seen]
    if unit_id:
        unit_id = int(unit_id)
        rows = [r for r in rows if unit_id in (r.unit_path or [])]
    return rows


def visible_ids(actor, ids) -> set[int]:
    """Items (live or deleted since) that the actor may see now."""
    ids = list(ids)
    if actor is None or is_global(actor):
        return set(ids)
    clause = work_visibility_clause(actor)
    return set(db.session.scalars(select(WorkItem.id).where(WorkItem.id.in_(ids), clause))) if ids else set()


# ---------------------------------------------------------------------- reading
def _convert(kind, raw, key):
    try:
        if kind is int:
            return int(raw)
        if kind is date:
            return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValidationFailed(f"Invalid value '{raw}' for filter {key}") from exc
    return str(raw)


def _compare(value, op, raw, kind, key):
    if op == "contains":
        return value is not None and str(raw).lower() in str(value).lower()
    if op == "in":
        wanted = {_convert(kind, v, key) for v in str(raw).split(",") if v != ""}
        return value in wanted
    target = _convert(kind, raw, key)
    if op == "":
        return value == target
    if value is None:
        return False
    return COMPARE[op](value, target)


def _unsupported(key):
    raise ValidationFailed(f"The filter “{key}” cannot be calculated from a snapshot", {"field": key})


def _custom_match(value, op, raw):
    if value is None:
        return False
    if isinstance(value, list):
        values = {str(v) for v in value}
        return (bool(values & set(str(raw).split(","))) if op == "in" else str(raw) in values)
    if op == "in":
        return str(value) in str(raw).split(",")
    if op == "contains":
        return str(raw).lower() in str(value).lower()
    if op in ("gte", "lte"):
        try:
            a, b = float(value), float(raw)
        except (TypeError, ValueError):
            a, b = str(value), str(raw)
        return a >= b if op == "gte" else a <= b
    return str(value) == str(raw)


class FrozenSet:
    def __init__(self, actor, snapshot):
        self.actor = actor
        self.snapshot = snapshot
        self.tenant_id = snapshot.tenant_id
        rows = db.session.scalars(select(SnapshotItem).where(SnapshotItem.snapshot_id == snapshot.id)
                                  .order_by(SnapshotItem.code)).all()
        self.by_id = {r.work_item_id: r for r in rows}
        seen = visible_ids(actor, self.by_id)
        self.rows = [r for r in rows if r.work_item_id in seen]

    def ancestors(self, row) -> set[int]:
        found, parent = set(), row.parent_id
        while parent and parent not in found and parent in self.by_id:
            found.add(parent)
            parent = self.by_id[parent].parent_id
        return found

    def select(self, params, *, sort=None) -> list:
        """Rows matching work list parameters (use portfolio_params() for Portfolio-style filters)."""
        params = {k: v for k, v in dict(params).items() if v not in (None, "") and k not in IGNORED}
        sort = params.pop("sort", None) or sort
        me = getattr(self.actor, "id", None)
        preds = []
        if params.pop("top_level", "") in TRUE:
            preds.append(lambda r: r.parent_id is None)
        if anc := params.pop("ancestor_id", None):
            anc = _convert(int, anc, "ancestor_id")
            preds.append(lambda r, anc=anc: anc in self.ancestors(r))
        if params.pop("include_descendants", "") in TRUE and (unit := params.pop("unit_id", None)):
            unit = _convert(int, unit, "unit_id")
            preds.append(lambda r, unit=unit: unit in (r.unit_path or []))
        roles = {
            "accountable": lambda r, p: r.accountable_id == p,
            "responsible": lambda r, p: p in (r.responsible_ids or []),
            "assigned": lambda r, p: p in (r.assignee_ids or []),
        }
        roles["any"] = lambda r, p: any(f(r, p) for f in list(roles.values())[:3])
        if mine := params.pop("mine", None):
            if mine not in roles or me is None:
                raise ValidationFailed(f"Unknown value for 'mine': {mine}")
            preds.append(lambda r, mine=mine: roles[mine](r, me))
        if who := params.pop("involves", None):
            who = _convert(int, who, "involves")
            preds.append(lambda r, who=who: roles["any"](r, who))
        if who := params.pop("responsible_id", None):
            who = _convert(int, who, "responsible_id")
            preds.append(lambda r, who=who: roles["responsible"](r, who))
        open_only = params.pop("open", "") in TRUE
        if who := params.pop("allocated_to", None):  # assigned on open work (assignment dates are not kept)
            who = _convert(int, who, "allocated_to")
            preds.append(lambda r, who=who: roles["assigned"](r, who))
            open_only = True
        if params.pop("validated", "") in TRUE:
            done = published_value_id(self.tenant_id, "status", "done")
            preds.append(lambda r: r.status_id == done and r.approval_status in (None, "approved"))
        if params.pop("overdue", "") in TRUE:
            preds.append(lambda r: r.is_overdue)
            open_only = True
        if due := params.pop("due_within", None):
            last = self.snapshot.as_of + timedelta(days=_convert(int, due, "due_within"))
            preds.append(lambda r, last=last: r.planned_end is not None and self.snapshot.as_of <= r.planned_end <= last)
            open_only = True
        if open_only:
            preds.append(lambda r: r.is_open)
        if health := {h for h in str(params.pop("health", "")).split(",") if h}:
            preds.append(lambda r, health=health: (r.health or "na") in health)
        if q := str(params.pop("q", "")).strip().lower():
            preds.append(lambda r, q=q: q in r.code.lower() or q in r.title.lower())
        for key, raw in params.items():
            if key.startswith("cf."):
                code, _, op = key[3:].partition("__")
                preds.append(lambda r, code=code, op=op, raw=raw: _custom_match((r.custom_fields or {}).get(code), op, raw))
                continue
            name, _, op = key.partition("__")
            if name not in FIELDS or op not in ("", "in", "gte", "lte", "gt", "lt", "contains"):
                _unsupported(key)
            if op == "in":  # check the values now, so a bad filter fails even when nothing matches
                [_convert(FIELDS[name], v, key) for v in str(raw).split(",") if v != ""]
            elif op != "contains":
                _convert(FIELDS[name], raw, key)
            preds.append(lambda r, name=name, op=op, raw=raw, key=key: _compare(getattr(r, name), op, raw, FIELDS[name], key))
        rows = [r for r in self.rows if all(p(r) for p in preds)]
        return self._sorted(rows, sort or "code")

    @staticmethod
    def _sorted(rows, sort):
        rows = sorted(rows, key=lambda r: r.code)
        for part in reversed([s.strip() for s in str(sort).split(",") if s.strip()]):
            desc, field = part.startswith("-"), part.lstrip("-")
            if field not in FIELDS and field not in ("progress", "health"):
                continue
            present = [r for r in rows if getattr(r, field) is not None]
            missing = [r for r in rows if getattr(r, field) is None]
            present.sort(key=lambda r: getattr(r, field), reverse=desc)
            rows = present + missing  # empty values last, as in the live list
        return rows


def row_out(r: SnapshotItem) -> dict:
    """A snapshot row in the shape of a serialized work item (what tables and widgets draw)."""
    return {
        "id": r.work_item_id, "code": r.code, "title": r.title, "parent_id": r.parent_id, "parent": None,
        "item_type_id": r.item_type_id, "status_id": r.status_id, "priority_id": r.priority_id,
        "category_id": r.category_id, "unit": {"id": r.unit_id, "name": r.unit_name} if r.unit_id else None,
        "unit_id": r.unit_id, "accountable_id": r.accountable_id,
        "accountable": {"id": r.accountable_id, "full_name": r.accountable_name, "initials": _initials(r.accountable_name),
                        "job_title": None} if r.accountable_id else None,
        "planned_start": r.planned_start.isoformat() if r.planned_start else None,
        "planned_end": r.planned_end.isoformat() if r.planned_end else None,
        "actual_end": r.actual_end.isoformat() if r.actual_end else None,
        "progress": r.progress, "is_overdue": r.is_overdue, "is_open": r.is_open, "approval_status": r.approval_status,
        "health": {"code": r.health, "value_id": r.health_value_id, "reason": r.health_reason, "flags": 0},
    }


def weighted(rows) -> int:
    rows = list(rows)
    if not rows:
        return 0
    total = sum(max(r.weight or 0, 0) for r in rows)
    if not total:
        return round(sum(r.progress for r in rows) / len(rows))
    return round(sum(r.progress * max(r.weight or 0, 0) for r in rows) / total)


def _has_people(snapshot) -> bool:
    from app.modules.snapshots.models import SnapshotPerson

    return bool(db.session.scalar(select(SnapshotPerson.id).where(SnapshotPerson.snapshot_id == snapshot.id).limit(1)))


def widget_data(fs: FrozenSet, widget) -> dict:
    """Widget figures from the snapshot (same output as the live widget_data)."""
    from app.modules.dashboards.service import effective_filters

    kind = widget["type"]
    if kind in LIVE_ONLY:
        return {"error": LIVE_ONLY[kind]}
    filters = widget.get("filters") if widget.get("frozen") else effective_filters(widget)
    filters = dict(filters or {})
    if kind == "capacity":  # people, not work: only the unit filter applies
        people = people_rows(fs.actor, fs.snapshot, filters.get("unit_id"))
        if not people:
            return {"error": "This snapshot has no capacity figures (it was taken before they were kept)."} \
                if not _has_people(fs.snapshot) else {"filters": {}, "total": 0, "items": [], "free_pct": 0, "buffer_pct": 0}
        people.sort(key=lambda r: (-r.load_pct, r.full_name))
        return {"filters": {}, "total": len(people), "free_pct": sum(r.free_pct for r in people),
                "buffer_pct": people[0].buffer_pct,
                "items": [{"person": {"id": r.person_id, "full_name": r.full_name, "initials": _initials(r.full_name),
                                      "job_title": r.job_title, "unit": r.unit_name, "function": r.function_name},
                           "skill_ids": r.skill_ids or [], "capacity_pct": r.capacity_pct,
                           "available_pct": r.available_pct, "usable_pct": r.usable_pct, "load_pct": r.load_pct,
                           "free_pct": r.free_pct, "status": r.status, "allocated_items": r.allocated_items,
                           "next_time_off": None} for r in people[: widget.get("limit") or 12]]}
    params = portfolio_params(filters)
    rows = fs.select(params, sort="planned_end" if kind == "table" else None)
    base = {"filters": filters, "total": len(rows)}
    if kind == "kpi":
        return {**base, "value": len(rows)}
    if kind == "table":
        return {**base, "items": [row_out(r) for r in rows[: widget.get("limit") or 8]]}
    if kind == "chart":
        group_by = widget["group_by"]
        value_of = (lambda r: r.health or "na") if group_by == "health" else (lambda r: getattr(r, group_by))
        counts, names = {}, {}
        for r in rows:
            v = value_of(r)
            counts[v] = counts.get(v, 0) + 1
            if group_by == "accountable_id" and v:
                names[v] = r.accountable_name
        groups = [{"value": v, "count": c, "filters": {**filters, group_by: str(v)} if v is not None else None,
                   "person": {"id": v, "full_name": names.get(v), "initials": _initials(names.get(v))}
                   if group_by == "accountable_id" and v else None}
                  for v, c in sorted(counts.items(), key=lambda kv: -kv[1])]
        return {**base, "group_by": group_by, "groups": groups}
    if kind == "progress":
        in_set = {r.work_item_id for r in rows}
        tops = [r for r in rows if r.parent_id not in in_set]
        shown = sorted(tops, key=lambda r: (r.progress, r.code))[: widget.get("limit") or 10]
        return {**base, "average": weighted(tops), "counted": len(tops),
                "items": [{"id": r.work_item_id, "code": r.code, "title": r.title, "progress": r.progress,
                           "status_id": r.status_id} for r in shown]}
    if kind == "timeline":
        dated = sorted((r for r in rows if r.planned_end), key=lambda r: (r.planned_end, r.code))[: widget.get("limit") or 20]
        return {**base, "items": [{
            "id": r.work_item_id, "code": r.code, "title": r.title, "status_id": r.status_id,
            "planned_start": r.planned_start.isoformat() if r.planned_start else None,
            "planned_end": r.planned_end.isoformat(), "is_overdue": r.is_overdue} for r in dated]}
    raise ValidationFailed("Unknown widget type")

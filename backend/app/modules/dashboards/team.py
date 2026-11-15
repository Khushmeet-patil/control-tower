"""Team view: a manager's unit, its people, their load and the work behind every number.

Only units the viewer manages can be opened (organisation-wide roles: any unit). Every count comes with
the Portfolio filters that list the same items, and is taken with WorkItemService.count() on those
filters, so the number and the list always agree.
"""
from sqlalchemy import select

from app.core.errors import Forbidden, NotFound
from app.core.tree import ancestor_ids, descendant_ids
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem, WorkItemClosure
from app.extensions import db
from app.modules.access.scope import managed_unit_ids, person_visibility_clause
from app.modules.auth.models import User
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from app.modules.rules.engine import capacity_buffer
from app.modules.work.progress import progress_map, weighted_average
from app.modules.work.service import WorkItemService, _int, allocation_load, person_ref, portfolio_params


def load_status(load: int, usable: int) -> str:
    """The prototype's capacity bands: above usable = overloaded, below half of it = underutilised."""
    if load > usable:
        return "overloaded"
    if load < usable / 2:
        return "underutilised"
    return "balanced"


def selectable_units(actor) -> list[OrgUnit]:
    managed = managed_unit_ids(actor)
    stmt = select(OrgUnit).where(OrgUnit.tenant_id == actor.tenant_id, OrgUnit.is_deleted.is_(False))
    if managed is not None:
        stmt = stmt.where(OrgUnit.id.in_(managed or [0]))
    return db.session.scalars(stmt.order_by(OrgUnit.name)).all()


def default_unit_id(actor, units) -> int | None:
    ids = {u.id for u in units}
    tops = [u for u in units if u.parent_id not in ids]
    own = next((u for u in tops if u.head_id == actor.id), None)
    return (own or (tops[0] if tops else None)).id if (own or tops) else None


def people_load(actor, person_ids, usable) -> dict[int, dict]:
    loads = allocation_load(actor.tenant_id, person_ids)
    return {pid: {"load_pct": v["pct"], "free_pct": max(0, usable - v["pct"]),
                  "status": load_status(v["pct"], usable), "allocated_items": v["items"]} for pid, v in loads.items()}


def initiatives_of(work, rows) -> list[dict]:
    """The top-most item the viewer can open above each row (or the row itself), without repeats."""
    out = {}
    for r in rows:
        chain = ancestor_ids(WorkItemClosure, r.id, include_self=True)  # top first
        visible = set(db.session.scalars(work.base_query().with_only_columns(WorkItem.id).where(WorkItem.id.in_(chain))))
        top_id = next((i for i in chain if i in visible), r.id)
        if top_id not in out:
            top = db.session.get(WorkItem, top_id)
            out[top_id] = {"id": top.id, "code": top.code, "title": top.title}
    return list(out.values())


def team_view(actor, unit_id=None) -> dict:
    units = selectable_units(actor)
    if not units:
        raise Forbidden("The team view is for people who manage a unit")
    by_id = {u.id: u for u in units}
    unit_id = _int(unit_id, "unit_id") if unit_id else default_unit_id(actor, units)
    if unit_id not in by_id:
        raise NotFound("Unit not found or not in your area") if db.session.get(OrgUnit, unit_id) is None \
            else Forbidden("You can only see the team view of units you manage")
    unit = by_id[unit_id]
    subtree = descendant_ids(OrgUnitClosure, [unit_id])
    work = WorkItemService(actor)
    buffer = capacity_buffer(actor.tenant_id)
    usable = 100 - buffer

    def metric(key, label, filters, tone=None):
        return {"key": key, "label": label, "value": work.count(portfolio_params(filters)), "filters": filters,
                "tone": tone}

    base = {"level": "all", "unit_id": str(unit_id)}
    # ---- people in the unit and below (only those the viewer may see)
    stmt = select(User).where(User.tenant_id == actor.tenant_id, User.is_deleted.is_(False), User.is_active.is_(True),
                              User.unit_id.in_(subtree))
    if (clause := person_visibility_clause(actor)) is not None:
        stmt = stmt.where(clause)
    people = db.session.scalars(stmt.order_by(User.full_name)).all()
    loads = people_load(actor, [p.id for p in people], usable)
    members = []
    action_type = published_value_id(actor.tenant_id, "item_type", "action")
    for p in people:
        pid = str(p.id)
        allocated = {"level": "all", "allocated_to": pid}
        allocated_rows = work.rows(portfolio_params(allocated))
        visible_allocated = len(allocated_rows)
        members.append({
            "person": {**person_ref(p), "unit": p.unit.name if p.unit else None,
                       "function": p.function.name if p.function else None},
            # The prototype's "Initiatives" column: the top-level work behind this person's load.
            "initiatives": initiatives_of(work, allocated_rows),
            **loads[p.id],
            # Items behind the load that this viewer cannot open (load still counts them).
            "hidden_items": max(0, loads[p.id]["allocated_items"] - visible_allocated),
            "counts": [
                {"key": "allocated", "label": "Allocated on", "value": visible_allocated, "filters": allocated},
                metric("accountable", "Accountable for (open)", {"level": "all", "accountable_id": pid, "open": "1"}),
                metric("open", "Involved in (open)", {"level": "all", "involves": pid, "open": "1"}),
                metric("overdue", "Overdue", {"level": "all", "involves": pid, "overdue": "1"}, "red"),
                metric("actions", "Open actions", {"level": "all", "item_type_id": str(action_type), "open": "1",
                                                   "responsible_id": pid}),
            ],
        })

    # ---- progress of the unit and of each unit directly below it
    def rollup(uid):  # weighted progress of the top-most visible items in the unit and below
        rows = work.rows(portfolio_params({"level": "all", "unit_id": str(uid)}))
        in_set = {r.id for r in rows}
        tops = [r for r in rows if r.parent_id not in in_set]
        return weighted_average(tops, progress_map(actor.tenant_id, [r.id for r in tops]))

    children = [u for u in units if u.parent_id == unit_id]
    subunits = []
    for u in children:
        f = {"level": "all", "unit_id": str(u.id)}
        subunits.append({
            "unit": {"id": u.id, "name": u.name}, "progress": rollup(u.id),
            "open": metric("open", "Open", {**f, "open": "1"}),
            "overdue": metric("overdue", "Overdue", {**f, "overdue": "1"}, "red"),
            "red": metric("red", "Red", {**f, "health": "red"}, "red"),
        })

    overloaded = sum(1 for m in members if m["status"] == "overloaded")
    return {
        "unit": {"id": unit.id, "name": unit.name, "head": person_ref(unit.head)},
        "units": [{"id": u.id, "name": u.name, "parent_id": u.parent_id if u.parent_id in by_id else None} for u in units],
        "buffer_pct": buffer, "usable_pct": usable,
        "progress": rollup(unit_id),
        "kpis": [
            {"key": "members", "label": "People", "value": len(members), "filters": None, "tone": None},
            metric("open", "Open items", {**base, "open": "1"}),
            metric("overdue", "Overdue", {**base, "overdue": "1"}, "red"),
            metric("red", "Red", {**base, "health": "red"}, "red"),
            metric("amber", "Amber", {**base, "health": "amber"}, "amber"),
            metric("approval", "Awaiting approval", {**base, "approval_status": "pending"}, "amber"),
            {"key": "overloaded", "label": "People overloaded", "value": overloaded, "filters": None,
             "tone": "red" if overloaded else None},
        ],
        "members": members,
        "subunits": subunits,
        "overdue_filters": {**base, "overdue": "1"},
    }

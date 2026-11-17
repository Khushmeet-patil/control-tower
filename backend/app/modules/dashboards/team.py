"""Team view: a manager's unit, its people, their load and the work behind every number.

Only units the viewer manages can be opened (organisation-wide roles: any unit). Every count comes with
the Portfolio filters that list the same items, and is taken with WorkItemService.count() on those
filters, so the number and the list always agree.
"""
from sqlalchemy import select

from app.core.errors import Forbidden, NotFound
from app.core.tree import descendant_ids
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem, WorkItemClosure
from app.extensions import db
from app.modules.access.scope import managed_unit_ids, person_visibility_clause
from app.modules.auth.models import User
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from app.modules.capacity.engine import rollup as capacity_rollup
from app.modules.rules.engine import capacity_buffer
from app.modules.work.progress import progress_map, weighted_average
from app.modules.work.service import WorkItemService, _int, person_ref, portfolio_params


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


def people_load(actor, person_ids) -> dict[int, dict]:
    """Today's capacity figures per person (see app.modules.capacity.engine)."""
    from app.modules.capacity.engine import people_now

    return people_now(actor.tenant_id, person_ids, capacity_buffer(actor.tenant_id))


def initiatives_by_item(work, item_ids) -> dict[int, dict]:
    """{item id: the top-most item above it (or itself) that the viewer can open}, in three queries."""
    item_ids = set(item_ids)
    if not item_ids:
        return {}
    chains = {}
    for anc, desc, depth in db.session.execute(select(WorkItemClosure.ancestor_id, WorkItemClosure.descendant_id,
                                                      WorkItemClosure.depth).where(WorkItemClosure.descendant_id.in_(item_ids))):
        chains.setdefault(desc, []).append((depth, anc))
    every = {a for chain in chains.values() for _, a in chain} | item_ids
    visible = set(db.session.scalars(work.base_query().with_only_columns(WorkItem.id).where(WorkItem.id.in_(every))))
    top_of = {}
    for i in item_ids:
        chain = [a for _, a in sorted(chains.get(i, [(0, i)]), reverse=True)]  # deepest ancestor (top) first
        top_of[i] = next((a for a in chain if a in visible), i)
    refs = {r.id: {"id": r.id, "code": r.code, "title": r.title} for r in db.session.execute(
        select(WorkItem.id, WorkItem.code, WorkItem.title).where(WorkItem.id.in_(set(top_of.values()))))}
    return {i: refs[t] for i, t in top_of.items() if t in refs}


def member_figures(actor, work, person_ids) -> dict[int, dict]:
    """Per person, the numbers behind the team table, worked out for everyone at once (a handful of
    queries instead of five per person).

    Each figure is the size of the Portfolio list its link opens (the filters in team_view): the same
    scoped items (WorkItemService.query), the same "involves" (accountable, responsible or assigned),
    "open", "overdue" and "allocated today" (allocated_pairs). tests/test_dashboards.py checks every
    figure against WorkItemService.count() for several viewers.
    """
    from collections import defaultdict

    from app.modules.work.models import WorkItemResponsible
    from app.modules.work.service import Assignment, allocated_pairs

    tid = actor.tenant_id
    people = list(person_ids)
    open_params = portfolio_params({"level": "all", "open": "1"})
    open_rows = work.light_rows(open_params, WorkItem.id, WorkItem.accountable_id, WorkItem.item_type_id)
    open_ids = work.query(open_params).with_only_columns(WorkItem.id).order_by(None)
    overdue = {r.id for r in work.light_rows(portfolio_params({"level": "all", "overdue": "1"}), WorkItem.id)}
    action_type = published_value_id(tid, "item_type", "action")
    actions = {r.id for r in open_rows if r.item_type_id == action_type}
    involved, responsible, accountable = defaultdict(set), defaultdict(set), defaultdict(int)
    for r in open_rows:
        involved[r.accountable_id].add(r.id)
        accountable[r.accountable_id] += 1
    for item_id, user_id in db.session.execute(select(WorkItemResponsible.work_item_id, WorkItemResponsible.user_id)
                                               .where(WorkItemResponsible.work_item_id.in_(open_ids))):
        involved[user_id].add(item_id)
        responsible[user_id].add(item_id)
    for item_id, user_id in db.session.execute(select(Assignment.work_item_id, Assignment.person_id).where(
            Assignment.work_item_id.in_(open_ids), Assignment.is_deleted.is_(False))):
        involved[user_id].add(item_id)
    allocated = defaultdict(set)
    if people:
        visible = work.base_query().with_only_columns(WorkItem.id).order_by(None)
        for pid, item_id in db.session.execute(allocated_pairs(tid, people).where(Assignment.work_item_id.in_(visible))):
            allocated[pid].add(item_id)
    tops = initiatives_by_item(work, {i for items in allocated.values() for i in items})
    out = {}
    for pid in people:
        mine = involved.get(pid, set())
        out[pid] = {
            "allocated": len(allocated.get(pid, ())), "accountable": accountable.get(pid, 0), "open": len(mine),
            "overdue": len(mine & overdue), "actions": len(responsible.get(pid, set()) & actions),
            "initiatives": list({tops[i]["id"]: tops[i] for i in sorted(allocated.get(pid, ())) if i in tops}.values()),
        }
    return out


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
    usable = 100 - buffer  # for a full-time person; each person's own figure allows for part time and leave

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
    loads = people_load(actor, [p.id for p in people])
    figures = member_figures(actor, work, [p.id for p in people])
    members = []
    action_type = published_value_id(actor.tenant_id, "item_type", "action")
    for p in people:
        pid, f = str(p.id), figures[p.id]
        count = lambda key, label, filters, tone=None: {"key": key, "label": label, "value": f[key],  # noqa: E731
                                                         "filters": filters, "tone": tone}
        members.append({
            "person": {**person_ref(p), "unit": p.unit.name if p.unit else None,
                       "function": p.function.name if p.function else None},
            "skill_ids": p.skill_ids or [], "backlog_days": p.backlog_days, "unit_id": p.unit_id,
            # The prototype's "Initiatives" column: the top-level work behind this person's load.
            "initiatives": f["initiatives"],
            **loads[p.id],
            # Items behind the load that this viewer cannot open (load still counts them).
            "hidden_items": max(0, loads[p.id]["allocated_items"] - f["allocated"]),
            "counts": [
                count("allocated", "Allocated on", {"level": "all", "allocated_to": pid}),
                count("accountable", "Accountable for (open)", {"level": "all", "accountable_id": pid, "open": "1"}),
                count("open", "Involved in (open)", {"level": "all", "involves": pid, "open": "1"}),
                count("overdue", "Overdue", {"level": "all", "involves": pid, "overdue": "1"}, "red"),
                count("actions", "Open actions", {"level": "all", "item_type_id": str(action_type), "open": "1",
                                                  "responsible_id": pid}),
            ],
        })

    # ---- progress of the unit and of each unit directly below it
    def rollup(uid):  # weighted progress of the top-most visible items in the unit and below
        rows = work.light_rows(portfolio_params({"level": "all", "unit_id": str(uid)}), WorkItem.id, WorkItem.parent_id,
                               WorkItem.weight)
        in_set = {r.id for r in rows}
        tops = [r for r in rows if r.parent_id not in in_set]
        return weighted_average(tops, progress_map(actor.tenant_id, [r.id for r in tops]))

    children = [u for u in units if u.parent_id == unit_id]
    subunits = []
    for u in children:
        f = {"level": "all", "unit_id": str(u.id)}
        below = descendant_ids(OrgUnitClosure, [u.id])
        subunits.append({
            "unit": {"id": u.id, "name": u.name}, "progress": rollup(u.id),
            "capacity": capacity_rollup([m for m in members if m["unit_id"] in below]),
            "open": metric("open", "Open", {**f, "open": "1"}),
            "overdue": metric("overdue", "Overdue", {**f, "overdue": "1"}, "red"),
            "red": metric("red", "Red", {**f, "health": "red"}, "red"),
        })

    overloaded = sum(1 for m in members if m["status"] == "overloaded")
    capacity = capacity_rollup(members)
    return {
        "unit": {"id": unit.id, "name": unit.name, "head": person_ref(unit.head)},
        "units": [{"id": u.id, "name": u.name, "parent_id": u.parent_id if u.parent_id in by_id else None} for u in units],
        "buffer_pct": buffer, "usable_pct": usable, "capacity": capacity,
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
            # The prototype's demand check: free capacity in points (1 point = 1% of one person's week).
            {"key": "free", "label": "Free capacity (pts)", "value": capacity["free_pct"], "filters": None, "tone": None},
        ],
        "members": members,
        "subunits": subunits,
        "overdue_filters": {**base, "overdue": "1"},
    }

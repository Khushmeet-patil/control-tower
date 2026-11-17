"""What-if scenarios: propose changes, measure their effect, apply them atomically (see models.py).

Who: people holding `scenarios.use`. A change may only be proposed for something the person could
change today (they manage the work item), and applying checks everything again, as the person applying.

Impact (`impact`), worked out without touching live data:
- schedule: proposed dates against dependencies ("starts before what it depends on finishes"), against
  the parent's dates, and finishing in the past;
- capacity: week by week, each affected person's load before and after, against their usable capacity
  (the same engine and buffer as the Team view), and how many overloaded weeks that makes.
"""
from datetime import date, timedelta

from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.models import utcnow
from app.core.pagination import paginate
from app.core.permissions import ensure_can
from app.extensions import db
from app.modules.access.scope import is_global
from app.modules.scenarios.models import (ASSIGNMENT_FIELDS, CHANGE_KINDS, ITEM_FIELDS, Scenario,
                                          ScenarioChange)
from app.modules.work.models import Assignment, WorkItem, WorkItemDependency
from app.modules.work.service import (MANAGE, AssignmentService, WorkItemService, closed_status_ids,
                                      person_ref)

DATE_FIELDS = {"planned_start", "planned_end", "start_date", "end_date"}


def _iso(v):
    return v.isoformat() if isinstance(v, date) else v


def _date(v):
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError as exc:
        raise ValidationFailed("Dates are written as YYYY-MM-DD") from exc


def _to_python(changes: dict) -> dict:
    return {k: _date(v) if k in DATE_FIELDS else v for k, v in (changes or {}).items()}


def _to_json(changes: dict) -> dict:
    return {k: _iso(v) for k, v in changes.items()}


class ScenarioService(CommandService):
    model = Scenario
    entity_type = "scenario"
    permissions = {"create": "scenarios.use", "update": "scenarios.use", "delete": "scenarios.use"}
    protected_fields = frozenset({"owner_id", "status", "applied_at", "applied_by_id", "applied_correlation_id"})

    def base_query(self):
        stmt = super().base_query()
        if self.actor is None or is_global(self.actor):
            return stmt
        return stmt.where(Scenario.owner_id == self.actor.id)

    def _work(self):
        return WorkItemService(self.actor, tenant_id=self.tenant_id, source=self.source,
                               correlation_id=self.correlation_id)

    def _assignments(self):
        return AssignmentService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                 correlation_id=self.correlation_id)

    def list(self, params):
        stmt = self.base_query()
        if status := params.get("status"):
            stmt = stmt.where(Scenario.status == status)
        return paginate(stmt.order_by(Scenario.updated_at.desc()), params, self.serialize)

    def changes_of(self, scenario_id) -> list[ScenarioChange]:
        return db.session.scalars(select(ScenarioChange).where(
            ScenarioChange.scenario_id == scenario_id, ScenarioChange.is_deleted.is_(False))
            .order_by(ScenarioChange.id)).all()

    def serialize(self, s: Scenario, detail=False) -> dict:
        changes = self.changes_of(s.id)
        out = {"id": s.id, "name": s.name, "description": s.description, "status": s.status,
               "owner": person_ref(s.owner), "change_count": len(changes),
               "applied_at": s.applied_at.isoformat() if s.applied_at else None,
               "applied_correlation_id": s.applied_correlation_id,
               "can_edit": s.status == "draft" and (self.actor is None or s.owner_id == self.actor.id),
               "updated_at": s.updated_at.isoformat(), "version": s.version}
        if detail:
            out["changes"] = [self.serialize_change(c) for c in changes]
        return out

    def serialize_change(self, c: ScenarioChange) -> dict:
        """The change with the current values next to the proposed ones."""
        out = {"id": c.id, "kind": c.kind, "target_id": c.target_id, "work_item_id": c.work_item_id,
               "changes": c.changes or {}, "base_version": c.base_version, "note": c.note, "current": {},
               "stale": False, "item": None, "person": None}
        item = assignment = None
        if c.kind == "item":
            item = db.session.get(WorkItem, c.target_id)
        elif c.kind in ("assignment", "remove_assignment"):
            assignment = db.session.get(Assignment, c.target_id)
            item = db.session.get(WorkItem, assignment.work_item_id) if assignment else None
        else:
            item = db.session.get(WorkItem, c.work_item_id)
        record = item if c.kind == "item" else assignment
        if record is not None:
            out["current"] = {f: _iso(getattr(record, f)) for f in (c.changes or {})}
            out["stale"] = bool(c.base_version and (record.version != c.base_version or record.is_deleted))
        elif c.kind != "new_assignment":
            out["stale"] = True
        if item is not None:
            out["item"] = {"id": item.id, "code": item.code, "title": item.title}
        if assignment is not None:
            out["person"] = person_ref(assignment.person)
        if c.kind == "new_assignment" and (c.changes or {}).get("person_id"):
            from app.modules.auth.models import User

            out["person"] = person_ref(db.session.get(User, c.changes["person_id"]))
        return out

    def validate_create(self, data):
        if not (data.get("name") or "").strip():
            raise ValidationFailed("Name the scenario", {"field": "name"})

    def apply_create(self, data):
        return Scenario(**data, owner_id=self.actor.id if self.actor else None, status="draft")

    def _editable(self, scenario_id) -> Scenario:
        s = self.get(scenario_id)
        if s.status != "draft":
            raise Conflict("This scenario was already applied or discarded")
        if self.actor is not None and s.owner_id != self.actor.id:
            raise Forbidden("Only the scenario's owner can change it")
        return s

    def validate_update(self, obj, changes):
        self._editable(obj.id)

    def validate_delete(self, obj):
        if self.actor is not None and obj.owner_id != self.actor.id and not is_global(self.actor):
            raise Forbidden("Only the scenario's owner can delete it")

    # ------------------------------------------------------------------ changes
    def _check_change(self, kind, target_id, work_item_id, changes) -> tuple[int | None, int | None, dict]:
        """Validate a proposed change; returns (target id, work item id, cleaned changes). The proposer
        must be able to make it today (manage the work item)."""
        work = self._work()
        if kind not in CHANGE_KINDS:
            raise ValidationFailed("Unknown kind of change", {"field": "kind"})
        changes = dict(changes or {})
        if kind == "item":
            allowed = ITEM_FIELDS
            item = work.get(target_id or 0)
        elif kind == "new_assignment":
            allowed = ASSIGNMENT_FIELDS
            item = work.get(work_item_id or 0)
            if not changes.get("person_id"):
                raise ValidationFailed("Choose a person", {"field": "person_id"})
        else:
            allowed = ASSIGNMENT_FIELDS if kind == "assignment" else ()
            a = self._assignments().get(target_id or 0)
            item = work.get(a.work_item_id)
            work_item_id = a.work_item_id
            if kind == "remove_assignment":
                changes = {}
        if bad := [f for f in changes if f not in allowed]:
            raise ValidationFailed(f"These cannot be planned in a scenario: {', '.join(bad)}", {"fields": bad})
        if kind in ("item", "assignment") and not changes:
            raise ValidationFailed("Propose at least one change")
        if work.access(item) != MANAGE:
            raise Forbidden(f"You cannot change {item.code}, so you cannot plan changes to it")
        py = _to_python(changes)
        if kind == "item":
            merged = {f: py.get(f, getattr(item, f)) for f in ("planned_start", "planned_end")}
            work._check_dates(merged["planned_start"], merged["planned_end"], "planned_end")
            for field in ("status_id", "priority_id"):
                if field in py:
                    work._check_lookup(field, py[field], previous=getattr(item, field))
            if "accountable_id" in py:
                work._check_person(py["accountable_id"], "accountable_id")
        else:
            if "person_id" in py:
                work._check_person(py["person_id"], "person_id")
            if "allocation_pct" in py and not (isinstance(py["allocation_pct"], int) and 0 <= py["allocation_pct"] <= 100):
                raise ValidationFailed("Allocation is 0 to 100%", {"field": "allocation_pct"})
            if "role_id" in py:
                work._check_lookup("role_id", py["role_id"], list_code="functional_role")
        return target_id, (item.id if kind != "item" else None) or work_item_id, _to_json(py)

    def add_change(self, scenario_id, data: dict) -> ScenarioChange:
        s = self._editable(scenario_id)
        kind = data.get("kind")
        target_id, work_item_id, changes = self._check_change(kind, data.get("target_id"), data.get("work_item_id"),
                                                              data.get("changes"))
        base = None
        if kind == "item":
            base = db.session.get(WorkItem, target_id).version
        elif kind in ("assignment", "remove_assignment"):
            base = db.session.get(Assignment, target_id).version
        svc = ScenarioChangeService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                    correlation_id=self.correlation_id)
        with self.transaction():
            change = svc.create({"scenario_id": s.id, "kind": kind, "target_id": target_id,
                                 "work_item_id": work_item_id, "changes": changes, "base_version": base,
                                 "note": data.get("note")}, reason=f"Planned in scenario “{s.name}”")
            s.updated_at = utcnow()
        return change

    def update_change(self, scenario_id, change_id, data: dict) -> ScenarioChange:
        s = self._editable(scenario_id)
        c = self._change(s, change_id)
        changes = data.get("changes", c.changes)
        _, _, cleaned = self._check_change(c.kind, c.target_id, c.work_item_id, changes)
        svc = ScenarioChangeService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                    correlation_id=self.correlation_id)
        return svc.update(c.id, {"changes": cleaned, "note": data.get("note", c.note)}, reason="Scenario edited")

    def remove_change(self, scenario_id, change_id):
        s = self._editable(scenario_id)
        c = self._change(s, change_id)
        ScenarioChangeService(self.actor, tenant_id=self.tenant_id, source=self.source,
                              correlation_id=self.correlation_id).delete(c.id, reason="Removed from scenario")

    def _change(self, s, change_id) -> ScenarioChange:
        c = db.session.get(ScenarioChange, change_id)
        if c is None or c.scenario_id != s.id or c.is_deleted:
            raise NotFound("Change not found")
        return c

    # ------------------------------------------------------------------ impact
    def _proposed(self, changes):
        """In-memory picture: {item id: proposed fields}, and assignments before/after as plain dicts."""
        items, before, after = {}, {}, {}
        for c in changes:
            py = _to_python(c.changes)
            if c.kind == "item":
                items.setdefault(c.target_id, {}).update(py)
            elif c.kind == "new_assignment":
                after[f"new{c.id}"] = {"person_id": py.get("person_id"), "work_item_id": c.work_item_id,
                                       "allocation_pct": py.get("allocation_pct") or 0,
                                       "start_date": py.get("start_date"), "end_date": py.get("end_date")}
            else:
                a = db.session.get(Assignment, c.target_id)
                if a is None or a.is_deleted:
                    continue
                row = {"person_id": a.person_id, "work_item_id": a.work_item_id, "allocation_pct": a.allocation_pct,
                       "start_date": a.start_date, "end_date": a.end_date}
                before[a.id] = row
                after[a.id] = None if c.kind == "remove_assignment" else {**row, **py}
        return items, before, after

    def impact(self, scenario_id, weeks: int = 12) -> dict:
        s = self.get(scenario_id)
        weeks = max(1, min(26, int(weeks or 12)))
        changes = self.changes_of(s.id)
        items, before, after = self._proposed(changes)
        return {"scenario": self.serialize(s), "weeks": weeks, "schedule": self._schedule(items),
                "capacity": self._capacity(items, before, after, weeks)}

    def _schedule(self, items: dict) -> list[dict]:
        """Date problems the proposed dates would cause."""
        if not items:
            return []
        problems = []
        ids = list(items)
        rows = {w.id: w for w in db.session.scalars(select(WorkItem).where(WorkItem.id.in_(ids)))}

        def dates(item):
            p = items.get(item.id, {})
            return p.get("planned_start", item.planned_start), p.get("planned_end", item.planned_end)

        edges = db.session.execute(select(WorkItemDependency.work_item_id, WorkItemDependency.depends_on_id).where(
            or_(WorkItemDependency.work_item_id.in_(ids), WorkItemDependency.depends_on_id.in_(ids)))).all()
        involved = {i for e in edges for i in e} | set(ids)
        involved_rows = {w.id: w for w in db.session.scalars(select(WorkItem).where(
            WorkItem.id.in_(involved), WorkItem.is_deleted.is_(False)))}
        for item_id, dep_id in edges:
            a, b = involved_rows.get(item_id), involved_rows.get(dep_id)
            if a is None or b is None:
                continue
            a_start, _ = dates(a)
            _, b_end = dates(b)
            if a_start and b_end and a_start <= b_end:
                problems.append({"kind": "dependency", "item": _brief(a), "other": _brief(b),
                                 "message": f"{a.code} would start on {a_start:%d %b} but depends on {b.code}, "
                                            f"which finishes on {b_end:%d %b}"})
        for item_id, item in rows.items():
            start, end = dates(item)
            if item.parent_id:
                parent = db.session.get(WorkItem, item.parent_id)
                p_start, p_end = dates(parent)
                if end and p_end and end > p_end:
                    problems.append({"kind": "parent", "item": _brief(item), "other": _brief(parent),
                                     "message": f"{item.code} would finish {end:%d %b}, after its parent {parent.code} ({p_end:%d %b})"})
                if start and p_start and start < p_start:
                    problems.append({"kind": "parent", "item": _brief(item), "other": _brief(parent),
                                     "message": f"{item.code} would start {start:%d %b}, before its parent {parent.code} ({p_start:%d %b})"})
            children = db.session.scalars(select(WorkItem).where(WorkItem.parent_id == item.id,
                                                                 WorkItem.is_deleted.is_(False))).all()
            for child in children:
                c_start, c_end = dates(child)
                if end and c_end and c_end > end:
                    problems.append({"kind": "child", "item": _brief(item), "other": _brief(child),
                                     "message": f"{child.code} finishes {c_end:%d %b}, after {item.code}'s new finish ({end:%d %b})"})
            if "planned_end" in items[item_id] and end and end < today():
                problems.append({"kind": "past", "item": _brief(item), "other": None,
                                 "message": f"{item.code} would be due on {end:%d %b}, which has already passed"})
        return problems

    def _capacity(self, items, before, after, weeks) -> list[dict]:
        from app.modules.auth.models import User
        from app.modules.capacity import engine
        from app.modules.rules.engine import capacity_buffer

        people = {r["person_id"] for r in list(before.values()) + [a for a in after.values() if a]}
        status_changed = [i for i, p in items.items() if "status_id" in p]
        if status_changed:
            people |= set(db.session.scalars(select(Assignment.person_id).where(
                Assignment.work_item_id.in_(status_changed), Assignment.is_deleted.is_(False))))
        people.discard(None)
        if not people:
            return []
        buffer = capacity_buffer(self.tenant_id)
        base = engine.weekly(self.tenant_id, people, buffer, weeks)
        closed = set(closed_status_ids(self.tenant_id))
        status_of = dict(db.session.execute(select(WorkItem.id, WorkItem.status_id).where(
            WorkItem.id.in_({r["work_item_id"] for r in list(before.values()) + [a for a in after.values() if a]}
                            | set(status_changed)))).all())

        def is_open(item_id, proposed):
            status = items.get(item_id, {}).get("status_id", status_of.get(item_id)) if proposed else status_of.get(item_id)
            return status not in closed

        def share(row, start, end, proposed):
            if row is None or row["person_id"] is None or not is_open(row["work_item_id"], proposed):
                return 0
            s, e = row.get("start_date"), row.get("end_date")
            return row["allocation_pct"] if (s is None or s <= end) and (e is None or e >= start) else 0

        # assignments not edited in the scenario, on items whose status the scenario changes
        untouched = []
        if status_changed:
            untouched = [{"person_id": a.person_id, "work_item_id": a.work_item_id, "allocation_pct": a.allocation_pct,
                          "start_date": a.start_date, "end_date": a.end_date, "id": a.id}
                         for a in db.session.scalars(select(Assignment).where(
                             Assignment.work_item_id.in_(status_changed), Assignment.is_deleted.is_(False)))
                         if a.id not in before]
        names = {u.id: u for u in db.session.scalars(select(User).where(User.id.in_(people)))}
        out = []
        for pid in sorted(people, key=lambda p: names[p].full_name if p in names else ""):
            rows = []
            for week in base[pid]:
                start = date.fromisoformat(week["week_start"])
                end = start + timedelta(days=6)
                delta = 0
                for key, old in before.items():
                    if old["person_id"] == pid:
                        delta -= share(old, start, end, False)
                for key, new in after.items():
                    if new and new["person_id"] == pid:
                        delta += share(new, start, end, True)
                for row in untouched:
                    if row["person_id"] == pid:
                        delta += share(row, start, end, True) - share(row, start, end, False)
                load = max(0, week["load_pct"] + delta)
                rows.append({"week_start": week["week_start"], "usable_pct": week["usable_pct"],
                             "load_before": week["load_pct"], "load_after": load,
                             "status_before": week["status"],
                             "status_after": engine.load_status(load, week["usable_pct"], week["available_pct"])})
            over_before = sum(1 for r in rows if r["status_before"] == "overloaded")
            over_after = sum(1 for r in rows if r["status_after"] == "overloaded")
            out.append({"person": person_ref(names.get(pid)), "weeks": rows,
                        "overloaded_weeks_before": over_before, "overloaded_weeks_after": over_after,
                        "peak_before": max((r["load_before"] for r in rows), default=0),
                        "peak_after": max((r["load_after"] for r in rows), default=0)})
        return out

    # ------------------------------------------------------------------ apply / discard
    def apply(self, scenario_id, reason=None) -> dict:
        s = self._editable(scenario_id)
        changes = self.changes_of(s.id)
        if not changes:
            raise ValidationFailed("The scenario has no changes to apply")
        stale = [self.serialize_change(c) for c in changes]
        stale = [c for c in stale if c["stale"]]
        if stale:
            raise Conflict("Some records changed since they were planned. Review those changes, then apply again.",
                           {"stale": [{"id": c["id"], "item": c["item"]} for c in stale]})
        work, assignments = self._work(), self._assignments()
        why = reason or f"Scenario “{s.name}” applied"
        touched = set()
        with self.transaction():
            for c in changes:
                py = _to_python(c.changes)
                if c.kind == "item":
                    item = work.update(c.target_id, py, expected_version=c.base_version, reason=why)
                    touched |= {item.accountable_id}
                elif c.kind == "assignment":
                    a = assignments.update(c.target_id, py, expected_version=c.base_version, reason=why)
                    touched.add(a.person_id)
                elif c.kind == "remove_assignment":
                    a = assignments.get(c.target_id)
                    if a.version != c.base_version:
                        raise Conflict("An assignment changed since it was planned")
                    assignments.delete(c.target_id, reason=why)
                    touched.add(a.person_id)
                else:
                    a = assignments.create({"work_item_id": c.work_item_id, **py}, reason=why)
                    touched.add(a.person_id)
            s.status, s.applied_at = "applied", utcnow()
            s.applied_by_id = getattr(self.actor, "id", None)
            s.applied_correlation_id = self.correlation_id
            s.updated_by_id = s.applied_by_id
            self._audit(s.id, "apply", field="status", old="draft", new="applied", reason=why)
            from app.modules.notifications.service import notify

            notify(self.tenant_id, touched, "scenario_applied", f"Scenario “{s.name}” changed your work",
                   body=f"{len(changes)} planned change{'s' if len(changes) != 1 else ''} applied by "
                        f"{getattr(self.actor, 'full_name', 'the system')}.",
                   link="/pages/my-work.html", entity=("scenario", s.id), actor=self.actor,
                   source=self.source)
        return self.serialize(s, detail=True)

    def discard(self, scenario_id, reason=None) -> dict:
        s = self._editable(scenario_id)
        with self.transaction():
            s.status = "discarded"
            s.updated_by_id = getattr(self.actor, "id", None)
            self._audit(s.id, "update", field="status", old="draft", new="discarded", reason=reason or "Discarded")
        return self.serialize(s)

    def duplicate(self, scenario_id) -> Scenario:
        """Copy a scenario (any status) as a new draft, with every change re-checked against today's data."""
        ensure_can(self.actor, "scenarios.use")
        s = self.get(scenario_id)
        with self.transaction():
            copy = self.create({"name": f"{s.name} (copy)"[:160], "description": s.description},
                               reason=f"Copied from scenario “{s.name}”")
            for c in self.changes_of(s.id):
                if c.kind != "new_assignment" and c.target_id is None:
                    continue
                try:
                    self.add_change(copy.id, {"kind": c.kind, "target_id": c.target_id, "work_item_id": c.work_item_id,
                                              "changes": c.changes, "note": c.note})
                except (NotFound, Forbidden, ValidationFailed):
                    continue  # no longer possible: left out of the copy
        return copy


class ScenarioChangeService(CommandService):
    model = ScenarioChange
    entity_type = "scenario_change"
    permissions = {"create": "scenarios.use", "update": "scenarios.use", "delete": "scenarios.use"}


def _brief(item):
    return {"id": item.id, "code": item.code, "title": item.title} if item else None

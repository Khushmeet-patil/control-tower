"""The manager's weekly review: the sections of the reference prototype's Action Centre that sit below
the KPIs and Top 5 (see reference/MY Control Tower 1.html, VIEWS.dash):

    progress board · hold points ("where I am needed") · watchlist · blockers and pending decisions ·
    upcoming milestones (14 days) · team capacity · technical completion vs adoption ·
    milestones completed per month

Everything is limited to the work the viewer can see (`rows` comes from their scoped query). Where a
section shows a number, it carries the Portfolio filters that list the same items.
"""
from datetime import date

from sqlalchemy import select

from app.core.dates import today
from app.extensions import db
from app.modules.access.scope import person_visibility_clause
from app.modules.auth.models import User
from app.modules.config.versioning import published_list, published_value_id
from app.modules.rules import engine
from app.modules.work.models import WorkItemClosure, WorkItemResponsible
from app.modules.work.progress import progress_map
from app.modules.work.service import person_ref

BOARD_N, HOLD_N, CAPACITY_N, LIST_N, UPCOMING_DAYS, MONTHS = 15, 14, 30, 15, 14, 6
RANK = {"red": 0, "amber": 1, "grey": 2, "green": 3}


class Review:
    def __init__(self, actor, rows, results, view, closed, bonus, inbox):
        self.actor, self.rows, self.results, self.view, self.bonus, self.inbox = actor, rows, results, view, bonus, inbox
        self.tid = actor.tenant_id
        self.by_id = {r.id: r for r in rows}
        self.closed = closed
        self.today = today()
        value = lambda lst, code: published_value_id(self.tid, lst, code)  # noqa: E731
        self.milestone, self.action = value("item_type", "milestone"), value("item_type", "action")
        self.done, self.cancelled = value("status", "done"), value("status", "cancelled")
        self.blocker = value("action_type", "blocker")
        self.decisions = {i for i in (value("action_type", "decision"), value("action_type", "approval")) if i}
        self.responsibles = {}
        for item_id, user_id in db.session.execute(select(WorkItemResponsible.work_item_id, WorkItemResponsible.user_id)
                                                   .where(WorkItemResponsible.work_item_id.in_(list(self.by_id) or [0]))):
            self.responsibles.setdefault(item_id, []).append(user_id)

    # ------------------------------------------------------------------ helpers
    def health(self, r):
        res = self.results.get(r.id)
        return res.health if res else None

    def is_open(self, r):
        return r.status_id not in self.closed

    def holder(self, r):
        """The prototype's "action holder" / "owner": the first responsible owner."""
        ids = self.responsibles.get(r.id) or [r.accountable_id]
        return self.view.person(ids[0])

    def below(self, item_id):
        ids = set(db.session.scalars(select(WorkItemClosure.descendant_id).where(
            WorkItemClosure.ancestor_id == item_id, WorkItemClosure.depth > 0)))
        return [self.by_id[i] for i in ids if i in self.by_id]

    def top_of(self, r):
        """The top-level item (as far as the viewer can see) a row belongs to."""
        seen = set()
        while r.parent_id in self.by_id and r.id not in seen:
            seen.add(r.id)
            r = self.by_id[r.parent_id]
        return r

    def next_milestone(self, item_id):
        open_ms = [r for r in self.below(item_id) if r.item_type_id == self.milestone and self.is_open(r)]
        return min(open_ms, key=lambda r: (r.planned_end or date.max, r.code), default=None)

    def next_action(self, item_id):
        acts = [r for r in self.below(item_id) if r.item_type_id == self.action and self.is_open(r)
                and r.action_type_id not in self.decisions]
        return min(acts, key=lambda r: (r.planned_end or date.max, r.code), default=None)

    def dated(self, r, key="planned_end"):
        value = getattr(r, key)
        return value.isoformat() if value else None

    def age(self, r):
        return max(0, (self.today - (r.planned_start or r.created_at.date())).days)

    # ------------------------------------------------------------------ sections
    def tops_in_delivery(self):
        return [r for r in self.rows if r.parent_id not in self.by_id and self.health(r)]

    def board(self):
        tops = sorted(self.tops_in_delivery(), key=lambda r: (RANK[self.health(r)], -self.bonus.get(r.priority_id, 0), r.code))
        progress = progress_map(self.tid, [r.id for r in tops])
        out = []
        for r in tops[:BOARD_N]:
            ms, act = self.next_milestone(r.id), self.next_action(r.id)
            out.append({
                **self.view.ref(r.id), "category_id": r.category_id, "priority_id": r.priority_id,
                "accountable": self.view.person(r.accountable_id), "health": self.view.summary(self.results[r.id]),
                "progress": progress.get(r.id, 0),
                "to_validate": sum(1 for x in self.below(r.id) if x.approval_status == "pending"),
                "next_milestone": {**self.view.ref(ms.id), "planned_end": self.dated(ms), "holder": self.holder(ms)} if ms else None,
                "next_action": {**self.view.ref(act.id), "planned_end": self.dated(act), "owner": self.holder(act)} if act else None,
            })
        return out

    def hold_points(self):
        """Where I am needed, most urgent first (the prototype's ordering)."""
        points = []

        def add(rank, kind, r, when, sort_date=None, owner=None, **extra):
            top = self.top_of(r)
            points.append({"rank": rank, "type": kind, "item": self.view.ref(r.id),
                           "in": self.view.ref(top.id) if top.id != r.id else None,
                           "owner": owner if owner is not None else self.holder(r), "when": when,
                           "sort": (sort_date or date.max).isoformat(), **extra})

        for req in self.inbox:
            r = self.by_id.get(req["work_item"]["id"])
            if r is not None:
                add(0, "Validate", r, f"done {r.actual_end:%d %b %Y}" if r.actual_end else "",
                    owner=req["submitted_by"], approval_id=req["id"])
        for r in self.rows:
            if not self.is_open(r):
                continue
            late = bool(r.planned_end and r.planned_end < self.today)
            if r.item_type_id == self.action and r.action_type_id == self.blocker:
                add(1, "Blocker", r, f"{self.age(r)} days old", r.planned_start)
            elif r.item_type_id == self.action and r.action_type_id in self.decisions:
                add(0.5 if late else 2, "Decision", r,
                    (f"overdue {r.planned_end:%d %b %Y}" if late else f"due {r.planned_end:%d %b %Y}") if r.planned_end else "",
                    r.planned_end, action_type_id=r.action_type_id)
            elif r.item_type_id == self.milestone and late and self.health(self.top_of(r)):
                add(3, "Late milestone", r, f"due {r.planned_end:%d %b %Y}", r.planned_end)
        progress = progress_map(self.tid, [r.id for r in self.tops_in_delivery()])
        for r in self.tops_in_delivery():
            if not self.next_milestone(r.id) and progress.get(r.id, 0) < 100:
                add(5, "Setup gap", r, "no next milestone", owner=self.view.person(r.accountable_id))
        points.sort(key=lambda p: (p["rank"], p["sort"], p["item"]["code"]))
        return points

    def watchlist(self):
        """Signals (ready for rollout, built not adopted, quick wins) and stale updates, grouped by rule."""
        stale_rules = {r["code"] for r in engine.published_rules(self.tid) if r["rule_type"] == "stale"}
        watch = {}
        for r in self.rows:
            res = self.results.get(r.id)
            for f in (res.findings if res else []):
                if f.source_id == r.id and (f.kind == "signal" or f.rule_code in stale_rules):
                    watch.setdefault(f.rule_name, []).append(self.view.ref(r.id))
        return [{"rule": k, "count": len(v), "items": v} for k, v in sorted(watch.items())]

    def blockers_and_decisions(self):
        rows = [r for r in self.rows if self.is_open(r) and r.item_type_id == self.action
                and (r.action_type_id == self.blocker or r.action_type_id in self.decisions)]
        rows.sort(key=lambda r: (r.action_type_id != self.blocker, r.planned_end or date.max, r.code))
        return [{**self.view.ref(r.id), "action_type_id": r.action_type_id, "severity_id": r.severity_id,
                 "is_blocker": r.action_type_id == self.blocker, "age_days": self.age(r), "planned_end": self.dated(r),
                 "is_late": bool(r.planned_end and r.planned_end < self.today), "owner": self.holder(r)}
                for r in rows[:LIST_N]], len(rows)

    def upcoming_milestones(self):
        horizon = date.fromordinal(self.today.toordinal() + UPCOMING_DAYS)
        rows = sorted((r for r in self.rows if r.item_type_id == self.milestone and self.is_open(r) and r.planned_end
                       and self.today <= r.planned_end <= horizon), key=lambda r: (r.planned_end, r.code))
        out = []
        for r in rows[:LIST_N]:
            top = self.top_of(r)
            out.append({**self.view.ref(r.id), "planned_end": self.dated(r), "status_id": r.status_id,
                        "in": self.view.ref(top.id) if top.id != r.id else None, "holder": self.holder(r)})
        return out, {"level": "all", "item_type_id": str(self.milestone), "due_within": str(UPCOMING_DAYS)}

    def capacity(self):
        from app.modules.dashboards.team import people_load

        stmt = select(User).where(User.tenant_id == self.tid, User.is_deleted.is_(False), User.is_active.is_(True))
        if (clause := person_visibility_clause(self.actor)) is not None:
            stmt = stmt.where(clause)
        people = db.session.scalars(stmt).all()
        usable = 100 - engine.capacity_buffer(self.tid)
        loads = people_load(self.actor, [p.id for p in people], usable)
        open_actions = {}
        for r in self.rows:
            if r.item_type_id == self.action and self.is_open(r):
                for pid in self.responsibles.get(r.id, []):
                    open_actions[pid] = open_actions.get(pid, 0) + 1
        rows = [{"person": person_ref(p), **loads[p.id], "open_actions": open_actions.get(p.id, 0),
                 "open_actions_filters": {"level": "all", "item_type_id": str(self.action), "open": "1",
                                          "responsible_id": str(p.id)}}
                for p in people if loads[p.id]["allocated_items"] or open_actions.get(p.id)]
        rows.sort(key=lambda x: (-x["load_pct"], x["person"]["full_name"]))
        return rows[:CAPACITY_N], usable

    def adoption(self):
        tracked = [r for r in self.rows if r.parent_id not in self.by_id and r.status_id != self.cancelled]
        stages = sorted((v for v in published_list(self.tid, "adoption_stage").values() if v["is_active"]),
                        key=lambda v: (v["sort_order"], v["id"]))
        return {"total": len(tracked), "stages": [
            {"stage_id": v["id"], "count": sum(1 for r in tracked if v["id"] in (r.adoption_stage_ids or []))}
            for v in stages]}

    def completed_by_month(self):
        """Validated milestones (done and approved) per month of their actual finish, last six months."""
        months, first = [], self.today.replace(day=1)
        for back in range(MONTHS - 1, -1, -1):
            y, m = divmod(first.year * 12 + first.month - 1 - back, 12)
            start = date(y, m + 1, 1)
            y2, m2 = divmod(y * 12 + m + 1, 12)
            end = date.fromordinal(date(y2, m2 + 1, 1).toordinal() - 1)
            n = sum(1 for r in self.rows if r.item_type_id == self.milestone and r.status_id == self.done
                    and r.approval_status in (None, "approved") and r.actual_end and start <= r.actual_end <= end)
            months.append({"month": start.isoformat()[:7], "count": n, "filters": {
                "level": "all", "item_type_id": str(self.milestone), "validated": "1",
                "actual_end__gte": start.isoformat(), "actual_end__lte": end.isoformat()}})
        return months

    def build(self) -> dict:
        blockers, blockers_total = self.blockers_and_decisions()
        upcoming, upcoming_filters = self.upcoming_milestones()
        capacity, usable = self.capacity()
        holds = self.hold_points()
        return {
            "board": self.board(), "hold_points": holds[:HOLD_N], "hold_points_total": len(holds),
            "watchlist": self.watchlist(), "blockers_decisions": blockers, "blockers_decisions_total": blockers_total,
            "upcoming_milestones": upcoming, "upcoming_filters": upcoming_filters,
            "capacity": capacity, "usable_pct": usable, "adoption": self.adoption(),
            "completed_by_month": self.completed_by_month(),
        }

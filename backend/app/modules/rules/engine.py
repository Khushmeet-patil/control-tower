"""Health engine: runs the published rules over work items and explains every result.

    results = evaluate(tenant_id, [item ids])   → {item id: HealthResult} for those items and everything below

How an item's health is decided (Red > Amber > Grey > Green):
1. Items that are not being delivered (Ideation, On hold, Done, Cancelled) have no health ("n/a"),
   except Done work still waiting for approval, which is checked until it is approved.
2. Every active published rule that applies to the item's type is tested. A rule of kind "health"
   gives its colour; a "data_quality" rule only adds a flag. Variants of one condition that report the
   same thing (e.g. "overdue" Red for high priority and Amber for any priority) count once, the worst one.
3. Health rolls up: an item is at least as bad as its worst child. The parent then lists that child as
   a finding, naming the item deep down that caused it.
4. No finding at all means Green. Missing information is Grey, never Green.
Each finding carries the rule, the reason, the source item, the recommended action and the escalation owner.
Nothing is stored: health is recalculated on every read, so it always matches the data.
"""
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.core.dates import today
from app.extensions import db
from app.modules.auth.models import User
from app.modules.config.versioning import published_list, published_snapshot, published_value_id
from app.modules.organisation.models import OrgUnit
from app.modules.rules.catalog import EVALUATORS
from app.modules.work.models import Assignment, WorkItem, WorkItemClosure, WorkItemResponsible
from app.modules.work.progress import progress_map
from app.modules.workflows.models import ApprovalRequest

RANK = {"red": 3, "amber": 2, "grey": 1, "green": 0}
NO_HEALTH_STATUSES = ("ideation", "on_hold", "done", "cancelled")
HEALTH_LABEL = {"red": "Red", "amber": "Amber", "grey": "Grey", "green": "Green"}


@dataclass
class Finding:
    rule_code: str
    rule_name: str
    kind: str
    outcome: str
    reason: str
    days: int
    source_id: int
    score: int
    action: str | None
    escalation_id: int | None
    via_child_id: int | None = None


@dataclass
class HealthResult:
    item_id: int
    health: str | None  # red/amber/grey/green, None = not assessed
    findings: list[Finding] = field(default_factory=list)

    @property
    def top(self):
        return next((f for f in self.findings if f.kind == "health"), None)


class _Defaults(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def published_rules(tenant_id: int) -> list[dict]:
    snapshot, _ = published_snapshot(tenant_id)
    rules = [r for r in snapshot.get("health_rules", []) if r["is_active"] and r["rule_type"] in EVALUATORS]
    return sorted(rules, key=lambda r: (r["sort_order"], r["id"]))


class Context:
    """Everything the evaluators need, loaded once per evaluation."""

    def __init__(self, tenant_id, rows):
        self.tenant_id = tenant_id
        self.today = today()
        self.rows = {r.id: r for r in rows}
        self._children = {}
        for r in rows:
            if r.parent_id in self.rows:
                self._children.setdefault(r.parent_id, []).append(r)
        ids = list(self.rows)
        self.labels = {}
        self.orders = {}
        snapshot, _ = published_snapshot(tenant_id)
        for v in snapshot.get("lookup_values", []):
            self.labels[v["id"]] = v["label"]
            self.orders[v["id"]] = v["sort_order"]
        self.closed = {published_value_id(tenant_id, "status", c) for c in ("done", "cancelled")} - {None}
        self.no_health = {published_value_id(tenant_id, "status", c) for c in NO_HEALTH_STATUSES} - {None}
        self.responsibles = {}
        for item_id, user_id in db.session.execute(select(WorkItemResponsible.work_item_id, WorkItemResponsible.user_id)
                                                   .where(WorkItemResponsible.work_item_id.in_(ids))):
            self.responsibles.setdefault(item_id, []).append(user_id)
        self.assignments = dict(db.session.execute(
            select(Assignment.work_item_id, func.count(Assignment.id))
            .where(Assignment.work_item_id.in_(ids), Assignment.is_deleted.is_(False)).group_by(Assignment.work_item_id)).all())
        self.pending = {}
        for req in db.session.scalars(select(ApprovalRequest).where(
                ApprovalRequest.work_item_id.in_(ids), ApprovalRequest.status == "pending")):
            step = req.steps[req.current_step]["name"] if req.current_step < len(req.steps) else ""
            self.pending[req.work_item_id] = {"submitted_on": req.submitted_at.date(), "step": step,
                                              "approver_id": req.current_approver_id, "request_id": req.id}
        self._progress = None
        self._loads = None
        self._names = {}
        self._helpers = {}

    def status_id(self, code):
        return published_value_id(self.tenant_id, "status", code)

    def label(self, value_id):
        return self.labels.get(value_id, "")

    def stage_order(self, value_id):
        return (self.orders.get(value_id, 0), value_id)

    def is_closed(self, row):
        return row.status_id in self.closed

    def assessed(self, row):
        # Work marked Done but still waiting for approval is not finished: keep checking it.
        return row.status_id not in self.no_health or row.approval_status == "pending"

    def age_days(self, row):
        start = row.planned_start or row.created_at.date()
        return max(0, (self.today - start).days)

    def children(self, item_id):
        return [c for c in self._children.get(item_id, []) if c.status_id != self.status_id("cancelled")]

    def progress(self, item_id):
        if self._progress is None:
            roots = [i for i, r in self.rows.items() if r.parent_id not in self.rows]
            self._progress = progress_map(self.tenant_id, roots)
        return self._progress.get(item_id, 0)

    def load(self, person_id):
        if self._loads is None:
            self._loads = {}
        if person_id not in self._loads:
            from app.modules.work.service import allocation_load

            people = ({r.accountable_id for r in self.rows.values()} | {person_id}) - set(self._loads)
            self._loads.update({p: v["pct"] for p, v in allocation_load(self.tenant_id, people).items()})
        return self._loads.get(person_id, 0)

    def helpers(self, row):
        """People who could help finish an item: its assignees and responsible owners, and the people of its unit."""
        if row.id not in self._helpers:
            people = set(self.responsibles.get(row.id, []))
            people |= set(db.session.scalars(select(Assignment.person_id).where(
                Assignment.work_item_id == row.id, Assignment.is_deleted.is_(False))))
            if row.unit_id:
                people |= set(db.session.scalars(select(User.id).where(
                    User.unit_id == row.unit_id, User.is_active.is_(True), User.is_deleted.is_(False))))
            self._helpers[row.id] = sorted(people)
        return self._helpers[row.id]

    def person_name(self, person_id):
        if person_id is None:
            return "nobody"
        if person_id not in self._names:
            self._names[person_id] = db.session.scalar(select(User.full_name).where(User.id == person_id)) or "someone"
        return self._names[person_id]

    def pending_approval(self, item_id):
        return self.pending.get(item_id)

    def assignment_count(self, item_id):
        return self.assignments.get(item_id, 0)

    # ---- escalation
    def escalation(self, row, target):
        if target == "approver" and (p := self.pending.get(row.id)) and p["approver_id"]:
            return p["approver_id"]
        if target == "accountable_manager":
            return db.session.scalar(select(User.manager_id).where(User.id == row.accountable_id)) or row.accountable_id
        if target == "parent_accountable" and row.parent_id:
            parent = self.rows.get(row.parent_id) or db.session.get(WorkItem, row.parent_id)
            return parent.accountable_id if parent else row.accountable_id
        if target == "unit_head":
            unit_id, seen = row.unit_id, set()
            while unit_id and unit_id not in seen:
                seen.add(unit_id)
                unit = db.session.get(OrgUnit, unit_id)
                if unit is None:
                    break
                if unit.head_id:
                    return unit.head_id
                unit_id = unit.parent_id
        return row.accountable_id


def _load_rows(tenant_id, root_ids):
    ids = select(WorkItemClosure.descendant_id).where(WorkItemClosure.ancestor_id.in_(list(root_ids)))
    return db.session.scalars(select(WorkItem).where(WorkItem.id.in_(ids), WorkItem.tenant_id == tenant_id,
                                                     WorkItem.is_deleted.is_(False))).all()


def _applies(rule, row):
    types = rule.get("item_type_ids") or []
    return not types or row.item_type_id in types


def _own_findings(rules, row, ctx):
    best = {}
    for rule in rules:
        if not _applies(rule, row):
            continue
        result = EVALUATORS[rule["rule_type"]](row, ctx, rule.get("params") or {})
        if result is None:
            continue
        reason, days = result
        escalation = ctx.escalation(row, rule["escalate_to"])
        responsible = ", ".join(ctx.person_name(p) for p in ctx.responsibles.get(row.id, [])) or "the responsible owner"
        action = (rule.get("recommended_action") or "").format_map(_Defaults(
            accountable=ctx.person_name(row.accountable_id), responsible=responsible,
            escalation=ctx.person_name(escalation), days=days, item=f"{row.code} {row.title}")) or None
        finding = Finding(rule["code"], rule["name"], rule["kind"], rule["outcome"], reason, days, row.id,
                          rule["score"], action, escalation)
        # Variants of one condition (e.g. "overdue" Red for high priority, Amber for any) report the
        # same reason: keep only the worst. Different checks of one type (missing target vs missing
        # priority) give different reasons and are all kept.
        key = (rule["kind"], rule["rule_type"], reason)
        current = best.get(key)
        if current is None or (RANK[finding.outcome], finding.score) > (RANK[current.outcome], current.score):
            best[key] = finding
    return list(best.values())


def _sort(findings):
    return sorted(findings, key=lambda f: (f.kind != "health", -RANK[f.outcome], -f.score, f.reason))


def evaluate(tenant_id: int, root_ids) -> dict[int, HealthResult]:
    root_ids = {int(i) for i in root_ids}
    if not root_ids:
        return {}
    rows = _load_rows(tenant_id, root_ids)
    ctx = Context(tenant_id, rows)
    rules = published_rules(tenant_id)
    results: dict[int, HealthResult] = {}

    def compute(item_id):  # iterative post-order (children first)
        stack = [(item_id, False)]
        while stack:
            node, expanded = stack.pop()
            if node in results:
                continue
            kids = ctx.children(node)
            if kids and not expanded:
                stack.append((node, True))
                stack.extend((k.id, False) for k in kids if k.id not in results)
                continue
            row = ctx.rows[node]
            if not ctx.assessed(row):
                results[node] = HealthResult(node, None)
                continue
            findings = _own_findings(rules, row, ctx)
            for kid in kids:
                child = results.get(kid.id)
                if child is None or child.health in (None, "green") or child.top is None:
                    continue
                top = child.top
                findings.append(Finding(
                    "child", "Child item", "health", child.health,
                    f"{kid.code} {kid.title} is {HEALTH_LABEL[child.health]}: {top.reason}"
                    + (f" (in {ctx.rows[top.source_id].code})" if top.source_id != kid.id else ""),
                    top.days, top.source_id, top.score, top.action, top.escalation_id, via_child_id=kid.id))
            findings = _sort(findings)
            worst = max((RANK[f.outcome] for f in findings if f.kind == "health"), default=0)
            results[node] = HealthResult(node, next(k for k, v in RANK.items() if v == worst), findings)

    for root in root_ids:
        if root in ctx.rows:
            compute(root)
    return results


def health_value_ids(tenant_id: int) -> dict[str, int | None]:
    return {code: published_value_id(tenant_id, "health", code) for code in RANK}


def capacity_buffer(tenant_id: int) -> int:
    """% of capacity kept free for unplanned work: the published "owner overloaded" rule's setting
    (default 20), so the Team view's Overloaded matches the health rule."""
    for r in published_rules(tenant_id):
        if r["rule_type"] == "owner_overloaded":
            return int((r.get("params") or {}).get("buffer_pct") or 0)
    return 20


def priority_bonus(tenant_id: int) -> dict[int, int]:
    """Priority value id → points (lowest priority 1, next 2, …), following the Priority list's order,
    which admins keep from lowest to highest."""
    values = sorted(published_list(tenant_id, "priority").values(), key=lambda v: (v["sort_order"], v["id"]))
    return {v["id"]: i + 1 for i, v in enumerate(values)}

"""The condition types a health or data-quality rule can use.

Each type is code (how to test one item); everything else about a rule is data (HealthRule).
`params` describes the settings an admin can give the rule, so the admin screen can build its form:
    days / percent / number        → whole number
    lookup:<list code>             → several lookup value ids (e.g. lookup:priority)
    choice:<options key>           → one value from CHOICES
An evaluator returns None (rule does not fire) or (reason text, days) for the item; `days` (overdue,
waiting, age…) feeds the Action Centre score.
"""
from dataclasses import dataclass, field

CHOICES = {
    "field": {
        "planned_end": "Target date", "planned_start": "Start date", "priority_id": "Priority",
        "category_id": "Category", "unit_id": "Unit", "function_id": "Function", "evidence_url": "Evidence link",
        "description": "Description",
    },
}


@dataclass
class Param:
    key: str
    label: str
    type: str
    default: object = None
    help: str | None = None


@dataclass
class RuleType:
    label: str
    description: str
    params: list[Param] = field(default_factory=list)


def _ids(params, key):
    return set(params.get(key) or [])


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------------- evaluators
def overdue(item, ctx, params):
    if ctx.is_closed(item) or not item.planned_end or item.planned_end >= ctx.today:
        return None
    days = (ctx.today - item.planned_end).days
    if days <= int(params.get("min_days") or 0):
        return None
    if (prio := _ids(params, "priority_ids")) and item.priority_id not in prio:
        return None
    return f"Past its target date ({item.planned_end:%d %b %Y}) by {_plural(days, 'day')}", days


def due_soon_not_started(item, ctx, params):
    if item.status_id != ctx.status_id("not_started") or not item.planned_end or item.planned_end < ctx.today:
        return None
    days = (item.planned_end - ctx.today).days
    if days > int(params.get("within_days") or 7):
        return None
    return f"Due in {_plural(days, 'day')} but not started", 0


def status_is(item, ctx, params):
    if item.status_id in _ids(params, "status_ids"):
        return f"Status is {ctx.label(item.status_id)}", ctx.age_days(item)
    return None


def open_action(item, ctx, params):
    """Open actions (blockers, decisions…) matching type, severity, age or lateness."""
    if ctx.is_closed(item):
        return None
    if (types := _ids(params, "action_type_ids")) and item.action_type_id not in types:
        return None
    if (sev := _ids(params, "severity_ids")) and item.severity_id not in sev:
        return None
    age = ctx.age_days(item)
    min_age = int(params.get("min_age_days") or 0)
    if min_age and age <= min_age:
        return None
    late = item.planned_end and item.planned_end < ctx.today
    if params.get("overdue_only") and not late:
        return None
    kind = ctx.label(item.action_type_id) or "Action"
    parts = [f"Open {kind.lower()}", f"raised {_plural(age, 'day')} ago"]
    if item.severity_id:
        parts.insert(1, ctx.label(item.severity_id).lower())
    if late:
        parts.append(f"due {item.planned_end:%d %b %Y}")
    return ", ".join(parts), (ctx.today - item.planned_end).days if late else age


def missing_field(item, ctx, params):
    name = params.get("field") or "planned_end"
    if name == "planned_end" and item.status_id == ctx.status_id("ongoing"):
        return None  # ongoing work has no end date by design
    if getattr(item, name, None) in (None, ""):
        return f"No {CHOICES['field'].get(name, name).lower()}", 0
    return None


def no_children(item, ctx, params):
    types = _ids(params, "child_type_ids")
    kids = [c for c in ctx.children(item.id) if not types or c.item_type_id in types]
    if kids:
        return None
    what = ", ".join(ctx.label(t).lower() for t in types) if types else "child item"
    return f"Has no {what}s" if types else "Has no child items", 0


def no_open_children(item, ctx, params):
    kids = ctx.children(item.id)
    # A finished child still waiting for approval is not finished yet.
    if not kids or any(not ctx.is_closed(c) or c.approval_status == "pending" for c in kids) \
            or ctx.progress(item.id) >= 100:
        return None
    return "Every child item is finished but the work is not complete: nothing is planned next", 0


def owner_overloaded(item, ctx, params):
    usable = ctx.usable(item.accountable_id, int(params.get("buffer_pct") or 0))
    load = ctx.load(item.accountable_id)
    if load <= usable:
        return None
    return f"{ctx.person_name(item.accountable_id)} is allocated {load}% against {usable}% usable capacity", 0


def approval_waiting(item, ctx, params):
    pending = ctx.pending_approval(item.id)
    if not pending:
        return None
    days = (ctx.today - pending["submitted_on"]).days
    if days < int(params.get("min_days") or 0):
        return None
    return f"Waiting {_plural(days, 'day')} for approval ({pending['step']})", days


def approval_rejected(item, ctx, params):
    if item.approval_status != "rejected":
        return None
    return "An approver sent it back; fix it and mark it complete again", 0


def stale(item, ctx, params):
    days = (ctx.today - item.updated_at.date()).days
    if days <= int(params.get("min_days") or 14):
        return None
    return f"Not updated for {_plural(days, 'day')}", days


def unassigned(item, ctx, params):
    if ctx.assignment_count(item.id):
        return None
    return "Nobody is assigned with an allocation", 0


def adoption_gap(item, ctx, params):
    """Reached every stage in `reached_stage_ids` but not all of `missing_stage_ids` (adoption pipeline)."""
    reached = set(item.adoption_stage_ids or [])
    need, missing = _ids(params, "reached_stage_ids"), _ids(params, "missing_stage_ids")
    if not need or not missing or not need <= reached or missing <= reached:
        return None
    done = ", ".join(ctx.label(i) for i in sorted(need, key=ctx.stage_order))
    todo = ", ".join(ctx.label(i) for i in sorted(missing - reached, key=ctx.stage_order))
    return f"{done} done; {todo} not yet", 0


def quick_win(item, ctx, params):
    """Nearly finished, and someone on the item or in its unit has spare capacity (prototype "quick win")."""
    if ctx.is_closed(item):
        return None
    pct = ctx.progress(item.id)
    if pct < int(params.get("min_progress") or 80) or pct >= 100:
        return None
    buffer = int(params.get("buffer_pct") or 0)
    spare = [(ctx.load(p), p) for p in ctx.helpers(item) if ctx.usable(p, buffer) > 0]
    spare = sorted((load, p) for load, p in spare if load < ctx.usable(p, buffer) / 2)
    if not spare:
        return None
    load, person = spare[0]
    return f"{pct}% complete and {ctx.person_name(person)} has spare capacity ({load}% allocated)", 0


RULE_TYPES = {
    "overdue": RuleType("Past its target date", "The target (planned finish) date has passed and the work is not finished.", [
        Param("min_days", "Late by more than (days)", "days", 0),
        Param("priority_ids", "Only these priorities (none = any)", "lookup:priority", [])]),
    "due_soon_not_started": RuleType("Due soon, not started", "Status is Not started and the target date is close.", [
        Param("within_days", "Due within (days)", "days", 7)]),
    "status_is": RuleType("Has a status", "The item's status is one of the chosen statuses.", [
        Param("status_ids", "Statuses", "lookup:status", [])]),
    "open_action": RuleType("Open action", "An open action (blocker, decision, approval…) of the chosen kind.", [
        Param("action_type_ids", "Action types (none = any)", "lookup:action_type", []),
        Param("severity_ids", "Severities (none = any)", "lookup:severity", []),
        Param("min_age_days", "Open for more than (days; 0 = any age)", "days", 0),
        Param("overdue_only", "Only when past its due date (1 = yes)", "number", 0)]),
    "missing_field": RuleType("Missing information", "A field that should be filled in is empty.", [
        Param("field", "Field", "choice:field", "planned_end")]),
    "no_children": RuleType("No child items", "Nothing has been planned under it (e.g. no milestones).", [
        Param("child_type_ids", "Of these types (none = any)", "lookup:item_type", [])]),
    "no_open_children": RuleType("Nothing planned next", "All child items are finished but the item is not complete."),
    "owner_overloaded": RuleType("Owner overloaded", "The accountable owner's allocation is above their usable capacity.", [
        Param("buffer_pct", "Capacity kept free for unplanned work (%)", "percent", 20)]),
    "approval_waiting": RuleType("Approval waiting", "Marked complete and still waiting for approval.", [
        Param("min_days", "Waiting at least (days)", "days", 0)]),
    "approval_rejected": RuleType("Approval refused", "An approver sent the work back."),
    "stale": RuleType("Not updated recently", "Nobody has changed the item for a while.", [
        Param("min_days", "Not updated for more than (days)", "days", 14)]),
    "unassigned": RuleType("Nobody assigned", "No person is assigned to the item with an allocation."),
    "quick_win": RuleType("Quick win", "Nearly finished and someone nearby has spare capacity to close it.", [
        Param("min_progress", "Progress at least (%)", "percent", 80),
        Param("buffer_pct", "Capacity kept free for unplanned work (%)", "percent", 20)]),
    "adoption_gap": RuleType("Adoption gap", "Reached some adoption stages but not the next ones (e.g. built, not adopted).", [
        Param("reached_stage_ids", "Has reached all of these stages", "lookup:adoption_stage", []),
        Param("missing_stage_ids", "But not (all of) these", "lookup:adoption_stage", [])]),
}

EVALUATORS = {
    "overdue": overdue, "due_soon_not_started": due_soon_not_started, "status_is": status_is,
    "open_action": open_action, "missing_field": missing_field, "no_children": no_children,
    "no_open_children": no_open_children, "owner_overloaded": owner_overloaded,
    "approval_waiting": approval_waiting, "approval_rejected": approval_rejected, "stale": stale,
    "unassigned": unassigned, "adoption_gap": adoption_gap, "quick_win": quick_win,
}


def catalog() -> list[dict]:
    return [{"code": code, "label": t.label, "description": t.description,
             "params": [{"key": p.key, "label": p.label, "type": p.type, "default": p.default, "help": p.help}
                        for p in t.params]}
            for code, t in RULE_TYPES.items()]


def default_params(rule_type: str) -> dict:
    return {p.key: p.default for p in RULE_TYPES[rule_type].params}


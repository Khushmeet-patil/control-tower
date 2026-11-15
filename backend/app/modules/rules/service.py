"""Health rules (settings draft), health for screens, and the Action Centre."""
import re

from sqlalchemy import func, select

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import ValidationFailed
from app.extensions import db
from app.modules.access.scope import managed_unit_ids
from app.modules.auth.models import User
from app.modules.config.versioning import published_list, published_value_id
from app.modules.lookups.models import LookupType, LookupValue
from app.modules.lookups.service import _keep_order_if_empty, _no_code_change
from app.modules.rules import engine
from app.modules.rules.catalog import CHOICES, RULE_TYPES, default_params
from app.modules.rules.models import ESCALATE_TO, OUTCOMES, RULE_KINDS, HealthRule
from app.modules.work.models import WorkItem
from app.modules.work.service import WorkItemService, closed_status_ids, person_ref, portfolio_params

SETTINGS = {"create": "settings.manage", "update": "settings.manage", "delete": "settings.manage"}
CODE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
TOP_N, NEEDED_N, DQ_N, UPCOMING_DAYS = 5, 25, 15, 14


# ---------------------------------------------------------------------- rules (settings)
class HealthRuleService(CommandService):
    model = HealthRule
    entity_type = "health_rule"
    permissions = SETTINGS

    def _lookup_ids(self, list_code, ids, field):
        ids = sorted({int(i) for i in ids or []})
        found = set(db.session.scalars(
            select(LookupValue.id).join(LookupType, LookupType.id == LookupValue.lookup_type_id)
            .where(LookupType.tenant_id == self.tenant_id, LookupType.code == list_code, LookupValue.id.in_(ids))))
        if found != set(ids):
            raise ValidationFailed("Choose from the listed options", {"field": field})
        return ids

    def _clean_params(self, rule_type, params):
        spec = RULE_TYPES[rule_type]
        params = dict(params or {})
        unknown = set(params) - {p.key for p in spec.params}
        if unknown:
            raise ValidationFailed("Unknown setting for this kind of rule", {"field": "params", "keys": sorted(unknown)})
        clean = default_params(rule_type)
        for p in spec.params:
            if p.key not in params:
                continue
            value = params[p.key]
            if p.type in ("days", "percent", "number"):
                try:
                    value = int(value or 0)
                except (TypeError, ValueError) as exc:
                    raise ValidationFailed(f"{p.label}: enter a whole number", {"field": f"params.{p.key}"}) from exc
                if value < 0 or (p.type == "percent" and value > 100):
                    raise ValidationFailed(f"{p.label}: out of range", {"field": f"params.{p.key}"})
            elif p.type.startswith("lookup:"):
                value = self._lookup_ids(p.type.split(":", 1)[1], value, f"params.{p.key}")
            elif p.type.startswith("choice:"):
                if value not in CHOICES[p.type.split(":", 1)[1]]:
                    raise ValidationFailed(f"{p.label}: choose one of the options", {"field": f"params.{p.key}"})
            clean[p.key] = value
        return clean

    def _check(self, data, obj=None):
        rule_type = data.get("rule_type", getattr(obj, "rule_type", None))
        if rule_type not in RULE_TYPES:
            raise ValidationFailed("Choose a condition", {"field": "rule_type"})
        if "params" in data or obj is None or "rule_type" in data:
            data["params"] = self._clean_params(rule_type, data.get("params", getattr(obj, "params", None)))
        for field, allowed in (("kind", RULE_KINDS), ("outcome", OUTCOMES), ("escalate_to", ESCALATE_TO)):
            if field in data and data[field] not in allowed:
                raise ValidationFailed("Choose one of the options", {"field": field})
        if "item_type_ids" in data:
            data["item_type_ids"] = self._lookup_ids("item_type", data["item_type_ids"], "item_type_ids") or None
        if "score" in data and not 0 <= int(data["score"]) <= 100:
            raise ValidationFailed("Score must be between 0 and 100", {"field": "score"})

    def validate_create(self, data):
        if not CODE.match(data.get("code") or ""):
            raise ValidationFailed("Use lowercase letters, numbers and _ (start with a letter)", {"field": "code"})
        if db.session.scalar(select(HealthRule.id).where(HealthRule.tenant_id == self.tenant_id,
                                                         HealthRule.code == data["code"])):
            raise ValidationFailed("This code is already used", {"field": "code"})
        if data.get("sort_order") is None:
            last = db.session.scalar(select(func.max(HealthRule.sort_order)).where(HealthRule.tenant_id == self.tenant_id))
            data["sort_order"] = (last or 0) + 10
        self._check(data)

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "code")
        _keep_order_if_empty(changes)
        self._check(changes, obj)

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Rules are never deleted; retire them instead")

    def list_all(self):
        rules = db.session.scalars(self.base_query().order_by(HealthRule.kind, HealthRule.sort_order, HealthRule.id)).all()
        return [serialize_rule(r) for r in rules]


def serialize_rule(r):
    return {
        "id": r.id, "code": r.code, "name": r.name, "kind": r.kind, "rule_type": r.rule_type,
        "rule_type_label": RULE_TYPES[r.rule_type].label if r.rule_type in RULE_TYPES else r.rule_type,
        "params": r.params or {}, "outcome": r.outcome, "item_type_ids": r.item_type_ids or [], "score": r.score,
        "recommended_action": r.recommended_action, "escalate_to": r.escalate_to, "description": r.description,
        "sort_order": r.sort_order, "is_active": r.is_active, "version": r.version,
    }


# ---------------------------------------------------------------------- showing health
class HealthView:
    """Turns engine results into JSON for one viewer: items they cannot open are not named."""

    def __init__(self, actor, tenant_id):
        self.actor = actor
        self.tenant_id = tenant_id
        self.items = WorkItemService(actor, tenant_id=tenant_id)
        self.health_ids = engine.health_value_ids(tenant_id)
        self._visible = {}
        self._people = {}

    def visible(self, ids):
        ids = set(ids) - set(self._visible)
        if ids:
            seen = set(db.session.scalars(self.items.base_query().with_only_columns(WorkItem.id).where(WorkItem.id.in_(ids))))
            self._visible.update({i: i in seen for i in ids})
        return self._visible

    def person(self, person_id):
        if person_id and person_id not in self._people:
            self._people[person_id] = person_ref(db.session.get(User, person_id))
        return self._people.get(person_id)

    def ref(self, item_id):
        if not self.visible([item_id]).get(item_id):
            return {"id": None, "code": "…", "title": "an item you cannot open"}
        w = db.session.get(WorkItem, item_id)
        return {"id": w.id, "code": w.code, "title": w.title}

    def finding(self, f):
        reason = f.reason
        if f.via_child_id and not self.visible([f.via_child_id, f.source_id]).get(f.via_child_id):
            reason = f"A child item you cannot open is {engine.HEALTH_LABEL[f.outcome]}"
        return {
            "rule_code": f.rule_code, "rule": f.rule_name, "kind": f.kind, "outcome": f.outcome,
            "outcome_id": self.health_ids.get(f.outcome), "reason": reason, "days": f.days,
            "source": self.ref(f.source_id), "via_child": self.ref(f.via_child_id) if f.via_child_id else None,
            "recommended_action": f.action, "escalate_to": self.person(f.escalation_id),
        }

    def summary(self, result):
        if result is None or result.health is None:
            return {"code": None, "value_id": None, "reason": "Not assessed (not in delivery)", "flags": 0}
        top = result.top
        return {"code": result.health, "value_id": self.health_ids.get(result.health),
                "reason": self.finding(top)["reason"] if top else "No issues found",
                "flags": sum(1 for f in result.findings if f.kind == "data_quality")}

    def full(self, result):
        out = self.summary(result)
        out["findings"] = [self.finding(f) for f in (result.findings if result else [])]
        return out


def annotate_items(actor, tenant_id, items: list[dict]) -> None:
    """Add a "health" summary to serialized work items (one engine run for the whole page)."""
    if not items:
        return
    results = engine.evaluate(tenant_id, [i["id"] for i in items])
    view = HealthView(actor, tenant_id)
    for i in items:
        i["health"] = view.summary(results.get(i["id"]))


def health_detail(actor, tenant_id, item_id) -> dict:
    return HealthView(actor, tenant_id).full(engine.evaluate(tenant_id, [item_id]).get(item_id))


def filter_by_health(tenant_id, item_ids, wanted: set[str]) -> list[int]:
    results = engine.evaluate(tenant_id, item_ids)
    return [i for i in item_ids if (results.get(i) and results[i].health) in wanted
            or ("na" in wanted and (results.get(i) is None or results[i].health is None))]


# ---------------------------------------------------------------------- Action Centre
def _score(f, row, bonus):
    factors = [{"label": f"{f.rule_name} ({engine.HEALTH_LABEL.get(f.outcome, f.outcome)})", "points": f.score}]
    if row.priority_id in bonus:
        factors.append({"label": "Priority", "points": bonus[row.priority_id]})
    if f.days:
        factors.append({"label": f"{f.days} day(s) late, waiting or open", "points": round(min(f.days, 20) * 0.5, 1)})
    return round(sum(x["points"] for x in factors), 1), factors


def action_centre(actor) -> dict:
    """Everything on the Action Centre for one person, limited to the work they can see.
    Every count comes with the Portfolio filter that lists the same items."""
    tid = actor.tenant_id
    items_svc = WorkItemService(actor)
    rows = db.session.scalars(items_svc.base_query()).all()
    by_id = {r.id: r for r in rows}
    roots = [r.id for r in rows if r.parent_id not in by_id]
    results = engine.evaluate(tid, roots)
    view = HealthView(actor, tid)
    view.visible(by_id)
    closed = set(closed_status_ids(tid))
    open_rows = [r for r in rows if r.status_id not in closed]
    bonus = engine.priority_bonus(tid)
    health_of = lambda r: results.get(r.id).health if results.get(r.id) else None  # noqa: E731

    # ---- KPIs
    blocker = published_value_id(tid, "action_type", "blocker")
    decisions = [i for i in (published_value_id(tid, "action_type", c) for c in ("decision", "approval")) if i]
    from app.modules.workflows.service import ApprovalService

    counts = ApprovalService(actor).counts()
    dq = [(r, f) for r in rows for f in (results.get(r.id).findings if results.get(r.id) else [])
          if f.kind == "data_quality" and f.source_id == r.id]
    # The prototype's KPI strip. Each tile is counted with the same select as the list it opens.
    count = lambda filters: items_svc.count(portfolio_params(filters))  # noqa: E731
    kpi = lambda key, label, filters, tone=None, value=None: {  # noqa: E731
        "key": key, "label": label, "value": count(filters) if value is None else value, "filters": filters, "tone": tone}
    milestone = published_value_id(tid, "item_type", "milestone")
    tops = [r for r in rows if r.parent_id is None]
    in_delivery = sum(1 for r in tops if health_of(r))
    kpis = [
        kpi("initiatives", f"Top-level items ({in_delivery} in delivery)", {"level": "top"}),
        kpi("red", "Red (top level)", {"level": "top", "health": "red"}, "red"),
        kpi("overdue_milestones", "Overdue milestones", {"level": "all", "item_type_id": str(milestone or ""), "overdue": "1"}, "red"),
        kpi("blockers", "Open blockers", {"level": "all", "open": "1", "action_type_id": str(blocker or "")}),
        kpi("decisions", "Pending decisions",
            {"level": "all", "open": "1", "action_type_id__in": ",".join(map(str, decisions))}),
        kpi("approvals", "Awaiting my validation", None, "amber", counts["waiting_for_me"]),
        kpi("dq", "Data-quality flags", None, None, len(dq)),
    ]

    # ---- where I am needed: direct findings on items I answer for, plus approvals waiting for me
    managed = managed_unit_ids(actor)
    involved = {r.id for r in rows if r.accountable_id == actor.id}
    from app.modules.work.models import WorkItemResponsible

    involved |= set(db.session.scalars(select(WorkItemResponsible.work_item_id).where(WorkItemResponsible.user_id == actor.id)))
    entries = []
    waiting_rules = {r["code"] for r in engine.published_rules(tid) if r["rule_type"] == "approval_waiting"}
    for r in rows:
        res = results.get(r.id)
        if res is None:
            continue
        for f in res.findings:
            if f.kind not in ("health", "signal") or f.source_id != r.id:
                continue
            mine = (f.escalation_id == actor.id or r.id in involved
                    or (managed is None and actor.is_admin) or (managed and r.unit_id in managed))
            if not mine:
                continue
            score, factors = _score(f, r, bonus)
            entries.append({"score": score, "factors": factors, "item": view.ref(r.id), "what": f.rule_name,
                            "rule_code": f.rule_code,
                            "outcome": f.outcome, "outcome_id": view.health_ids.get(f.outcome), "why": f.reason,
                            "next": f.action, "owner": view.person(f.escalation_id),
                            "due": r.planned_end.isoformat() if r.planned_end else None, "kind": "finding"})
    inbox = ApprovalService(actor).inbox({"box": "mine", "per_page": 50})["items"]
    for req in inbox:
        r = by_id.get(req["work_item"]["id"])
        factors = [{"label": "Waiting for your approval", "points": 88}]
        if r is not None and r.priority_id in bonus:
            factors.append({"label": "Priority", "points": bonus[r.priority_id]})
        if req["waiting_days"]:
            factors.append({"label": f"Waiting {req['waiting_days']} day(s)", "points": round(min(req["waiting_days"], 20) * 0.5, 1)})
        # The approval itself replaces an "approval waiting" finding on the same item.
        entries = [e for e in entries if not (e["item"]["id"] == req["work_item"]["id"]
                                              and e.get("rule_code") in waiting_rules)]
        entries.append({"score": round(sum(x["points"] for x in factors), 1), "factors": factors,
                        "item": {"id": req["work_item"]["id"], "code": req["work_item"]["code"], "title": req["work_item"]["title"]},
                        "what": "Approve completed work", "outcome": "amber", "outcome_id": view.health_ids.get("amber"),
                        "why": f"{req['submitted_by']['full_name'] if req['submitted_by'] else 'Someone'} marked it complete; "
                               f"step {req['current_step'] + 1} of {req['step_count']} ({req['current_step_name']}) waits for you",
                        "next": "Review the evidence, then approve or send it back", "owner": person_ref(actor),
                        "due": None, "kind": "approval", "approval_id": req["id"]})
    entries.sort(key=lambda e: (-e["score"], e["item"]["code"]))

    # ---- priority × health for top-level work, health/status/category spread
    top_rows = [r for r in rows if r.parent_id not in by_id and health_of(r)]
    priorities = sorted(published_list(tid, "priority").values(), key=lambda v: (-v["sort_order"], v["id"]))
    matrix = [{"priority_id": p["id"], "label": p["label"],
               "cells": {h: sum(1 for r in top_rows if r.priority_id == p["id"] and health_of(r) == h)
                         for h in ("red", "amber", "grey", "green")}} for p in priorities if p["is_active"]]

    def spread(key):
        out = {}
        for r in [r for r in rows if r.parent_id not in by_id]:
            value = health_of(r) if key == "health" else getattr(r, key)
            out[value] = out.get(value, 0) + 1
        return [{"value": k, "count": v} for k, v in sorted(out.items(), key=lambda kv: -kv[1])]

    # ---- the rest of the prototype's weekly review (board, hold points, watchlist, capacity…)
    from app.modules.dashboards.review import Review

    review = Review(actor, rows, results, view, closed, bonus, inbox).build()

    # ---- upcoming deadlines and data quality
    horizon = today().toordinal() + UPCOMING_DAYS
    upcoming = sorted((r for r in open_rows if r.planned_end and today() <= r.planned_end
                       and r.planned_end.toordinal() <= horizon), key=lambda r: r.planned_end)[:10]
    return {
        "kpis": kpis,
        "top": entries[:TOP_N],
        "needed": entries[:NEEDED_N],
        "needed_total": len(entries),
        "matrix": matrix,
        "health_ids": view.health_ids,
        "spread": {"priority_id": spread("priority_id"), "status_id": spread("status_id"),
                   "category_id": spread("category_id"), "health": spread("health")},
        "upcoming": [{**view.ref(r.id), "planned_end": r.planned_end.isoformat(), "item_type_id": r.item_type_id,
                      "status_id": r.status_id, "accountable": view.person(r.accountable_id)} for r in upcoming],
        "data_quality": [{"item": view.ref(r.id), "rule": f.rule_name, "reason": f.reason,
                          "owner": view.person(f.escalation_id)} for r, f in dq[:DQ_N]],
        "data_quality_total": len(dq),
        **review,
    }


"""Seed data.

    flask --app run seed          tenant, unit types, built-in roles, top unit, first admin,
                                  default lookup lists and terms (published as settings version 1)
    flask --app run seed --demo   … plus a demo organisation, functions and people to try things out

Safe to run more than once: existing records (matched by code or email) are left alone.
"""
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.modules.access.catalog import PERMISSION_CODES
from app.modules.access.models import Role
from app.modules.access.service import RoleService
from app.modules.auth.models import User
from app.modules.config.models import Term
from app.modules.config.service import SettingsService, TermService
from app.modules.config.versioning import current_version
from app.modules.lookups.models import LookupType, LookupValue
from app.modules.lookups.service import LookupTypeService, LookupValueService
from app.modules.organisation.models import Function, OrgUnit, OrgUnitType, Tenant
from app.modules.organisation.service import FunctionService, UnitService
from app.modules.people.service import PersonService

UNIT_TYPES = [  # code, name, order, colour
    ("company", "Company", 10, "#2F5D8A"),
    ("division", "Division", 20, "#5B7DB1"),
    ("department", "Department", 30, "#3E8E7E"),
    ("team", "Team", 40, "#8A6D3B"),
]

VIEW = ["org.view", "functions.view", "people.view"]
WORK_VIEW = ["work.view"]
WORK_MANAGE = ["work.view", "work.create", "work.manage", "views.share", "dashboards.share"]
ROLES = [  # code, name, scope, permissions, is_default, description
    ("administrator", "Administrator", "all", sorted(PERMISSION_CODES), False,
     "Full access to everything, including settings."),
    ("executive", "Executive", "all", VIEW + ["audit.view"] + WORK_MANAGE, False,
     "Sees the whole organisation; does not change settings."),
    ("manager", "Manager", "unit", VIEW + ["org.manage", "people.manage"] + WORK_MANAGE, False,
     "Sees and manages their own unit and everything below it."),
    ("functional_lead", "Functional lead", "own", VIEW + WORK_VIEW, False,
     "Leads a function; sees the people in the functions they lead."),
    ("contributor", "Contributor", "own", VIEW + WORK_VIEW, True,
     "Sees their own work. Given to new people by default."),
    ("viewer", "Viewer", "unit", VIEW + WORK_VIEW, False, "Read-only view of their own unit."),
]
# Permission groups added after a database was first seeded. A built-in role that holds none of a
# group's codes yet receives its default codes from ROLES; once it holds any, admins' edits are kept.
LATER_PERMISSION_GROUPS = ["work.", "views.", "dashboards."]

# Default lookup lists: code, name, [(code, label, colour, is_default, is_system)]
# Colours stay calm: navy accent, muted greys, and red/amber/green only where they mean status.
GREY, NAVY, TEAL, BROWN, SLATE = "#9CA3AF", "#2F5D8A", "#3E8E7E", "#8A6D3B", "#64748B"
RED, AMBER, GREEN = "#DC2626", "#D97706", "#16A34A"
LOOKUPS = [
    ("status", "Status", [
        ("not_started", "Not started", GREY, True, False), ("in_progress", "In progress", NAVY, False, False),
        ("on_hold", "On hold", AMBER, False, False), ("blocked", "Blocked", RED, False, False),
        ("done", "Done", GREEN, False, False), ("cancelled", "Cancelled", SLATE, False, False),
        ("ideation", "Ideation", GREY, False, False), ("ongoing", "Ongoing", TEAL, False, False),
        ("under_validation", "Under validation", BROWN, False, False)]),
    ("priority", "Priority", [
        ("low", "Low", GREY, False, False), ("medium", "Medium", NAVY, True, False),
        ("high", "High", AMBER, False, False), ("critical", "Critical", RED, False, False)]),
    ("item_type", "Item type", [
        ("programme", "Programme", NAVY, False, False), ("project", "Project", TEAL, False, False),
        ("milestone", "Milestone", BROWN, False, False), ("task", "Task", SLATE, True, False),
        ("action", "Action", AMBER, False, False)]),
    ("category", "Category", [
        ("commercial", "Commercial", NAVY, False, False), ("business_challenge", "Business challenge", RED, False, False),
        ("governance", "Governance", SLATE, False, False), ("functional", "Functional", TEAL, False, False),
        ("project_tracking", "Project tracking", BROWN, False, False), ("misc", "Miscellaneous", GREY, False, False)]),
    ("action_type", "Action type", [  # the health and Action Centre rules rely on these codes
        ("decision", "Decision", NAVY, False, True), ("approval", "Approval", TEAL, False, True),
        ("blocker", "Blocker", RED, False, True), ("commitment", "Commitment", BROWN, False, True),
        ("action", "Action", SLATE, True, True)]),
    ("severity", "Severity", [
        ("minor", "Minor", AMBER, True, True), ("critical", "Critical", RED, False, True)]),
    ("functional_role", "Functional role", [
        ("lead", "Lead", NAVY, False, False), ("contributor", "Contributor", TEAL, True, False),
        ("reviewer", "Reviewer", BROWN, False, False), ("tester", "Tester", SLATE, False, False),
        ("adviser", "Adviser", GREY, False, False)]),
    ("adoption_stage", "Adoption stage", [  # the prototype's adoption pipeline, in order
        ("dev", "Development done", NAVY, False, False), ("test", "Testing done", TEAL, False, False),
        ("accepted", "Business acceptance", BROWN, False, False), ("trained", "Users trained", SLATE, False, False),
        ("rollout", "Rolled out", AMBER, False, False), ("adopted", "Adoption achieved", GREEN, False, False)]),
    ("health", "Health", [  # the health engine relies on these four codes
        ("green", "Green", GREEN, False, True), ("amber", "Amber", AMBER, False, True),
        ("red", "Red", RED, False, True), ("grey", "Grey (no data)", GREY, True, True)]),
]
# The reference prototype's validation gate as the default approval chain for milestones:
# the functional lead checks the work, then the accountable owner takes responsibility for it.
DEFAULT_CHAIN = {
    "code": "milestone_validation", "name": "Milestone validation",
    "description": "A milestone counts towards progress only after its functional lead and its accountable owner approve it.",
    "item_types": ["milestone"],
    "steps": [
        {"name": "Functional lead review", "approver_kind": "functional_lead", "when_missing": "skip",
         "require_evidence": True, "checklist": [
             "The deliverable meets our functional and technical standards",
             "Tests or evidence show it works, not just the developer's claim"]},
        {"name": "Accountable owner validation", "approver_kind": "accountable", "when_missing": "block",
         "checklist": [
             "I reviewed the deliverable against the milestone requirement",
             "I checked tests or evidence that it works, not just the developer's claim",
             "I verified data, logic or outputs myself or by spot check",
             "I am ready to stand accountable for this being complete"]},
    ],
}

# Default health and data-quality rules: the reference prototype's health(), dq() and top5() as data.
# Lookup references are given as (list code, [value codes]) and resolved when seeding.
# code, name, kind, rule type, params, outcome, item types, score, recommended action, escalate to
LARGE = ["programme", "project"]
DEFAULT_RULES = [
    ("overdue_high", "Overdue (high priority)", "health", "overdue",
     {"priority_ids": ("priority", ["critical", "high"])}, "red", [], 80,
     "Agree a recovery date with {responsible}", "accountable"),
    ("overdue", "Overdue", "health", "overdue", {}, "amber", [], 70,
     "Agree a new date with {responsible}", "accountable"),
    ("blocker_critical", "Critical blocker", "health", "open_action",
     {"action_type_ids": ("action_type", ["blocker"]), "severity_ids": ("severity", ["critical"])}, "red", ["action"], 90,
     "Escalate to {escalation} today", "parent_accountable"),
    ("blocker_ageing", "Blocker open too long", "health", "open_action",
     {"action_type_ids": ("action_type", ["blocker"]), "min_age_days": 7}, "red", ["action"], 90,
     "Escalate to {escalation}", "parent_accountable"),
    ("blocker", "Open blocker", "health", "open_action",
     {"action_type_ids": ("action_type", ["blocker"])}, "amber", ["action"], 75,
     "Agree who removes it and by when", "accountable"),
    ("decision_overdue", "Overdue decision or approval", "health", "open_action",
     {"action_type_ids": ("action_type", ["decision", "approval"]), "overdue_only": 1}, "amber", ["action"], 85,
     "Decide or delegate today; it may be blocking work", "accountable"),
    ("status_blocked", "Status is Blocked", "health", "status_is",
     {"status_ids": ("status", ["blocked"])}, "red", [], 85, "Find out what is blocking it and who can unblock it", "accountable"),
    ("due_soon", "Due soon, not started", "health", "due_soon_not_started", {"within_days": 7}, "amber", [], 70,
     "Confirm delivery with {responsible}", "accountable"),
    ("approval_waiting", "Approval waiting", "health", "approval_waiting", {"min_days": 3}, "amber", [], 88,
     "Review the evidence, then approve or send it back", "approver"),
    ("approval_rejected", "Sent back by an approver", "health", "approval_rejected", {}, "amber", [], 65,
     "Fix what the approver asked for and mark it complete again", "accountable"),
    ("owner_overloaded", "Owner overloaded", "health", "owner_overloaded", {"buffer_pct": 20}, "amber", LARGE, 60,
     "Rebalance {accountable}'s work or defer a lower-priority item", "accountable_manager"),
    ("no_target", "No target date", "health", "missing_field", {"field": "planned_end"}, "grey",
     LARGE + ["milestone"], 35, "Set a target date", "accountable"),
    ("no_priority", "No priority", "health", "missing_field", {"field": "priority_id"}, "grey", LARGE, 35,
     "Set a priority", "accountable"),
    ("no_milestones", "No milestones", "health", "no_children", {"child_type_ids": ("item_type", ["milestone"])},
     "grey", LARGE, 35, "Plan the milestones and give each a responsible owner", "accountable"),
    ("nothing_next", "Nothing planned next", "health", "no_open_children", {}, "grey", LARGE, 40,
     "Define the next milestone or mark the work complete", "accountable"),
    ("stale", "Not updated for two weeks", "data_quality", "stale", {"min_days": 14}, "grey", LARGE, 30,
     "Ask {responsible} for an update", "accountable"),
    ("unassigned", "Nobody assigned", "data_quality", "unassigned", {}, "grey", LARGE, 30,
     "Assign people with an allocation", "accountable"),
    # Signals: rank in the Action Centre and its watchlist without changing the colour.
    ("ready_for_rollout", "Ready for rollout", "signal", "adoption_gap",
     {"reached_stage_ids": ("adoption_stage", ["dev", "test", "accepted"]),
      "missing_stage_ids": ("adoption_stage", ["rollout"])}, "amber", LARGE, 50,
     "Plan the rollout with {responsible}", "accountable"),
    ("quick_win", "Quick win", "signal", "quick_win", {"min_progress": 80, "buffer_pct": 20}, "amber", LARGE, 40,
     "Close the remaining work now with the person who has spare capacity", "accountable"),
    ("built_not_adopted", "Built, not adopted", "signal", "adoption_gap",
     {"reached_stage_ids": ("adoption_stage", ["dev"]), "missing_stage_ids": ("adoption_stage", ["adopted"])},
     "amber", LARGE, 45, "Technical completion is not business value: capture adoption evidence and drive usage",
     "accountable"),
]
# name, filters (lookups as (list, [codes])), layout
DEFAULT_VIEWS = [
    ("Actions & decisions", {"level": "all", "open": "1", "item_type_id": ("item_type", ["action"])}, "list"),
    ("Open blockers", {"level": "all", "open": "1", "action_type_id": ("action_type", ["blocker"])}, "list"),
    ("Pending decisions", {"level": "all", "open": "1", "action_type_id__in": ("action_type", ["decision", "approval"])}, "list"),
    ("Red and amber work", {"level": "all", "health": "red,amber"}, "list"),
    ("Milestones board", {"level": "all", "item_type_id": ("item_type", ["milestone"])}, "board"),
]

# key, singular, plural, description
TERMS = [
    ("work_item", "Work item", "Work items", "Anything tracked: programmes, projects, milestones, tasks."),
    ("unit", "Unit", "Units", "A part of the administrative hierarchy (division, department, team…)."),
    ("function", "Function", "Functions", "A discipline in the functional hierarchy (QA, Development…)."),
    ("person", "Person", "People", "Someone who uses the platform."),
]


def _system(tenant):
    return {"tenant_id": tenant.id, "source": "system"}


def seed_base() -> tuple[Tenant, User]:
    tenant = db.session.scalar(select(Tenant).where(Tenant.code == "default"))
    if tenant is None:
        tenant = Tenant(code="default", name="My Organisation")
        db.session.add(tenant)
        db.session.commit()

    for code, name, order, color in UNIT_TYPES:
        if not db.session.scalar(select(OrgUnitType.id).where(OrgUnitType.tenant_id == tenant.id,
                                                              OrgUnitType.code == code)):
            db.session.add(OrgUnitType(tenant_id=tenant.id, code=code, name=name, sort_order=order, color=color))
    db.session.commit()

    roles = RoleService(None, **_system(tenant))
    for code, name, scope, perms, is_default, desc in ROLES:
        if not db.session.scalar(select(Role.id).where(Role.tenant_id == tenant.id, Role.code == code)):
            role = roles.create({"code": code, "name": name, "scope": scope, "permission_codes": perms,
                                 "is_default": is_default, "description": desc}, reason="Built-in role")
            role.is_system = True
            db.session.commit()

    root = db.session.scalar(select(OrgUnit).where(OrgUnit.tenant_id == tenant.id, OrgUnit.parent_id.is_(None),
                                                   OrgUnit.is_deleted.is_(False)))
    if root is None:
        company = db.session.scalar(select(OrgUnitType.id).where(OrgUnitType.tenant_id == tenant.id,
                                                                 OrgUnitType.code == "company"))
        root = UnitService(None, **_system(tenant)).create(
            {"name": tenant.name, "code": "ORG", "unit_type_id": company}, reason="Initial setup")

    admin_role = db.session.scalar(select(Role.id).where(Role.tenant_id == tenant.id, Role.code == "administrator"))
    email = current_app.config["SEED_ADMIN_EMAIL"].lower()
    people = PersonService(None, **_system(tenant))
    admin = db.session.scalar(select(User).where(User.email == email))
    if admin is None:
        admin = people.create(
            {"email": email, "full_name": "Platform Administrator", "password": current_app.config["SEED_ADMIN_PASSWORD"],
             "is_admin": True, "unit_id": root.id, "role_ids": [admin_role]},
            reason="Initial platform setup")
    else:
        changes = {}
        if admin.unit_id is None:
            changes["unit_id"] = root.id
        if admin_role not in people.read_value(admin, "role_ids"):
            changes["role_ids"] = sorted(set(people.read_value(admin, "role_ids")) | {admin_role})
        if changes:
            people.update(admin.id, changes, reason="Phase 1 setup")

    _grant_later_permissions(roles, tenant)

    # Built-in administrator role always holds every permission, including ones added later.
    admin_role_obj = db.session.get(Role, admin_role)
    if set(admin_role_obj.permission_codes) != PERMISSION_CODES:
        roles.update(admin_role, {"permission_codes": sorted(PERMISSION_CODES)}, reason="New permissions added")

    seed_settings(tenant)
    _seed_shared_views(tenant, admin)
    _seed_shared_dashboard(tenant, admin)
    return tenant, admin


def _grant_later_permissions(roles: RoleService, tenant: Tenant) -> None:
    defaults = {code: perms for code, _, _, perms, _, _ in ROLES}
    for role in db.session.scalars(select(Role).where(Role.tenant_id == tenant.id, Role.is_system.is_(True),
                                                      Role.is_deleted.is_(False))):
        held = set(role.permission_codes)
        add = set()
        for prefix in LATER_PERMISSION_GROUPS:
            if not any(c.startswith(prefix) for c in held):
                add |= {c for c in defaults.get(role.code, []) if c.startswith(prefix)}
        if add:
            roles.update(role.id, {"permission_codes": sorted(held | add)}, reason="New permissions added")


def _seed_default_chain(tenant: Tenant) -> bool:
    from app.modules.workflows.models import ApprovalChain
    from app.modules.workflows.service import ChainService, StepService

    if db.session.scalar(select(ApprovalChain.id).where(ApprovalChain.tenant_id == tenant.id,
                                                        ApprovalChain.code == DEFAULT_CHAIN["code"])):
        return False
    item_type = db.session.scalar(select(LookupType).where(LookupType.tenant_id == tenant.id, LookupType.code == "item_type"))
    type_ids = list(db.session.scalars(select(LookupValue.id).where(
        LookupValue.lookup_type_id == item_type.id, LookupValue.code.in_(DEFAULT_CHAIN["item_types"]))))
    chain = ChainService(None, **_system(tenant)).create(
        {"code": DEFAULT_CHAIN["code"], "name": DEFAULT_CHAIN["name"], "description": DEFAULT_CHAIN["description"],
         "item_type_ids": type_ids}, reason="Built-in approval chain")
    steps = StepService(None, **_system(tenant))
    for order, step in enumerate(DEFAULT_CHAIN["steps"], start=1):
        steps.create({"chain_id": chain.id, "sort_order": order * 10, **step}, reason="Built-in approval chain")
    return True


def _draft_value_ids(tenant, list_code, codes):
    lookup = db.session.scalar(select(LookupType).where(LookupType.tenant_id == tenant.id, LookupType.code == list_code))
    if lookup is None:
        return []
    found = dict(db.session.execute(select(LookupValue.code, LookupValue.id).where(
        LookupValue.lookup_type_id == lookup.id, LookupValue.code.in_(codes))).all())
    return [found[c] for c in codes if c in found]


def _resolve(value, tenant, joined=False):
    if isinstance(value, tuple):
        ids = _draft_value_ids(tenant, *value)
        return ",".join(map(str, ids)) if joined else ids
    return value


def _seed_default_rules(tenant: Tenant) -> bool:
    from app.modules.rules.models import HealthRule
    from app.modules.rules.service import HealthRuleService

    # Rules are never deleted (only retired), so a missing code is a built-in rule added in a later
    # release: add it. Existing rules are admins' to change and are left alone.
    existing = set(db.session.scalars(select(HealthRule.code).where(HealthRule.tenant_id == tenant.id)))
    rules = HealthRuleService(None, **_system(tenant))
    added = False
    for order, (code, name, kind, rule_type, params, outcome, types, score, action, escalate) in enumerate(DEFAULT_RULES, 1):
        if code in existing:
            continue
        added = True
        rules.create({"code": code, "name": name, "kind": kind, "rule_type": rule_type,
                      "params": {k: _resolve(v, tenant) for k, v in params.items()}, "outcome": outcome,
                      "item_type_ids": _draft_value_ids(tenant, "item_type", types), "score": score,
                      "recommended_action": action, "escalate_to": escalate, "sort_order": order * 10},
                     reason="Built-in rule (from the reference prototype)")
    return added


def _seed_shared_views(tenant: Tenant, owner: User) -> None:
    from app.modules.views.models import SavedView
    from app.modules.views.service import SavedViewService

    if db.session.scalar(select(SavedView.id).where(SavedView.tenant_id == tenant.id, SavedView.is_shared.is_(True))):
        return
    views = SavedViewService(None, **_system(tenant))
    for name, filters, layout in DEFAULT_VIEWS:
        views.create({"name": name, "page": "work", "layout": layout, "is_shared": True, "owner_id": owner.id,
                      "filters": {k: _resolve(v, tenant, joined=True) for k, v in filters.items()}},
                     reason="Built-in shared view")


# A shared starting dashboard (the prototype's Action Centre charts). Widgets name a shared view by
# its name ("view") or give Portfolio filters (lookups as (list, [codes])).
DEFAULT_DASHBOARD = ("Portfolio overview", "Health, status, progress and deadlines of the work you can see.", [
    {"type": "kpi", "title": "Open items", "filters": {"level": "all", "open": "1"}},
    {"type": "kpi", "title": "Red", "filters": {"level": "all", "health": "red"}},
    {"type": "kpi", "title": "Overdue", "filters": {"level": "all", "overdue": "1"}},
    {"type": "kpi", "title": "Pending decisions", "view": "Pending decisions"},
    {"type": "chart", "title": "Health of top-level work", "filters": {"level": "top"}, "group_by": "health",
     "chart": "doughnut"},
    {"type": "chart", "title": "Top-level work by status", "filters": {"level": "top"}, "group_by": "status_id"},
    {"type": "progress", "title": "Progress of top-level work", "filters": {"level": "top"}, "limit": 10},
    {"type": "timeline", "title": "Open milestones", "width": 2, "limit": 20,
     "filters": {"level": "all", "open": "1", "item_type_id": ("item_type", ["milestone"])}},
    {"type": "table", "title": "Red and amber work", "view": "Red and amber work", "width": 2, "limit": 8},
])


def _seed_shared_dashboard(tenant: Tenant, owner: User) -> None:
    from app.modules.dashboards.models import Dashboard
    from app.modules.dashboards.service import DashboardService
    from app.modules.views.models import SavedView

    if db.session.scalar(select(Dashboard.id).where(Dashboard.tenant_id == tenant.id)):
        return
    views = {v.name: v.id for v in db.session.scalars(select(SavedView).where(
        SavedView.tenant_id == tenant.id, SavedView.is_shared.is_(True), SavedView.is_deleted.is_(False)))}
    name, description, widgets = DEFAULT_DASHBOARD
    out = []
    for n, w in enumerate(widgets, 1):
        w = dict(w)
        view = w.pop("view", None)
        if view and views.get(view):
            w["view_id"] = views[view]
        w["filters"] = {k: _resolve(v, tenant, joined=True) for k, v in (w.get("filters") or {}).items()}
        out.append({"id": f"w{n}", **w})
    DashboardService(None, **_system(tenant)).create(
        {"name": name, "description": description, "is_shared": True, "owner_id": owner.id, "widgets": out},
        reason="Built-in shared dashboard")


def seed_settings(tenant: Tenant) -> None:
    """Default lookup lists and terms. Publishes a settings version if anything was added."""
    settings = SettingsService(None, **_system(tenant))
    # Admin edits waiting to be published must not be published by a seed run.
    had_pending = current_version(tenant.id) is not None and settings.status()["has_changes"]
    added = False
    types, values, terms = (LookupTypeService(None, **_system(tenant)), LookupValueService(None, **_system(tenant)),
                            TermService(None, **_system(tenant)))
    for order, (code, name, items) in enumerate(LOOKUPS, start=1):
        lookup = db.session.scalar(select(LookupType).where(LookupType.tenant_id == tenant.id, LookupType.code == code))
        if lookup is None:
            lookup = types.create({"code": code, "name": name, "sort_order": order * 10}, reason="Built-in list")
            lookup.is_system = True
            db.session.commit()
            added = True
        for v_order, (v_code, label, color, is_default, is_system) in enumerate(items, start=1):
            if db.session.scalar(select(LookupValue.id).where(LookupValue.lookup_type_id == lookup.id,
                                                              LookupValue.code == v_code)):
                continue
            value = values.create({"lookup_type_id": lookup.id, "code": v_code, "label": label, "color": color,
                                   "sort_order": v_order * 10, "is_default": is_default}, reason="Built-in value")
            value.is_system = is_system
            db.session.commit()
            added = True
    for key, singular, plural, description in TERMS:
        if not db.session.scalar(select(Term.id).where(Term.tenant_id == tenant.id, Term.key == key)):
            terms.create({"key": key, "singular": singular, "plural": plural, "default_singular": singular,
                          "default_plural": plural, "description": description}, reason="Built-in term")
            added = True
    added = _seed_default_chain(tenant) or added
    added = _seed_default_rules(tenant) or added
    if current_version(tenant.id) is None:
        settings.publish("Initial settings", allow_empty=True)
    elif added and not had_pending:
        settings.publish("Built-in settings added")


# ---------------------------------------------------------------------- demo organisation
DEMO_PASSWORD = "Password123!"

# code, name, type, parent code
DEMO_UNITS = [
    ("TECH", "Technology", "division", "ORG"),
    ("OPS", "Operations", "division", "ORG"),
    ("ENG", "Engineering", "department", "TECH"),
    ("QUAL", "Quality", "department", "TECH"),
    ("PLAT", "Platform Team", "team", "ENG"),
    ("MOB", "Mobile Team", "team", "ENG"),
    ("SUP", "Support Team", "team", "OPS"),
]
# code, name, parent code
DEMO_FUNCTIONS = [
    ("DEV", "Development", None),
    ("BE", "Backend development", "DEV"),
    ("FE", "Frontend development", "DEV"),
    ("QA", "Quality assurance", None),
    ("PM", "Project management", None),
    ("SUPF", "Customer support", None),
]
# email prefix, name, title, unit, function, manager prefix, roles, heads unit, leads function
DEMO_PEOPLE = [
    ("asha", "Asha Rao", "Chief Technology Officer", "TECH", "PM", None, ["executive"], "TECH", "PM"),
    ("ravi", "Ravi Kumar", "Head of Operations", "OPS", "SUPF", None, ["manager"], "OPS", None),
    ("meera", "Meera Iyer", "Engineering Manager", "ENG", "DEV", "asha", ["manager", "functional_lead"], "ENG", "DEV"),
    ("vikram", "Vikram Shah", "Quality Manager", "QUAL", "QA", "asha", ["manager", "functional_lead"], "QUAL", "QA"),
    ("karan", "Karan Mehta", "Platform Team Lead", "PLAT", "BE", "meera", ["manager"], "PLAT", "BE"),
    ("neha", "Neha Joshi", "Mobile Team Lead", "MOB", "FE", "meera", ["manager"], "MOB", "FE"),
    ("sara", "Sara Thomas", "Support Team Lead", "SUP", "SUPF", "ravi", ["manager", "functional_lead"], "SUP", "SUPF"),
    ("arjun", "Arjun Nair", "Backend Developer", "PLAT", "BE", "karan", ["contributor"], None, None),
    ("divya", "Divya Patel", "Backend Developer", "PLAT", "BE", "karan", ["contributor"], None, None),
    ("rohan", "Rohan Das", "QA Engineer", "PLAT", "QA", "karan", ["contributor"], None, None),
    ("isha", "Isha Gupta", "Mobile Developer", "MOB", "FE", "neha", ["contributor"], None, None),
    ("kabir", "Kabir Singh", "QA Engineer", "QUAL", "QA", "vikram", ["contributor"], None, None),
    ("leela", "Leela Menon", "Support Specialist", "SUP", "SUPF", "sara", ["contributor"], None, None),
]


def seed_demo(tenant: Tenant) -> None:
    units, functions, people_svc = UnitService(None, **_system(tenant)), FunctionService(None, **_system(tenant)), \
        PersonService(None, **_system(tenant))
    by_code = lambda model, code: db.session.scalar(  # noqa: E731
        select(model).where(model.tenant_id == tenant.id, model.code == code, model.is_deleted.is_(False)))
    type_id = {t.code: t.id for t in db.session.scalars(select(OrgUnitType).where(OrgUnitType.tenant_id == tenant.id))}
    role_id = {r.code: r.id for r in db.session.scalars(select(Role).where(Role.tenant_id == tenant.id))}

    for code, name, kind, parent in DEMO_UNITS:
        if not by_code(OrgUnit, code):
            units.create({"name": name, "code": code, "unit_type_id": type_id[kind],
                          "parent_id": by_code(OrgUnit, parent).id}, reason="Demo data")
    for code, name, parent in DEMO_FUNCTIONS:
        if not by_code(Function, code):
            functions.create({"name": name, "code": code,
                              "parent_id": by_code(Function, parent).id if parent else None}, reason="Demo data")

    person = {}
    for prefix, name, title, unit, fn, manager, roles, heads, leads in DEMO_PEOPLE:
        email = f"{prefix}@demo.local"
        existing = db.session.scalar(select(User).where(User.email == email))
        person[prefix] = existing or people_svc.create({
            "email": email, "full_name": name, "password": DEMO_PASSWORD, "job_title": title,
            "unit_id": by_code(OrgUnit, unit).id, "function_id": by_code(Function, fn).id,
            "manager_id": person[manager].id if manager else None,
            "role_ids": [role_id[r] for r in roles],
        }, reason="Demo data")
        if heads and by_code(OrgUnit, heads).head_id is None:
            units.update(by_code(OrgUnit, heads).id, {"head_id": person[prefix].id}, reason="Demo data")
        if leads and by_code(Function, leads).lead_id is None:
            functions.update(by_code(Function, leads).id, {"lead_id": person[prefix].id}, reason="Demo data")
    seed_demo_work(tenant)
    seed_demo_approvals(tenant)


# ---------------------------------------------------------------------- demo work (mirrors the reference prototype)
# key, parent key, type, title, unit, accountable, responsible, status, priority, category, start, end, extra
DEMO_WORK = [
    ("portal", None, "project", "Customer portal revamp", "TECH", "asha", ["meera"], "in_progress", "high", "commercial",
     "2026-09-01", "2027-01-31", {"objective": "Let customers raise and track requests online, cutting support calls by 30%.",
                                  "risks": "Payment gateway sandbox access is late.",
                                  "adoption": ["dev", "test", "accepted"]}),
    ("api", "portal", "milestone", "API redesign", "PLAT", "karan", ["karan"], "in_progress", None, None,
     "2026-10-01", "2026-11-10", {}),
    ("auth", "api", "task", "Authentication endpoints", "PLAT", None, ["arjun"], "done", None, None,
     "2026-10-05", "2026-10-30", {"actual_start": "2026-10-05", "actual_end": "2026-10-29"}),
    ("search", "api", "task", "Search endpoints", "PLAT", None, ["divya"], "in_progress", None, None,
     "2026-10-20", "2026-11-20", {"actual_start": "2026-10-21"}),
    ("beta", "portal", "milestone", "Mobile app beta", "MOB", "neha", ["isha"], "not_started", None, None,
     "2026-11-16", "2026-12-20", {}),
    ("uat", "portal", "milestone", "UAT sign-off", "QUAL", "vikram", ["kabir"], "not_started", None, None,
     "2026-12-21", "2027-01-20", {}),
    ("gateway", "portal", "action", "Payment gateway sandbox access", "TECH", None, ["meera"], "in_progress", None, None,
     "2026-11-02", "2026-11-18", {"action_type": "blocker", "severity": "critical"}),
    ("region", "portal", "action", "Choose the hosting region", "TECH", None, ["asha"], "not_started", None, None,
     None, "2026-11-10", {"action_type": "decision", "severity": "minor"}),
    ("triage", None, "project", "Support ticket triage automation", "OPS", "ravi", ["sara"], "in_progress", "medium",
     "functional", "2026-10-01", "2027-02-28", {"objective": "Route tickets to the right team automatically."}),
    ("rules", "triage", "milestone", "Triage rules defined", "SUP", "sara", ["leela"], "in_progress", None, None,
     "2026-11-01", "2026-11-30", {}),
]
# item key, person, functional role, allocation %
DEMO_ASSIGNMENTS = [
    ("portal", "arjun", "contributor", 40), ("portal", "divya", "contributor", 30), ("portal", "rohan", "tester", 20),
    ("portal", "isha", "contributor", 50), ("triage", "leela", "contributor", 60), ("triage", "sara", "lead", 30),
]


def seed_demo_work(tenant: Tenant) -> None:
    from datetime import date

    from app.modules.config.versioning import published_value_id
    from app.modules.work.models import WorkItem
    from app.modules.work.service import AssignmentService, WorkItemService

    if db.session.scalar(select(WorkItem.id).where(WorkItem.tenant_id == tenant.id)):
        return  # demo work already present (or real work exists): leave it alone
    items, assignments = WorkItemService(None, **_system(tenant)), AssignmentService(None, **_system(tenant))
    value = lambda lst, code: published_value_id(tenant.id, lst, code) if code else None  # noqa: E731
    people = {u.email.split("@")[0]: u.id for u in db.session.scalars(select(User).where(User.tenant_id == tenant.id))}
    unit = {u.code: u.id for u in db.session.scalars(select(OrgUnit).where(OrgUnit.tenant_id == tenant.id))}
    day = lambda d: date.fromisoformat(d) if d else None  # noqa: E731
    created = {}
    for key, parent, kind, title, unit_code, accountable, responsible, status, priority, category, start, end, extra \
            in DEMO_WORK:
        extra = dict(extra)
        data = {
            "title": title, "item_type_id": value("item_type", kind), "parent_id": created[parent].id if parent else None,
            "unit_id": unit[unit_code], "status_id": value("status", status), "priority_id": value("priority", priority),
            "category_id": value("category", category), "planned_start": day(start), "planned_end": day(end),
            "accountable_id": people[accountable] if accountable else None,
            "responsible_ids": [people[p] for p in responsible],
            "action_type_id": value("action_type", extra.pop("action_type", None)),
            "severity_id": value("severity", extra.pop("severity", None)),
            "adoption_stage_ids": [value("adoption_stage", c) for c in extra.pop("adoption", [])] or None,
            "actual_start": day(extra.pop("actual_start", None)), "actual_end": day(extra.pop("actual_end", None)),
            **extra,
        }
        created[key] = items.create({k: v for k, v in data.items() if v is not None},
                                    reason="Demo data: delegated to the team that delivers it")
    for key, who, role, pct in DEMO_ASSIGNMENTS:
        assignments.create({"work_item_id": created[key].id, "person_id": people[who],
                            "role_id": value("functional_role", role), "allocation_pct": pct}, reason="Demo data")


def seed_demo_approvals(tenant: Tenant) -> None:
    """Two completed milestones waiting for approval, so the inbox has something in it:
    MS-004 (Leela → Sara as functional lead) and "Test plan agreed" (Kabir → Vikram, then Meera)."""
    from app.modules.config.versioning import published_value_id
    from app.modules.workflows.models import ApprovalRequest
    from app.modules.work.models import WorkItem
    from app.modules.work.service import WorkItemService

    if db.session.scalar(select(ApprovalRequest.id).where(ApprovalRequest.tenant_id == tenant.id)):
        return
    people = {u.email.split("@")[0]: u for u in db.session.scalars(select(User).where(User.tenant_id == tenant.id))}
    by_code = lambda code: db.session.scalar(select(WorkItem).where(WorkItem.tenant_id == tenant.id,  # noqa: E731
                                                                    WorkItem.code == code))
    portal, rules = by_code("PRJ-001"), by_code("MS-004")
    if portal is None or rules is None or "kabir" not in people:
        return
    from datetime import date

    qa = db.session.scalar(select(Function.id).where(Function.tenant_id == tenant.id, Function.code == "QA"))
    plan = WorkItemService(None, **_system(tenant)).create({
        "title": "Test plan agreed", "item_type_id": published_value_id(tenant.id, "item_type", "milestone"),
        "parent_id": portal.id, "unit_id": db.session.scalar(select(OrgUnit.id).where(OrgUnit.code == "QUAL")),
        "function_id": qa, "accountable_id": people["meera"].id, "responsible_ids": [people["kabir"].id],
        "planned_start": date(2026, 10, 15), "planned_end": date(2026, 11, 12),
        "evidence_url": "https://docs.example.com/portal/test-plan",
    }, reason="Demo data: Engineering owns the test plan")
    for item, who in ((plan, "kabir"), (rules, "leela")):
        WorkItemService(people[who], tenant_id=tenant.id, source="system").update(
            item.id, {"status_id": published_value_id(tenant.id, "status", "done"), "actual_end": date(2026, 11, 12),
                      "evidence_url": item.evidence_url or "https://docs.example.com/support/triage-rules"},
            reason="Demo data: marked complete")


@click.command("seed")
@click.option("--demo", is_flag=True, help="Also create a demo organisation with people.")
@with_appcontext
def seed_command(demo):
    tenant, admin = seed_base()
    click.echo(f"Tenant: {tenant.name} (id {tenant.id})")
    click.echo(f"Admin:  {admin.email}")
    if demo:
        seed_demo(tenant)
        click.echo(f"Demo people created (password: {DEMO_PASSWORD}), e.g. meera@demo.local (Engineering Manager)")

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
ROLES = [  # code, name, scope, permissions, is_default, description
    ("administrator", "Administrator", "all", sorted(PERMISSION_CODES), False,
     "Full access to everything, including settings."),
    ("executive", "Executive", "all", VIEW + ["audit.view"], False,
     "Sees the whole organisation; does not change settings."),
    ("manager", "Manager", "unit", VIEW + ["org.manage", "people.manage"], False,
     "Sees and manages their own unit and everything below it."),
    ("functional_lead", "Functional lead", "own", VIEW, False,
     "Leads a function; sees the people in the functions they lead."),
    ("contributor", "Contributor", "own", VIEW, True,
     "Sees their own work. Given to new people by default."),
    ("viewer", "Viewer", "unit", VIEW, False, "Read-only view of their own unit."),
]

# Default lookup lists: code, name, [(code, label, colour, is_default, is_system)]
# Colours stay calm: navy accent, muted greys, and red/amber/green only where they mean status.
GREY, NAVY, TEAL, BROWN, SLATE = "#94A3B8", "#2F5D8A", "#3E8E7E", "#8A6D3B", "#64748B"
RED, AMBER, GREEN = "#B42318", "#B54708", "#067647"
LOOKUPS = [
    ("status", "Status", [
        ("not_started", "Not started", GREY, True, False), ("in_progress", "In progress", NAVY, False, False),
        ("on_hold", "On hold", AMBER, False, False), ("blocked", "Blocked", RED, False, False),
        ("done", "Done", GREEN, False, False), ("cancelled", "Cancelled", SLATE, False, False)]),
    ("priority", "Priority", [
        ("low", "Low", GREY, False, False), ("medium", "Medium", NAVY, True, False),
        ("high", "High", AMBER, False, False), ("critical", "Critical", RED, False, False)]),
    ("item_type", "Item type", [
        ("programme", "Programme", NAVY, False, False), ("project", "Project", TEAL, False, False),
        ("milestone", "Milestone", BROWN, False, False), ("task", "Task", SLATE, True, False)]),
    ("functional_role", "Functional role", [
        ("lead", "Lead", NAVY, False, False), ("contributor", "Contributor", TEAL, True, False),
        ("reviewer", "Reviewer", BROWN, False, False), ("tester", "Tester", SLATE, False, False),
        ("adviser", "Adviser", GREY, False, False)]),
    ("health", "Health", [  # the health engine relies on these four codes
        ("green", "Green", GREEN, False, True), ("amber", "Amber", AMBER, False, True),
        ("red", "Red", RED, False, True), ("grey", "Grey (no data)", GREY, True, True)]),
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

    # Built-in administrator role always holds every permission, including ones added later.
    admin_role_obj = db.session.get(Role, admin_role)
    if set(admin_role_obj.permission_codes) != PERMISSION_CODES:
        roles.update(admin_role, {"permission_codes": sorted(PERMISSION_CODES)}, reason="New permissions added")

    seed_settings(tenant)
    return tenant, admin


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

import pytest

from app.core.audit import AuditEvent
from app.core.errors import Conflict, Forbidden, ValidationFailed
from app.extensions import db
from app.modules.organisation.service import FunctionService, UnitService
from tests.conftest import person, unit_id


def team_type():
    from app.modules.organisation.models import OrgUnitType
    return db.session.scalar(db.select(OrgUnitType.id).where(OrgUnitType.code == "team"))


def test_admin_creates_company_division_department_team(admin_client):
    root = admin_client.get("/api/v1/units").get_json()["items"][0]
    types = {t["code"]: t["id"] for t in admin_client.get("/api/v1/unit-types").get_json()["items"]}
    parent = root["id"]
    for name, kind in [("Finance", "division"), ("Accounts", "department"), ("Payables", "team")]:
        resp = admin_client.post("/api/v1/units", json={"name": name, "unit_type_id": types[kind], "parent_id": parent})
        assert resp.status_code == 201, resp.get_json()
        parent = resp.get_json()["id"]
    detail = admin_client.get(f"/api/v1/units/{parent}").get_json()
    assert [p["name"] for p in detail["path"]] == ["My Organisation", "Finance", "Accounts"]


def test_unit_changes_are_audited_with_reason(admin_client, demo):
    resp = admin_client.patch(f"/api/v1/units/{unit_id('MOB')}", json={"name": "Mobile Apps Team", "reason": "Rename"})
    assert resp.status_code == 200
    row = db.session.scalar(db.select(AuditEvent).where(AuditEvent.entity_type == "org_unit",
                                                        AuditEvent.field == "name").order_by(AuditEvent.id.desc()))
    assert row.new_value == '"Mobile Apps Team"' and row.reason == "Rename"


def test_cannot_move_unit_under_its_own_child(demo, admin):
    with pytest.raises(ValidationFailed):
        UnitService(admin).update(unit_id("TECH"), {"parent_id": unit_id("PLAT")})


def test_cannot_delete_unit_with_children_or_people(demo, admin):
    with pytest.raises(Conflict):
        UnitService(admin).delete(unit_id("ENG"))  # has teams
    with pytest.raises(Conflict):
        UnitService(admin).delete(unit_id("PLAT"))  # has people


def test_manager_creates_team_inside_own_area_only(demo):
    meera = person("meera")  # heads Engineering
    team = UnitService(meera).create({"name": "Data Team", "unit_type_id": team_type(), "parent_id": unit_id("ENG")})
    assert team.parent_id == unit_id("ENG")
    with pytest.raises(Forbidden):
        UnitService(meera).create({"name": "Rogue", "unit_type_id": team_type(), "parent_id": unit_id("OPS")})


def test_manager_cannot_move_or_delete_own_top_unit(demo):
    meera = person("meera")
    with pytest.raises(Forbidden):
        UnitService(meera).update(unit_id("ENG"), {"parent_id": unit_id("OPS")})
    with pytest.raises(Forbidden):
        UnitService(meera).delete(unit_id("ENG"))


def test_manager_can_move_team_within_own_area(demo):
    meera = person("meera")
    UnitService(meera).update(unit_id("MOB"), {"parent_id": unit_id("PLAT")}, reason="Merge into platform")


def test_functions_tree_and_lead(demo, admin_client):
    items = admin_client.get("/api/v1/functions").get_json()["items"]
    dev = next(f for f in items if f["code"] == "DEV")
    assert dev["lead"]["full_name"] == "Meera Iyer"
    assert {f["code"] for f in items if f["parent_id"] == dev["id"]} == {"BE", "FE"}


def test_contributor_cannot_manage_functions(demo):
    with pytest.raises(Forbidden):
        FunctionService(person("arjun")).create({"name": "Design"})


def test_contributor_sees_own_unit_but_cannot_edit_it(demo):
    arjun = person("arjun")
    assert UnitService(arjun).get(unit_id("PLAT"))
    with pytest.raises(Forbidden):
        UnitService(arjun).update(unit_id("PLAT"), {"name": "Mine"})

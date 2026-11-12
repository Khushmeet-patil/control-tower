import pytest

from app.core.audit import AuditEvent
from app.core.errors import Forbidden, ValidationFailed
from app.extensions import db
from app.modules.people.service import PersonService
from tests.conftest import login, person, unit_id


def test_admin_adds_person_in_both_hierarchies_with_roles(demo, admin_client):
    roles = {r["code"]: r["id"] for r in admin_client.get("/api/v1/roles").get_json()["items"]}
    resp = admin_client.post("/api/v1/people", json={
        "email": "new@demo.local", "full_name": "New Person", "password": "Password123!",
        "unit_id": unit_id("MOB"), "manager_id": person("neha").id, "role_ids": [roles["contributor"]],
    })
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["unit"]["name"] == "Mobile Team" and body["manager"]["full_name"] == "Neha Joshi"
    assert [r["name"] for r in body["roles"]] == ["Contributor"]


def test_new_person_gets_default_role(demo):
    p = PersonService(person("meera")).create({
        "email": "joiner@demo.local", "full_name": "Joiner", "password": "Password123!", "unit_id": unit_id("PLAT")})
    assert [r.code for r in PersonService._roles_of(p.id)] == ["contributor"]


def test_manager_adds_people_only_in_own_area(demo):
    with pytest.raises(Forbidden):
        PersonService(person("meera")).create({
            "email": "x@demo.local", "full_name": "X", "password": "Password123!", "unit_id": unit_id("SUP")})


def test_manager_cannot_assign_roles(demo):
    admin_role = db.session.scalar(db.text("select id from roles where code='administrator'"))
    with pytest.raises(Forbidden):
        PersonService(person("meera")).update(person("arjun").id, {"role_ids": [admin_role]})


def test_reporting_loop_is_blocked(demo, admin):
    with pytest.raises(ValidationFailed):
        PersonService(admin).update(person("meera").id, {"manager_id": person("arjun").id})


def test_role_change_is_audited(demo, admin):
    viewer = db.session.scalar(db.text("select id from roles where code='viewer'"))
    PersonService(admin).update(person("arjun").id, {"role_ids": [viewer]}, reason="Read-only for now")
    row = db.session.scalar(db.select(AuditEvent).where(AuditEvent.field == "role_ids").order_by(AuditEvent.id.desc()))
    assert row.new_value == f"[{viewer}]" and row.reason == "Read-only for now"


def test_cannot_deactivate_yourself(admin):
    with pytest.raises(ValidationFailed):
        PersonService(admin).update(admin.id, {"is_active": False})


def test_reset_password_audited_and_works(demo, admin, client):
    PersonService(admin).reset_password(person("arjun").id, "NewPassword1!", reason="Forgot")
    assert login(client, "arjun@demo.local", "NewPassword1!").status_code == 200
    assert db.session.scalar(db.select(AuditEvent.id).where(AuditEvent.operation == "password_reset"))


def test_change_own_password(demo, as_user):
    c = as_user("arjun")
    resp = c.post("/api/v1/auth/change-password", json={"current_password": "wrong", "new_password": "Another123!"})
    assert resp.status_code == 422
    resp = c.post("/api/v1/auth/change-password", json={"current_password": "Password123!", "new_password": "Another123!"})
    assert resp.status_code == 200


def test_contributor_cannot_add_people_via_api(demo, as_user):
    resp = as_user("arjun").post("/api/v1/people", json={"email": "a@b.co", "full_name": "A", "password": "Password123!"})
    assert resp.status_code == 403

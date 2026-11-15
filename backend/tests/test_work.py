"""Phase 3: work items, ownership and delegation (service, API and permission tests).

The demo fixture seeds the prototype's sample work (see seed.cli.DEMO_WORK):
  PRJ-001 Customer portal revamp (TECH, accountable Asha, responsible Meera)
    MS-001 API redesign (PLAT, Karan) → TSK-001 Auth (Arjun), TSK-002 Search (Divya)
    MS-002 Mobile app beta (MOB, Neha) · MS-003 UAT sign-off (QUAL, Vikram) · ACT-001 · ACT-002
  PRJ-002 Support ticket triage automation (OPS, Ravi) → MS-004 (SUP, Sara)
"""
from datetime import timedelta

import pytest

from app.core.audit import AuditEvent
from app.core.dates import today
from app.core.errors import Forbidden, ValidationFailed
from app.extensions import db
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem
from app.modules.work.service import AssignmentService, WorkItemService, allocation_load
from tests.conftest import person, unit_id


def item(code):
    return db.session.scalar(db.select(WorkItem).where(WorkItem.code == code))


def lv(list_code, code):
    from app.modules.organisation.models import Tenant
    return published_value_id(db.session.scalar(db.select(Tenant.id)), list_code, code)


# ---------------------------------------------------------------------- Done when (1): split down the hierarchy
def test_initiative_split_down_to_department_team_and_employee_task(demo, as_user):
    c = as_user("asha")  # executive
    top = c.post("/api/v1/work-items", json={
        "title": "Company data platform", "item_type_id": lv("item_type", "programme"), "unit_id": unit_id("TECH"),
        "responsible_ids": [person("meera").id]})
    assert top.status_code == 201, top.get_json()
    top = top.get_json()
    assert top["code"].startswith("PGM-") and top["accountable"]["full_name"] == "Asha Rao"

    # Department level: a different accountable owner needs a reason.
    body = {"title": "Engineering delivery", "item_type_id": lv("item_type", "project"), "parent_id": top["id"],
            "unit_id": unit_id("ENG"), "accountable_id": person("meera").id}
    refused = c.post("/api/v1/work-items", json=body)
    assert refused.status_code == 422 and refused.get_json()["error"]["details"]["field"] == "reason"
    dept = c.post("/api/v1/work-items", json={**body, "reason": "Engineering owns delivery"}).get_json()
    assert dept["owner_overridden"] is True and dept["accountable"]["full_name"] == "Meera Iyer"

    # Team level, created by the department's accountable manager (delegation).
    c = as_user("meera")
    team = c.post("/api/v1/work-items", json={
        "title": "Platform ingestion", "item_type_id": lv("item_type", "milestone"), "parent_id": dept["id"],
        "unit_id": unit_id("PLAT")}).get_json()
    assert team["accountable_id"] == person("meera").id and team["owner_overridden"] is False  # inherited
    assert team["responsible_ids"] == dept["responsible_ids"]  # inherited
    assert team["priority_id"] == dept["priority_id"] and team["unit"]["name"] == "Platform Team"

    # Employee task: responsible owner overridden, accountable still inherited.
    task = c.post("/api/v1/work-items", json={
        "title": "Kafka connector", "item_type_id": lv("item_type", "task"), "parent_id": team["id"],
        "responsible_ids": [person("arjun").id]}).get_json()
    assert task["accountable_id"] == person("meera").id and task["responsibles"][0]["full_name"] == "Arjun Nair"

    detail = c.get(f"/api/v1/work-items/{task['id']}").get_json()
    assert [a["title"] for a in detail["ancestors"]] == [
        "Company data platform", "Engineering delivery", "Platform ingestion"]
    children = c.get("/api/v1/work-items", query_string={"ancestor_id": top["id"]}).get_json()
    assert children["total"] == 3


def test_child_work_goes_down_not_sideways(demo, as_user):
    c = as_user("meera")
    resp = c.post("/api/v1/work-items", json={
        "title": "Wrong team", "item_type_id": lv("item_type", "task"), "parent_id": item("MS-001").id,
        "unit_id": unit_id("SUP")})
    assert resp.status_code == 422 and resp.get_json()["error"]["details"]["field"] == "unit_id"


# ---------------------------------------------------------------------- Done when (2): assign three people
def test_manager_assigns_three_people_with_different_roles(demo, as_user):
    c = as_user("karan")  # accountable for MS-001
    ms = item("MS-001").id
    roles = {"lead": lv("functional_role", "lead"), "contributor": lv("functional_role", "contributor"),
             "tester": lv("functional_role", "tester")}
    for who, role, pct in (("arjun", "lead", 20), ("divya", "contributor", 25), ("rohan", "tester", 10)):
        resp = c.post(f"/api/v1/work-items/{ms}/assignments", json={
            "person_id": person(who).id, "role_id": roles[role], "allocation_pct": pct})
        assert resp.status_code == 201, resp.get_json()
    rows = c.get(f"/api/v1/work-items/{ms}/assignments").get_json()["items"]
    assert sorted((r["person"]["full_name"], r["role_id"]) for r in rows) == sorted([
        ("Arjun Nair", roles["lead"]), ("Divya Patel", roles["contributor"]), ("Rohan Das", roles["tester"])])
    # Load counts every open item: Arjun already has 40% on PRJ-001.
    assert next(r for r in rows if r["person"]["full_name"] == "Arjun Nair")["person_load"]["pct"] == 60

    dup = c.post(f"/api/v1/work-items/{ms}/assignments", json={"person_id": person("arjun").id})
    assert dup.status_code == 422


def test_load_ignores_closed_items_and_past_assignments(demo, admin):
    svc = AssignmentService(admin)
    svc.create({"work_item_id": item("TSK-001").id, "person_id": person("kabir").id, "allocation_pct": 50})  # done
    svc.create({"work_item_id": item("MS-003").id, "person_id": person("kabir").id, "allocation_pct": 30,
                "end_date": today() - timedelta(days=1)})
    svc.create({"work_item_id": item("PRJ-002").id, "person_id": person("kabir").id,
                "allocation_pct": 25})
    assert allocation_load(admin.tenant_id, [person("kabir").id])[person("kabir").id] == {"pct": 25, "items": 1}


def test_only_managers_of_the_item_assign_people(demo):
    with pytest.raises(Forbidden):  # Divya is responsible for TSK-002, not its manager
        AssignmentService(person("divya")).create({"work_item_id": item("TSK-002").id, "person_id": person("rohan").id})


# ---------------------------------------------------------------------- Done when (3): field-level rights
def test_contributor_edits_only_allowed_fields(demo, as_user):
    c = as_user("divya")  # responsible for TSK-002
    task = c.get(f"/api/v1/work-items/{item('TSK-002').id}").get_json()
    assert task["permissions"]["level"] == "contribute"
    assert "title" not in task["permissions"]["editable_fields"]

    ok = c.patch(f"/api/v1/work-items/{task['id']}", json={
        "status_id": lv("status", "done"), "actual_end": today().isoformat(), "evidence_url": "https://git.example/pr/7",
        "version": task["version"]})
    assert ok.status_code == 200, ok.get_json()
    again = ok.get_json()

    refused = c.patch(f"/api/v1/work-items/{task['id']}", json={
        "title": "Renamed", "planned_end": today().isoformat(), "version": again["version"]})
    assert refused.status_code == 403
    assert set(refused.get_json()["error"]["details"]["fields"]) == {"title", "planned_end"}

    # Sending unchanged values of other fields (as the edit form does) is fine.
    same = c.patch(f"/api/v1/work-items/{task['id']}", json={
        "title": again["title"], "remarks": "Merged", "responsible_ids": list(reversed(again["responsible_ids"])),
        "version": again["version"]})
    assert same.status_code == 200, same.get_json()


def test_assignee_contributes_but_cannot_add_children(demo):
    svc = WorkItemService(person("isha"))  # assigned 50% on PRJ-001
    portal = svc.get(item("PRJ-001").id)
    assert svc.access(portal) == "contribute" and svc.can_add_child(portal) is False
    with pytest.raises(Forbidden):
        svc.create({"title": "x", "item_type_id": lv("item_type", "task"), "parent_id": portal.id})


def test_responsible_owner_delegates_by_adding_children(demo):
    svc = WorkItemService(person("divya"))
    child = svc.create({"title": "Index tuning", "item_type_id": lv("item_type", "task"),
                        "parent_id": item("TSK-002").id})
    assert child.accountable_id == person("karan").id  # inherited from the parent
    assert svc.access(child) == "manage"  # the delivery lead manages their own breakdown


def test_seeing_an_item_is_not_editing_it(demo):
    assert WorkItemService(person("asha")).access(item("MS-004")) == "manage"  # executive: organisation-wide
    svc = WorkItemService(person("rohan"))  # assigned on PRJ-001, so sees MS-001, but has no role on it
    assert svc.access(svc.get(item("MS-001").id)) == "view"
    with pytest.raises(Forbidden):
        svc.update(item("MS-001").id, {"status_id": lv("status", "done")})


# ---------------------------------------------------------------------- scope
def test_manager_cannot_see_another_branch(demo, as_user):
    c = as_user("sara")  # Support team manager
    assert c.get(f"/api/v1/work-items/{item('PRJ-001').id}").status_code == 404
    codes = {i["code"] for i in c.get("/api/v1/work-items", query_string={"per_page": 100}).get_json()["items"]}
    assert codes == {"PRJ-002", "MS-004"}  # responsible for PRJ-002 (and so its subtree); nothing from Technology


def test_involvement_opens_the_subtree_only(demo, as_user):
    c = as_user("karan")
    assert c.get(f"/api/v1/work-items/{item('PRJ-001').id}").status_code == 404
    codes = {i["code"] for i in c.get("/api/v1/work-items", query_string={"per_page": 100}).get_json()["items"]}
    assert codes == {"MS-001", "TSK-001", "TSK-002"}
    trail = c.get(f"/api/v1/work-items/{item('TSK-001').id}").get_json()["ancestors"]
    assert trail[0] == {"id": None, "code": "…", "title": "Item you cannot open"} and trail[1]["code"] == "MS-001"


def test_list_count_matches_mine_filter(demo, as_user):
    c = as_user("meera")
    mine = c.get("/api/v1/work-items", query_string={"mine": "responsible", "per_page": 100}).get_json()
    assert {i["code"] for i in mine["items"]} == {"PRJ-001", "ACT-001"} and mine["total"] == 2


def test_contributor_cannot_create_top_level_work(demo, as_user):
    resp = as_user("arjun").post("/api/v1/work-items", json={"title": "Side project",
                                                             "item_type_id": lv("item_type", "project")})
    assert resp.status_code == 403


def test_top_level_work_only_in_own_units(demo):
    with pytest.raises(Forbidden):
        WorkItemService(person("karan")).create({"title": "x", "item_type_id": lv("item_type", "project"),
                                                 "unit_id": unit_id("SUP")})


# ---------------------------------------------------------------------- handover, audit, rules
def test_handover_needs_reason_and_is_audited(demo):
    svc = WorkItemService(person("asha"))
    with pytest.raises(ValidationFailed):
        svc.update(item("MS-002").id, {"accountable_id": person("meera").id})
    svc.update(item("MS-002").id, {"accountable_id": person("meera").id}, reason="Neha on leave")
    row = db.session.scalar(db.select(AuditEvent).where(AuditEvent.entity_type == "work_item",
                                                        AuditEvent.field == "accountable_id")
                            .order_by(AuditEvent.id.desc()))
    assert row.reason == "Neha on leave" and row.new_value == str(person("meera").id)
    assert item("MS-002").owner_overridden is True  # still differs from the parent's (Asha)


def test_every_write_creates_an_audit_row(demo, admin):
    before = db.session.scalar(db.select(db.func.count()).select_from(AuditEvent))
    svc = WorkItemService(admin)
    w = svc.create({"title": "Audit me", "item_type_id": lv("item_type", "task"), "parent_id": item("MS-004").id})
    svc.update(w.id, {"remarks": "changed"})
    a = AssignmentService(admin).create({"work_item_id": w.id, "person_id": person("leela").id, "allocation_pct": 10})
    AssignmentService(admin).delete(a.id, reason="Not needed")
    svc.delete(w.id, reason="Duplicate")
    ops = db.session.execute(db.select(AuditEvent.entity_type, AuditEvent.operation).where(AuditEvent.id > 0)
                             .order_by(AuditEvent.id.desc()).limit(5)).all()
    assert db.session.scalar(db.select(db.func.count()).select_from(AuditEvent)) == before + 5
    assert ops[0] == ("work_item", "delete") and ("assignment", "create") in ops


def test_history_shows_item_and_assignment_events(demo, as_user):
    c = as_user("asha")
    events = c.get(f"/api/v1/work-items/{item('PRJ-001').id}/history").get_json()["items"]
    assert {e["entity_type"] for e in events} == {"work_item", "assignment"}


def test_items_with_children_cannot_be_deleted(demo, as_user):
    resp = as_user("asha").delete(f"/api/v1/work-items/{item('MS-001').id}", json={"reason": "x"})
    assert resp.status_code == 409


def test_circular_dependency_is_rejected(demo, admin):
    svc = WorkItemService(admin)
    svc.update(item("MS-002").id, {"depends_on_ids": [item("MS-001").id]})
    svc.update(item("MS-003").id, {"depends_on_ids": [item("MS-002").id]})
    with pytest.raises(ValidationFailed):
        svc.update(item("MS-001").id, {"depends_on_ids": [item("MS-003").id]})


def test_dates_must_be_in_order(demo, admin):
    with pytest.raises(ValidationFailed):
        WorkItemService(admin).update(item("MS-001").id, {"planned_start": today(), "planned_end": today() - timedelta(1)})


def test_overdue_filter_and_progress(demo, as_user):
    c = as_user("asha")
    WorkItemService(person("asha")).update(item("MS-002").id, {"planned_start": today() - timedelta(days=9),
                                                                       "planned_end": today() - timedelta(days=1)})
    overdue = {i["code"] for i in c.get("/api/v1/work-items", query_string={"overdue": "1", "per_page": 100})
               .get_json()["items"]}
    assert "MS-002" in overdue and "TSK-001" not in overdue  # TSK-001 is done
    api = c.get(f"/api/v1/work-items/{item('MS-001').id}").get_json()
    assert api["progress"] == 50 and api["child_count"] == 2  # one of two tasks done


def test_custom_fields_limited_to_item_type(demo, admin):
    from app.modules.config.service import FieldService, SettingsService

    FieldService(admin).create({"entity_type": "work_item", "code": "sponsor", "label": "Sponsor",
                                "field_type": "text", "is_required": True,
                                "item_type_ids": [lv("item_type", "project")]})
    SettingsService(admin).publish("Sponsor on projects")
    svc = WorkItemService(admin)
    svc.create({"title": "Task without sponsor", "item_type_id": lv("item_type", "task"), "parent_id": item("MS-004").id})
    with pytest.raises(ValidationFailed):
        svc.create({"title": "Project without sponsor", "item_type_id": lv("item_type", "project")})
    p = svc.create({"title": "Sponsored", "item_type_id": lv("item_type", "project"),
                    "custom_fields": {"sponsor": "CFO"}})
    assert p.custom_fields == {"sponsor": "CFO"}


def test_retired_lookup_rejected_for_new_values(demo, admin):
    from app.modules.config.service import SettingsService
    from app.modules.lookups.service import LookupValueService

    LookupValueService(admin).update(lv("category", "misc"), {"is_active": False})
    SettingsService(admin).publish("Retire misc")
    with pytest.raises(ValidationFailed):
        WorkItemService(admin).update(item("MS-001").id, {"category_id": lv("category", "misc")})

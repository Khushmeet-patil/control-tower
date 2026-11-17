"""Phase 6A: capacity and availability, and demand intake (the prototype's Team & Capacity and Demand
Intake screens)."""
from datetime import timedelta

from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.core.dates import today
from app.extensions import db
from app.modules.capacity import engine
from app.modules.config.versioning import published_value_id
from app.modules.demand.models import DemandRequest
from app.modules.work.models import WorkItem
from tests.conftest import person, unit_id


def tid():
    return person("asha").tenant_id


def value(lst, code):
    return published_value_id(tid(), lst, code)


def request(code):
    return db.session.scalar(select(DemandRequest).where(DemandRequest.code == code))


def next_monday():
    return today() + timedelta(days=7 - today().weekday())


# ---------------------------------------------------------------------- capacity
def test_part_time_people_have_less_usable_capacity(demo):
    figures = engine.people_now(tid(), [person("rohan").id, person("arjun").id], 20)
    assert figures[person("rohan").id]["usable_pct"] == 40  # 50% working week, less the 20% buffer
    assert figures[person("arjun").id]["usable_pct"] == 80
    assert figures[person("rohan").id]["status"] == "balanced"  # 20% load against 40% usable


def test_time_off_shows_week_by_week(demo, as_user):
    c = as_user("karan")
    data = c.get("/api/v1/capacity/timeline", query_string={"unit_id": unit_id("PLAT"), "weeks": 3}).get_json()
    arjun = next(p for p in data["people"] if p["person"]["full_name"] == "Arjun Nair")
    this_week, next_week = arjun["weeks"][0], arjun["weeks"][1]
    assert next_week["week_start"] == next_monday().isoformat()
    assert next_week["available_pct"] == 0 and next_week["status"] == "on_leave"
    assert this_week["available_pct"] == 100 and this_week["load_pct"] == 40


def test_time_phased_allocation(demo, admin):
    from app.modules.work.service import AssignmentService

    a = db.session.scalar(select(AssignmentService.model).where(AssignmentService.model.person_id == person("divya").id))
    AssignmentService(admin).update(a.id, {"start_date": next_monday() + timedelta(days=7)}, reason="starts later")
    weeks = engine.weekly(tid(), [person("divya").id], 20, 3)[person("divya").id]
    assert [w["load_pct"] for w in weeks] == [0, 0, 30]


def test_timeline_only_for_managed_units(demo, as_user):
    assert as_user("neha").get("/api/v1/capacity/timeline", query_string={"unit_id": unit_id("PLAT")}).status_code == 403


def test_time_off_rights(demo, as_user):
    monday = next_monday() + timedelta(days=14)
    body = {"start_date": monday.isoformat(), "end_date": (monday + timedelta(days=1)).isoformat(),
            "kind_id": value("time_off_type", "leave")}
    c = as_user("divya")
    assert c.post("/api/v1/time-off", json=body).status_code == 201  # for herself
    assert c.post("/api/v1/time-off", json={**body, "person_id": person("arjun").id}).status_code == 403
    k = as_user("karan")  # manages the Platform Team
    assert k.post("/api/v1/time-off", json={**body, "person_id": person("arjun").id}).status_code == 201
    assert k.post("/api/v1/time-off", json={**body, "person_id": person("isha").id}).status_code in (403, 422)
    bad = {**body, "end_date": (monday - timedelta(days=1)).isoformat()}
    assert c.post("/api/v1/time-off", json=bad).status_code == 422
    assert db.session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "time_off")) >= 2


def test_find_people_by_skill_most_free_first(demo, as_user):
    c = as_user("meera")
    testing = value("skill", "testing")
    rows = c.get("/api/v1/capacity/people", query_string={"skill_ids": str(testing)}).get_json()["items"]
    names = [r["person"]["full_name"] for r in rows]
    assert "Rohan Das" in names and "Arjun Nair" not in names
    assert [r["free_pct"] for r in rows] == sorted([r["free_pct"] for r in rows], reverse=True)


def test_people_search_respects_scope(demo, as_user):
    rows = as_user("karan").get("/api/v1/capacity/people").get_json()["items"]
    assert "Leela Menon" not in {r["person"]["full_name"] for r in rows}


def test_assignment_suggestions(demo, as_user):
    c = as_user("karan")
    api_ms = db.session.scalar(select(WorkItem).where(WorkItem.code == "MS-001"))
    rows = c.get(f"/api/v1/work-items/{api_ms.id}/assignment-suggestions").get_json()["items"]
    names = [r["person"]["full_name"] for r in rows]
    assert names and set(names) <= {"Arjun Nair", "Divya Patel", "Rohan Das", "Karan Mehta"}
    backend = value("skill", "backend")
    rows = c.get(f"/api/v1/work-items/{api_ms.id}/assignment-suggestions", query_string={"skill_ids": backend}).get_json()["items"]
    assert all(backend in r["skill_ids"] for r in rows)


def test_skills_are_validated(demo, admin):
    from app.core.errors import ValidationFailed
    from app.modules.people.service import PersonService

    try:
        PersonService(admin).update(person("arjun").id, {"skill_ids": [value("priority", "high")]})
        raise AssertionError("expected a validation error")
    except ValidationFailed:
        pass


def test_team_capacity_rolls_up(demo, as_user):
    team = as_user("meera").get("/api/v1/team").get_json()
    members = team["members"]
    assert team["capacity"]["free_pct"] == sum(m["free_pct"] for m in members)
    plat = next(s for s in team["subunits"] if s["unit"]["name"] == "Platform Team")
    assert plat["capacity"]["people"] == 4
    free = next(k for k in team["kpis"] if k["key"] == "free")
    assert free["value"] == team["capacity"]["free_pct"]


def test_overloaded_uses_part_time_capacity(demo, admin):
    from app.modules.people.service import PersonService
    from app.modules.rules.engine import evaluate

    portal = db.session.scalar(select(WorkItem).where(WorkItem.code == "PRJ-001"))
    asha = person("asha")
    from app.modules.work.service import AssignmentService

    AssignmentService(admin).create({"work_item_id": portal.id, "person_id": asha.id, "allocation_pct": 30}, reason="t")
    rule_names = lambda: {f.rule_code for f in evaluate(tid(), [portal.id])[portal.id].findings}  # noqa: E731
    assert "owner_overloaded" not in rule_names()  # 30% of 80% usable
    PersonService(admin).update(asha.id, {"capacity_pct": 30}, reason="part time")
    assert "owner_overloaded" in rule_names()  # 30% against 24% usable


# ---------------------------------------------------------------------- demand intake
def test_requests_are_seeded_and_scoped(demo, as_user):
    codes = lambda who: {r["code"] for r in as_user(who).get("/api/v1/demand", query_string={"per_page": 50}).get_json()["items"]}  # noqa: E731
    assert codes("meera") >= {"REQ-001", "REQ-002", "REQ-003"}  # Engineering and below
    assert codes("karan") == {"REQ-002"}  # Platform Team only
    assert codes("sara") == {"REQ-001"}  # she raised it
    assert codes("leela") == set()


def test_assessment_shows_free_capacity_shortfall_and_deferrable_work(demo, as_user):
    c = as_user("meera")
    r = request("REQ-001")
    a = c.get(f"/api/v1/demand/{r.id}/assessment").get_json()
    team = c.get("/api/v1/capacity/people", query_string={"unit_id": unit_id("ENG")}).get_json()["items"]
    assert a["free_pts"] == sum(p["free_pct"] for p in team)
    assert a["need_pts"] == 120
    assert a["verdict"] == ("shortfall" if 120 > a["free_pts"] else "fits")
    unestimated = c.get(f"/api/v1/demand/{request('REQ-002').id}/assessment").get_json()
    assert unestimated["verdict"] == "not_estimated"


def test_deferrable_work_has_lower_priority(demo, as_user, admin):
    from app.modules.demand.service import DemandService

    r = request("REQ-001")
    DemandService(admin).update(r.id, {"effort_pct": 5000, "priority_id": value("priority", "critical"),
                                       "unit_id": unit_id("ORG")}, reason="big")
    a = as_user("asha").get(f"/api/v1/demand/{r.id}/assessment").get_json()
    assert a["verdict"] == "shortfall" and a["shortfall_pts"] == 5000 - a["free_pts"]
    codes = [c["code"] for c in a["candidates"]]
    assert "PRJ-001" in codes  # high priority, in delivery, below critical
    portal = next(c for c in a["candidates"] if c["code"] == "PRJ-001")
    assert portal["allocated_pts"] == 140  # 40 + 30 + 20 + 50


def test_accepting_creates_a_draft_initiative_in_one_transaction(demo, as_user):
    c = as_user("meera")
    r = request("REQ-001")
    project = value("item_type", "project")
    resp = c.post(f"/api/v1/demand/{r.id}/decide", json={
        "decision_id": value("demand_decision", "accepted"), "note": "Fits after the beta",
        "initiative": {"item_type_id": project, "unit_id": unit_id("ENG")}})
    assert resp.status_code == 200, resp.get_json()
    out = resp.get_json()
    item = db.session.get(WorkItem, out["work_item"]["id"])
    assert item.title == r.title and item.priority_id == r.priority_id and item.planned_end == r.needed_by
    assert item.remarks.startswith("From request REQ-001")
    events = db.session.scalars(select(AuditEvent).where(
        ((AuditEvent.entity_type == "work_item") & (AuditEvent.entity_id == item.id))
        | ((AuditEvent.entity_type == "demand_request") & (AuditEvent.entity_id == r.id) & (AuditEvent.field == "decision_id")))).all()
    assert len({e.correlation_id for e in events}) == 1  # one command, one trail
    assert c.post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": value("demand_decision", "rejected"),
                                                         "note": "x"}).status_code == 422


def test_a_failed_acceptance_saves_nothing(demo, as_user):
    c = as_user("meera")
    r = request("REQ-003")
    before = db.session.scalar(select(func.count()).select_from(WorkItem))
    resp = c.post(f"/api/v1/demand/{r.id}/decide", json={
        "decision_id": value("demand_decision", "accepted"),
        "initiative": {"item_type_id": value("priority", "high")}})  # not an item type
    assert resp.status_code == 422
    db.session.expire_all()
    assert db.session.scalar(select(func.count()).select_from(WorkItem)) == before
    assert request("REQ-003").decision_id == value("demand_decision", "new")


def test_decision_rules(demo, as_user):
    r = request("REQ-001")
    rejected = value("demand_decision", "rejected")
    assert as_user("sara").post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": rejected, "note": "no"}).status_code == 403
    c = as_user("meera")
    assert c.post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": rejected}).status_code == 422  # note needed
    assert c.post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": value("demand_decision", "new")}).status_code == 422
    assert c.post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": rejected, "note": "Not this year"}).status_code == 200


def test_requester_edits_only_while_open(demo, as_user):
    s = as_user("sara")
    created = s.post("/api/v1/demand", json={"title": "Chat widget", "effort_pct": 30}).get_json()
    assert created["code"].startswith("REQ-") and created["unit"]["name"] == "Support Team"
    assert created["decision_id"] == value("demand_decision", "new")
    assert s.patch(f"/api/v1/demand/{created['id']}", json={"effort_pct": 40}).status_code == 200
    assert s.patch(f"/api/v1/demand/{created['id']}", json={"decision_id": 1}).status_code == 422  # protected
    r = request("REQ-001")
    as_user("meera").post(f"/api/v1/demand/{r.id}/decide", json={"decision_id": value("demand_decision", "deferred"), "note": "Q2"})
    assert as_user("sara").patch(f"/api/v1/demand/{r.id}", json={"effort_pct": 10}).status_code == 403


def test_requests_are_hold_points_for_deciders(demo, as_user):
    ac = as_user("meera").get("/api/v1/action-centre").get_json()
    requests = [h for h in ac["hold_points"] if h["type"] == "Request"]
    assert {h["item"]["code"] for h in requests} >= {"REQ-001", "REQ-002"}
    assert any(w["rule"] == "Requests awaiting decision" for w in ac["watchlist"])
    ac = as_user("sara").get("/api/v1/action-centre").get_json()  # requester, not a decider for Engineering
    assert not [h for h in ac["hold_points"] if h["type"] == "Request"]


def test_nested_commands_roll_back_together(demo, admin):
    """The core rule behind accept-and-create: an inner command joins the outer transaction."""
    from app.modules.demand.service import DemandService

    svc = DemandService(admin)
    r = request("REQ-003")
    try:
        with svc.transaction():
            svc.update(r.id, {"title": "Changed"}, reason="t")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    db.session.expire_all()
    assert request("REQ-003").title == "Dark mode in the mobile app"

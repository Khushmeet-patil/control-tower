"""Phase 7: tools registry (Tool Centre), opening tools with access checks and audit, and built-in
form and checklist tools that save to the work item."""
from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.extensions import db
from app.modules.access.models import Role
from app.modules.tools.models import Tool
from app.modules.work.models import WorkItem
from tests.conftest import person, unit_id


def tool(name):
    return db.session.scalar(select(Tool).where(Tool.name == name))


def item(title):
    return db.session.scalar(select(WorkItem).where(WorkItem.title == title))


def names(resp):
    assert resp.status_code == 200, resp.get_json()
    return {t["name"] for t in resp.get_json()["items"]}


def events(entity_type, operation=None):
    stmt = select(AuditEvent).where(AuditEvent.entity_type == entity_type)
    if operation:
        stmt = stmt.where(AuditEvent.operation == operation)
    return db.session.scalars(stmt.order_by(AuditEvent.id)).all()


def make_viewer(admin, demo):
    """A read-only person in Technology: sees the portal project but cannot change it."""
    from app.modules.people.service import PersonService

    viewer = db.session.scalar(select(Role.id).where(Role.code == "viewer"))
    PersonService(admin).create({"email": "vera@demo.local", "full_name": "Vera Viewer", "password": "Password123!",
                                 "unit_id": unit_id("TECH"), "role_ids": [viewer]})


# ---------------------------------------------------------------------- done when
def test_tool_linked_to_a_project_is_visible_and_opens_only_for_permitted_users(demo, as_user):
    portal_tool, portal = tool("Portal design files"), item("Customer portal revamp")

    c = as_user("arjun")  # assigned to the portal
    assert "Portal design files" in names(c.get("/api/v1/tools"))
    assert "Portal design files" in names(c.get("/api/v1/tools", query_string={"work_item_id": portal.id}))
    resp = c.post(f"/api/v1/tools/{portal_tool.id}/open", json={"work_item_id": portal.id})
    assert resp.status_code == 200 and resp.get_json()["url"] == "https://design.example.com/customer-portal"
    opened = events("tool", "open")
    assert len(opened) == 1 and opened[0].actor_id == person("arjun").id and opened[0].entity_id == portal_tool.id
    assert '"PRJ-001"' in opened[0].new_value

    c = as_user("leela")  # support: not on the portal
    assert "Portal design files" not in names(c.get("/api/v1/tools"))
    assert c.post(f"/api/v1/tools/{portal_tool.id}/open", json={}).status_code == 404
    assert c.post(f"/api/v1/tools/{portal_tool.id}/open", json={"work_item_id": portal.id}).status_code == 404
    assert c.get(f"/api/v1/tools/{portal_tool.id}").status_code == 404
    assert len(events("tool", "open")) == 1  # refused openings are not logged as opened


def test_lists_never_reveal_the_address(demo, as_user):
    for t in as_user("arjun").get("/api/v1/tools").get_json()["items"]:
        assert "url" not in t
    hr = next(t for t in as_user("arjun").get("/api/v1/tools").get_json()["items"] if t["name"] == "Leave and HR portal")
    assert hr["host"] == "hr.example.com"


def test_people_on_work_below_a_linked_project_can_use_its_tool(demo, as_user):
    c = as_user("kabir")  # responsible for "Test plan agreed", under the portal; cannot open the portal itself
    portal_tool = tool("Portal design files")
    assert "Portal design files" in names(c.get("/api/v1/tools"))
    plan = item("Test plan agreed")
    assert "Portal design files" in names(c.get("/api/v1/tools", query_string={"work_item_id": plan.id}))
    assert c.post(f"/api/v1/tools/{portal_tool.id}/open", json={"work_item_id": plan.id}).status_code == 200


def test_role_limited_tool(demo, as_user):
    assert "Budget tracker" not in names(as_user("arjun").get("/api/v1/tools"))
    assert as_user("arjun").post(f"/api/v1/tools/{tool('Budget tracker').id}/open", json={}).status_code == 404
    assert "Budget tracker" in names(as_user("karan").get("/api/v1/tools"))
    assert "Budget tracker" in names(as_user("asha").get("/api/v1/tools"))


def test_unit_scoped_tool(demo, as_user):
    assert "Support knowledge base" in names(as_user("leela").get("/api/v1/tools"))  # works in Support, under OPS
    assert "Support knowledge base" not in names(as_user("arjun").get("/api/v1/tools"))
    rules = item("Triage rules defined")  # assigned to Support
    on_item = names(as_user("leela").get("/api/v1/tools", query_string={"work_item_id": rules.id}))
    assert {"Support knowledge base", "Leave and HR portal", "Go-live readiness"} <= on_item
    assert "Risk review" not in on_item  # projects only
    assert "Portal design files" not in on_item


def test_tools_on_an_item(demo, as_user):
    portal = item("Customer portal revamp")
    on_item = names(as_user("asha").get("/api/v1/tools", query_string={"work_item_id": portal.id}))
    assert on_item == {"Portal design files", "Leave and HR portal", "Budget tracker", "Go-live readiness", "Risk review"}
    # An item you cannot see has no tools for you.
    assert as_user("leela").get("/api/v1/tools", query_string={"work_item_id": portal.id}).status_code == 404


def test_retired_tool_is_hidden_and_cannot_be_opened(demo, admin, as_user):
    from app.modules.tools.service import ToolService

    hr = tool("Leave and HR portal")
    ToolService(admin).update(hr.id, {"is_active": False}, reason="Replaced")
    c = as_user("arjun")
    assert "Leave and HR portal" not in names(c.get("/api/v1/tools"))
    assert c.post(f"/api/v1/tools/{hr.id}/open", json={}).status_code == 404


# ---------------------------------------------------------------------- built-in form tools
def test_form_tool_saves_to_the_work_item_with_audit(demo, as_user):
    portal, risk = item("Customer portal revamp"), tool("Risk review")
    c = as_user("asha")  # accountable for the portal
    resp = c.post(f"/api/v1/tools/{risk.id}/submit", json={
        "work_item_id": portal.id, "values": {"risks": "Gateway access late; vendor SLA unclear."},
        "version": portal.version, "reason": "Monthly risk review"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["risks"] == "Gateway access late; vendor SLA unclear."
    change = db.session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "work_item",
                                                        AuditEvent.entity_id == portal.id, AuditEvent.field == "risks"))
    assert change.source == "tool" and change.reason == "Risk review: Monthly risk review"
    use = events("tool", "use")[-1]
    assert use.correlation_id == change.correlation_id and '"risks"' in use.new_value


def test_form_tool_only_writes_its_own_fields_and_respects_item_rights(demo, as_user):
    portal, risk = item("Customer portal revamp"), tool("Risk review")
    c = as_user("asha")
    resp = c.post(f"/api/v1/tools/{risk.id}/submit", json={"work_item_id": portal.id, "values": {"title": "Hacked"}})
    assert resp.status_code == 422
    c = as_user("arjun")  # assigned: may only update progress fields, not risks
    resp = c.post(f"/api/v1/tools/{risk.id}/submit", json={"work_item_id": portal.id, "values": {"risks": "x"}})
    assert resp.status_code == 403
    assert item("Customer portal revamp").risks == "Payment gateway sandbox access is late."
    # Not a project: the tool does not apply.
    api = item("API redesign")
    resp = as_user("karan").post(f"/api/v1/tools/{risk.id}/submit", json={"work_item_id": api.id, "values": {"risks": "x"}})
    assert resp.status_code == 404


# ---------------------------------------------------------------------- built-in checklists
def test_checklist_scores_and_passes(demo, as_user):
    portal, ready = item("Customer portal revamp"), tool("Go-live readiness")
    c = as_user("arjun")  # assigned: may fill in checklists
    url = f"/api/v1/tools/{ready.id}/response"
    resp = c.put(url, json={"work_item_id": portal.id, "answers": {"tested_end_to_end": True, "users_trained": True,
                                                                   "rollback_plan_agreed": True}})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["score_pct"] == 60 and resp.get_json()["passed"] is False
    first = resp.get_json()
    resp = c.put(url, json={"work_item_id": portal.id, "version": first["version"], "reason": "UAT signed",
                            "answers": {**first["answers"], "user_acceptance_signed_off": True}})
    assert resp.get_json()["score_pct"] == 80 and resp.get_json()["passed"] is True
    assert c.get(url, query_string={"work_item_id": portal.id}).get_json()["response"]["score_pct"] == 80

    rows = events("tool_response")
    assert [r.operation for r in rows][:1] == ["create"] and all(r.source == "tool" for r in rows)
    assert {"answers", "score_pct", "passed"} <= {r.field for r in rows if r.operation == "update"}
    # Shown in the item's history, and in the results across items.
    history = c.get(f"/api/v1/work-items/{portal.id}/history", query_string={"per_page": 100}).get_json()["items"]
    assert any(e["entity_type"] == "tool_response" for e in history)
    results = as_user("asha").get(f"/api/v1/tools/{ready.id}/responses").get_json()["items"]
    assert [(r["work_item"]["code"], r["score_pct"]) for r in results] == [("PRJ-001", 80)]
    assert as_user("leela").get(f"/api/v1/tools/{ready.id}/responses").get_json()["items"] == []  # cannot see it


def test_saving_the_same_answers_again_writes_nothing(demo, as_user):
    portal, ready = item("Customer portal revamp"), tool("Go-live readiness")
    c = as_user("arjun")
    body = {"work_item_id": portal.id, "answers": {"tested_end_to_end": True}}
    c.put(f"/api/v1/tools/{ready.id}/response", json=body)
    before = db.session.scalar(select(func.count()).select_from(AuditEvent))
    c.put(f"/api/v1/tools/{ready.id}/response", json=body)
    assert db.session.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_checklist_needs_someone_working_on_the_item(demo, admin, as_user):
    make_viewer(admin, demo)
    portal, ready = item("Customer portal revamp"), tool("Go-live readiness")
    c = as_user("vera")
    assert "Go-live readiness" in names(c.get("/api/v1/tools", query_string={"work_item_id": portal.id}))
    listed = next(t for t in c.get("/api/v1/tools", query_string={"work_item_id": portal.id}).get_json()["items"]
                  if t["name"] == "Go-live readiness")
    assert listed["can_use"] is False
    resp = c.put(f"/api/v1/tools/{ready.id}/response", json={"work_item_id": portal.id, "answers": {"users_trained": True}})
    assert resp.status_code == 403
    resp = as_user("arjun").put(f"/api/v1/tools/{ready.id}/response",
                                json={"work_item_id": portal.id, "answers": {"made_up": True}})
    assert resp.status_code == 422


# ---------------------------------------------------------------------- registry management
def test_only_tool_managers_change_the_registry(demo, as_user):
    c = as_user("meera")
    assert c.post("/api/v1/tools", json={"name": "X", "kind": "link", "url": "https://x.example.com"}).status_code == 403
    assert c.get("/api/v1/tools", query_string={"manage": "1"}).status_code == 403
    assert c.get("/api/v1/tools/options").status_code == 403


def test_registry_validation_and_audit(demo, admin_client):
    c = admin_client
    bad = [
        {"name": "Bad", "kind": "link", "url": "javascript:alert(1)"},
        {"name": "No address", "kind": "link"},
        {"name": "Odd", "kind": "macro", "url": "https://x.example.com"},
        {"name": "Form", "kind": "form", "definition": {"fields": ["title"]}},
        {"name": "Empty checklist", "kind": "checklist", "definition": {"items": []}},
        {"name": "Pass mark", "kind": "checklist", "definition": {"items": ["A"], "pass_pct": 120}},
        {"name": "Codes", "kind": "link", "url": "https://x.example.com", "work_item_codes": ["NOPE-9"]},
        {"name": "Params", "kind": "link", "url": "https://x.example.com", "context_params": {"bad key!": "x"}},
    ]
    for body in bad:
        assert c.post("/api/v1/tools", json=body).status_code == 422, body

    resp = c.post("/api/v1/tools", json={"name": "Test dashboard", "kind": "link", "url": "https://qa.example.com",
                                         "work_item_codes": ["prj-001"], "unit_ids": [unit_id("QUAL")],
                                         "context_params": {"project": "{code}"}})
    assert resp.status_code == 201, resp.get_json()
    created = resp.get_json()
    assert created["work_item_ids"] == [item("Customer portal revamp").id] and created["work_item_codes"] == ["PRJ-001"]
    assert created["context_params"] == {"project": "{code}"}
    resp = c.patch(f"/api/v1/tools/{created['id']}", json={"url": "https://qa2.example.com", "version": created["version"],
                                                            "reason": "Moved"})
    assert resp.status_code == 200
    change = events("tool", "update")[-1]
    assert change.field == "url" and change.reason == "Moved"
    assert c.delete(f"/api/v1/tools/{created['id']}", json={"reason": "Not needed"}).status_code == 200
    assert "Test dashboard" not in names(c.get("/api/v1/tools", query_string={"manage": "1"}))

    options = c.get("/api/v1/tools/options").get_json()
    assert {"risks", "status_id"} <= {f["code"] for f in options["form_fields"]}
    assert any(r["name"] == "Manager" for r in options["roles"])


def test_checklist_codes_are_made_from_labels(demo, admin_client):
    resp = admin_client.post("/api/v1/tools", json={"name": "Handover", "kind": "checklist",
                                                    "definition": {"items": ["Docs written", "Docs written", ""]}})
    assert resp.status_code == 201
    assert [i["code"] for i in resp.get_json()["definition"]["items"]] == ["docs_written", "docs_written_2"]
    assert resp.get_json()["definition"]["pass_pct"] == 100

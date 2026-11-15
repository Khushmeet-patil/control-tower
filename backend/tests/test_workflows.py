"""Phase 4: configurable approvals and validated progress.

Demo data (seed.cli.seed_demo_approvals): milestone "Test plan agreed" under PRJ-001, function QA
(lead Vikram), accountable Meera, responsible Kabir, marked complete by Kabir → waiting for Vikram.
The default chain (milestones): functional lead review → accountable owner validation (4 checks).
"""
import pytest

from app.core.audit import AuditEvent
from app.core.errors import Forbidden, ValidationFailed
from app.extensions import db
from app.modules.auth.models import User
from app.modules.config.service import SettingsService
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem
from app.modules.work.service import WorkItemService
from app.modules.workflows.models import ApprovalChain, ApprovalRequest
from app.modules.workflows.service import ApprovalService, StepService
from seed.cli import DEFAULT_CHAIN
from tests.conftest import person, unit_id

LEAD_CHECKS = DEFAULT_CHAIN["steps"][0]["checklist"]
OWNER_CHECKS = DEFAULT_CHAIN["steps"][1]["checklist"]


def lv(list_code, code):
    from app.modules.organisation.models import Tenant
    return published_value_id(db.session.scalar(db.select(Tenant.id)), list_code, code)


def item(code=None, title=None):
    stmt = db.select(WorkItem)
    return db.session.scalar(stmt.where(WorkItem.code == code) if code else stmt.where(WorkItem.title == title))


def request_for(work_item):
    return db.session.scalar(db.select(ApprovalRequest).where(ApprovalRequest.work_item_id == work_item.id)
                             .order_by(ApprovalRequest.id.desc()))


def plan_item():
    return item(title="Test plan agreed")


def progress(code, actor="asha"):
    return WorkItemService(person(actor)).progress(item(code))


# ---------------------------------------------------------------------- Done when
def test_functional_lead_then_accountable_manager_then_progress_counts(demo, as_user):
    plan = plan_item()
    req = request_for(plan)
    assert plan.approval_status == "pending" and req.current_approver_id == person("vikram").id
    before = progress("PRJ-001")

    # Meera is not the approver yet.
    c = as_user("meera")
    assert c.post(f"/api/v1/approvals/{req.id}/approve", json={"checklist": OWNER_CHECKS}).status_code == 403
    assert c.get("/api/v1/approvals/counts").get_json()["waiting_for_me"] == 0

    c = as_user("vikram")
    inbox = c.get("/api/v1/approvals", query_string={"box": "mine"}).get_json()
    assert [r["work_item"]["title"] for r in inbox["items"]] == ["Test plan agreed"]
    resp = c.post(f"/api/v1/approvals/{req.id}/approve", json={"checklist": LEAD_CHECKS, "comment": "Covers all flows"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "pending" and body["current_approver"]["full_name"] == "Meera Iyer"
    assert [s["state"] for s in body["steps"]] == ["approved", "waiting"]
    assert progress("PRJ-001") == before  # not approved yet: does not count

    c = as_user("meera")
    resp = c.post(f"/api/v1/approvals/{req.id}/approve", json={"checklist": OWNER_CHECKS})
    assert resp.get_json()["status"] == "approved"
    db.session.expire_all()
    assert plan_item().approval_status == "approved" and plan_item().approved_at is not None
    assert progress("PRJ-001") > before

    ops = [o for (o,) in db.session.execute(db.select(AuditEvent.operation).where(
        AuditEvent.entity_type == "approval_request", AuditEvent.entity_id == req.id).order_by(AuditEvent.id))]
    assert ops == ["create", "approve", "approve", "complete"]


def test_rejection_returns_the_item_with_a_note(demo, as_user):
    req = request_for(plan_item())
    c = as_user("vikram")
    assert c.post(f"/api/v1/approvals/{req.id}/reject", json={}).status_code == 422  # a note is required
    resp = c.post(f"/api/v1/approvals/{req.id}/reject", json={"comment": "Missing the payments test cases"})
    assert resp.get_json()["status"] == "rejected"
    db.session.expire_all()
    plan = plan_item()
    assert plan.approval_status == "rejected" and plan.status_id == lv("status", "in_progress") and plan.actual_end is None
    row = db.session.scalar(db.select(AuditEvent).where(AuditEvent.entity_type == "approval_request",
                                                        AuditEvent.operation == "reject"))
    assert row.reason == "Missing the payments test cases" and row.actor_id == person("vikram").id


def test_changing_the_chain_in_admin_changes_behaviour(demo, admin):
    chain = db.session.scalar(db.select(ApprovalChain).where(ApprovalChain.code == "milestone_validation"))
    StepService(admin).create({"chain_id": chain.id, "name": "CTO sign-off", "approver_kind": "person",
                               "approver_person_id": person("asha").id, "when_missing": "block"})
    in_flight = request_for(plan_item())

    svc = WorkItemService(person("neha"))  # accountable for MS-002 (Mobile app beta)
    svc.update(item("MS-002").id, {"evidence_url": "https://builds.example.com/beta"})
    svc.complete(item("MS-002").id)
    assert len(request_for(item("MS-002")).steps) == 2  # draft only: nothing changes until published

    SettingsService(admin).publish("CTO signs off milestones")
    WorkItemService(admin).update(item("MS-002").id, {"status_id": lv("status", "in_progress")})
    svc.complete(item("MS-002").id)
    assert [s["name"] for s in request_for(item("MS-002")).steps][-1] == "CTO sign-off"
    db.session.refresh(in_flight)
    assert len(in_flight.steps) == 2  # requests already running keep the chain they started with


# ---------------------------------------------------------------------- rules
def test_every_check_must_be_ticked(demo):
    req = request_for(plan_item())
    with pytest.raises(ValidationFailed) as exc:
        ApprovalService(person("vikram")).decide(req.id, approve=True, checklist=LEAD_CHECKS[:1])
    assert exc.value.details["missing"] == LEAD_CHECKS[1:]


def test_evidence_is_needed_to_complete_a_gated_milestone(demo):
    with pytest.raises(ValidationFailed) as exc:
        WorkItemService(person("neha")).complete(item("MS-002").id)
    assert exc.value.details["field"] == "evidence_url"
    assert item("MS-002").status_id != lv("status", "done")  # nothing was saved


def test_nobody_approves_their_own_work(demo):
    # Karan is accountable, responsible and the Backend lead for MS-001: his manager Meera approves instead,
    # and is asked only once even though both steps would fall to her.
    svc = WorkItemService(person("karan"))
    svc.complete(item("MS-001").id, evidence_url="https://git.example.com/api/pr/42")
    req = request_for(item("MS-001"))
    assert req.current_approver_id == person("meera").id and "manager approves" in req.waiting_note
    ApprovalService(person("meera")).decide(req.id, approve=True, checklist=LEAD_CHECKS)
    db.session.refresh(req)
    detail = ApprovalService(person("meera")).detail(req.id)
    assert req.status == "approved" and [s["state"] for s in detail["steps"]] == ["approved", "skipped"]
    assert "already approved" in detail["steps"][1]["decision"]["comment"]


def test_work_without_a_chain_counts_at_once(demo):
    WorkItemService(person("divya")).complete(item("TSK-002").id)  # tasks have no chain
    assert item("TSK-002").approval_status is None and request_for(item("TSK-002")) is None
    assert progress("MS-001") == 100  # both tasks finished


def test_reopening_cancels_the_pending_approval(demo):
    plan = plan_item()
    WorkItemService(person("kabir")).update(plan.id, {"status_id": lv("status", "in_progress")}, reason="Found a gap")
    assert request_for(plan).status == "cancelled" and plan_item().approval_status is None


def test_waits_when_nobody_can_approve_then_continues(demo, admin):
    db.session.get(User, person("meera").id).is_active = False  # the accountable owner leaves
    db.session.commit()
    req = request_for(plan_item())
    ApprovalService(person("vikram")).decide(req.id, approve=True, checklist=LEAD_CHECKS)
    db.session.refresh(req)
    assert req.status == "pending" and req.current_approver_id is None and req.waiting_note.startswith("Waiting")
    blocked = ApprovalService(admin).inbox({"box": "blocked"})
    assert [r["id"] for r in blocked["items"]] == [req.id] and blocked["items"][0]["can_decide"] is True

    db.session.get(User, person("meera").id).is_active = True
    db.session.commit()
    ApprovalService(person("asha")).retry(req.id)  # Asha manages the parent initiative
    db.session.refresh(req)
    assert req.current_approver_id == person("meera").id


def test_withdraw_returns_item_to_in_progress(demo):
    req = request_for(plan_item())
    with pytest.raises(Forbidden):
        ApprovalService(person("rohan")).withdraw(req.id)
    ApprovalService(person("kabir")).withdraw(req.id, "Submitted too early")
    assert request_for(plan_item()).status == "cancelled"
    assert plan_item().status_id == lv("status", "in_progress") and plan_item().approval_status is None


# ---------------------------------------------------------------------- progress engine
def test_weighted_progress_rolls_up(demo, admin):
    svc = WorkItemService(admin)
    task = lv("item_type", "task")
    parent = svc.create({"title": "Weighted", "item_type_id": lv("item_type", "project"), "unit_id": unit_id("PLAT")})
    big = svc.create({"title": "Big", "item_type_id": task, "parent_id": parent.id, "weight": 3})
    svc.create({"title": "Small", "item_type_id": task, "parent_id": parent.id, "progress_manual": 40})
    assert svc.progress(parent) == 10  # (0×3 + 40×1) / 4
    svc.complete(big.id)
    assert svc.progress(parent) == 85  # (100×3 + 40×1) / 4


def test_declared_but_unapproved_work_does_not_count(demo, admin):
    plan = plan_item()
    assert plan.status_id == lv("status", "done") and WorkItemService(admin).progress(plan) == 0


def test_unit_rollup_matches_items(demo, as_user):
    c = as_user("meera")
    WorkItemService(person("divya")).complete(item("TSK-002").id)
    roll = c.get("/api/v1/work-items/rollup", query_string={"unit_id": unit_id("PLAT")}).get_json()
    listed = c.get("/api/v1/work-items", query_string={"unit_id": unit_id("PLAT"), "include_descendants": "1",
                                                       "per_page": 100}).get_json()
    assert roll["items"] == listed["total"] == 3 and roll["top_level_items"] == 1
    assert roll["progress"] == progress("MS-001", "meera") == 100


def test_inbox_count_matches_list(demo, as_user):
    c = as_user("sara")  # functional lead of Customer support: MS-004 waits for her
    counts = c.get("/api/v1/approvals/counts").get_json()
    mine = c.get("/api/v1/approvals", query_string={"box": "mine"}).get_json()
    assert counts["waiting_for_me"] == mine["total"] == 1
    assert mine["items"][0]["work_item"]["code"] == "MS-004"


def test_contributor_marks_complete_through_the_api(demo, as_user):
    c = as_user("divya")
    resp = c.post(f"/api/v1/work-items/{item('TSK-002').id}/complete", json={"remarks": "Merged"})
    assert resp.status_code == 200 and resp.get_json()["progress"] == 100


def test_chain_settings_need_settings_permission(demo, as_user):
    assert as_user("meera").get("/api/v1/approval-chains").status_code == 403

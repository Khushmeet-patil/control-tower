"""Phase 5: health rules, saved views and the Action Centre.

Demo data: MS-001 API redesign (high priority, target 10 Nov 2026) and ACT-001 (critical blocker) under
PRJ-001. Tests that depend on "today" move dates relative to app.core.dates.today().
"""
from datetime import datetime, timedelta

import pytest

from app.core.dates import today
from app.core.errors import Forbidden, ValidationFailed
from app.extensions import db
from app.modules.config.service import SettingsService
from app.modules.rules.models import HealthRule
from app.modules.rules.service import HealthRuleService, action_centre
from app.modules.views.service import SavedViewService
from app.modules.work.service import WorkItemService
from app.modules.workflows.models import ApprovalRequest
from tests.conftest import person, unit_id
from tests.test_workflows import item, lv


def health(code, actor="asha"):
    return WorkItemService(person(actor)).detail(item(code).id)["health"]


def make_overdue(code, days=3):
    WorkItemService(person("asha")).update(item(code).id, {
        "planned_start": today() - timedelta(days=days + 20), "planned_end": today() - timedelta(days=days)})


# ---------------------------------------------------------------------- Done when
def test_overdue_high_priority_milestone_is_red_with_reason(demo):
    make_overdue("MS-001", 4)
    h = health("MS-001")
    assert h["code"] == "red"
    top = h["findings"][0]
    assert top["rule"] == "Overdue (high priority)" and "by 4 days" in top["reason"]
    assert top["source"]["code"] == "MS-001" and top["escalate_to"]["full_name"] == "Karan Mehta"
    assert top["recommended_action"] == "Agree a recovery date with Karan Mehta"


def test_parent_shows_which_child_caused_it(demo, admin):
    svc = WorkItemService(admin)
    for code in ("MS-001", "ACT-001", "ACT-002"):  # leave one cause, two levels down
        svc.update(item(code).id, {"planned_end": today() + timedelta(days=30)})
    svc.update(item("ACT-001").id, {"status_id": lv("status", "done")})
    make_overdue("TSK-002", 2)
    assert health("MS-001")["code"] == "red"
    portal = health("PRJ-001")
    assert portal["code"] == "red"
    cause = portal["findings"][0]
    assert cause["rule"] == "Child item" and cause["via_child"]["code"] == "MS-001"
    assert cause["source"]["code"] == "TSK-002" and "(in TSK-002)" in cause["reason"]


def test_action_centre_counts_match_the_filtered_lists(demo, as_user):
    make_overdue("MS-002", 1)  # an Amber one too (MS-002 has no priority override: high → Red; make it medium)
    WorkItemService(person("asha")).update(item("MS-002").id, {"priority_id": lv("priority", "medium")})
    for who in ("meera", "asha", "karan"):
        c = as_user(who)
        ac = c.get("/api/v1/action-centre").get_json()
        for kpi in ac["kpis"]:
            if not kpi["filters"]:
                continue
            from app.modules.work.service import portfolio_params

            listed = c.get("/api/v1/work-items", query_string={**portfolio_params(kpi["filters"]), "per_page": 1}).get_json()
            assert listed["total"] == kpi["value"], (who, kpi)
    assert any(k["key"] == "overdue_milestones" and k["value"] >= 1
               for k in as_user("asha").get("/api/v1/action-centre").get_json()["kpis"])


# ---------------------------------------------------------------------- rules behaviour
def test_missing_information_is_grey_never_green(demo, admin):
    p = WorkItemService(admin).create({"title": "Half planned", "item_type_id": lv("item_type", "project"),
                                       "unit_id": unit_id("PLAT"), "status_id": lv("status", "in_progress")})
    h = health(p.code)
    assert h["code"] == "grey"
    assert {f["rule"] for f in h["findings"]} >= {"No target date", "No priority", "No milestones"}


def test_finished_work_is_not_assessed(demo):
    assert health("TSK-001")["code"] is None


def test_changing_a_rule_in_admin_changes_health_after_publishing(demo, admin):
    make_overdue("MS-001")
    rule = db.session.scalar(db.select(HealthRule).where(HealthRule.code == "overdue_high"))
    HealthRuleService(admin).update(rule.id, {"outcome": "amber"})
    assert health("MS-001")["code"] == "red"  # draft: no change yet
    SettingsService(admin).publish("High-priority lateness is Amber")
    assert health("MS-001")["code"] == "amber"


def test_threshold_change_takes_effect(demo, admin):
    make_overdue("MS-001", 3)
    rule = db.session.scalar(db.select(HealthRule).where(HealthRule.code == "overdue_high"))
    HealthRuleService(admin).update(rule.id, {"params": {"min_days": 5, "priority_ids": rule.params["priority_ids"]}})
    SettingsService(admin).publish("Grace period")
    assert health("MS-001")["findings"][0]["rule"] == "Overdue"  # the Amber "any priority" rule still fires
    assert health("MS-001")["code"] == "amber"


def test_data_quality_flags_do_not_change_the_colour(demo, admin):
    db.session.execute(db.update(item("PRJ-002").__class__).where(item("PRJ-002").__class__.id == item("PRJ-002").id)
                       .values(updated_at=datetime.now() - timedelta(days=30)))
    db.session.commit()
    h = health("PRJ-002")
    assert h["code"] == "green" and h["flags"] == 1
    assert [f["rule"] for f in h["findings"] if f["kind"] == "data_quality"] == ["Not updated for two weeks"]


def test_approval_waiting_too_long_escalates_to_the_approver(demo):
    req = db.session.scalar(db.select(ApprovalRequest).where(ApprovalRequest.work_item_id == item(title="Test plan agreed").id))
    req.submitted_at = datetime.now() - timedelta(days=5)
    db.session.commit()
    h = health(item(title="Test plan agreed").code)
    assert h["code"] == "amber" and h["findings"][0]["escalate_to"]["full_name"] == "Vikram Shah"


def test_blocker_escalates_to_the_parents_owner(demo):
    h = health("ACT-001")
    assert h["code"] == "red" and h["findings"][0]["rule"] == "Critical blocker"
    assert h["findings"][0]["escalate_to"]["full_name"] == "Asha Rao"


def test_health_filter_on_the_list(demo, as_user):
    make_overdue("MS-001")
    c = as_user("karan")
    red = c.get("/api/v1/work-items", query_string={"health": "red", "per_page": 50}).get_json()
    assert {i["code"] for i in red["items"]} == {"MS-001"} and red["items"][0]["health"]["code"] == "red"


def test_rule_settings_are_validated(demo, admin):
    with pytest.raises(ValidationFailed):
        HealthRuleService(admin).create({"code": "bad", "name": "Bad", "rule_type": "overdue",
                                         "params": {"min_days": -1}})
    with pytest.raises(ValidationFailed):
        HealthRuleService(admin).create({"code": "bad2", "name": "Bad", "rule_type": "nope"})


# ---------------------------------------------------------------------- Action Centre ranking
def test_top_five_ranks_with_visible_factors(demo):
    make_overdue("MS-001")
    ac = action_centre(person("meera"))
    scores = [e["score"] for e in ac["top"]]
    assert scores == sorted(scores, reverse=True) and len(ac["top"]) <= 5
    first = ac["top"][0]
    assert first["item"]["code"] == "ACT-001" and first["what"] == "Critical blocker"
    assert sum(f["points"] for f in first["factors"]) == first["score"]


def test_approvals_waiting_for_me_are_in_my_top_five(demo):
    ac = action_centre(person("vikram"))
    approval = next(e for e in ac["top"] if e["kind"] == "approval")
    assert approval["item"]["title"] == "Test plan agreed" and approval["factors"][0]["points"] == 88


# ---------------------------------------------------------------------- saved views
def test_shared_views_are_seeded_for_everyone(demo, as_user):
    names = {v["name"] for v in as_user("arjun").get("/api/v1/views").get_json()["items"]}
    assert {"Actions & decisions", "Open blockers", "Pending decisions", "Milestones board"} <= names


def test_personal_and_shared_views(demo, as_user):
    c = as_user("arjun")
    mine = c.post("/api/v1/views", json={"name": "My overdue", "filters": {"overdue": "1", "level": "all"}}).get_json()
    assert mine["is_shared"] is False and mine["can_edit"] is True
    assert c.post("/api/v1/views", json={"name": "x", "is_shared": True}).status_code == 403  # contributors cannot share
    assert "My overdue" not in {v["name"] for v in as_user("divya").get("/api/v1/views").get_json()["items"]}

    c = as_user("meera")
    shared = c.post("/api/v1/views", json={"name": "Engineering board", "layout": "board", "is_shared": True,
                                           "filters": {"unit_id": str(unit_id("ENG"))}}).get_json()
    c = as_user("divya")
    seen = {v["name"]: v for v in c.get("/api/v1/views").get_json()["items"]}
    assert seen["Engineering board"]["can_edit"] is False
    assert c.patch(f"/api/v1/views/{shared['id']}", json={"name": "Mine now"}).status_code == 403


def test_views_cannot_carry_odd_filters(demo):
    with pytest.raises(ValidationFailed):
        SavedViewService(person("arjun")).create({"name": "x", "page": "work", "filters": {"a": {"nested": 1}}})
    with pytest.raises(Forbidden):
        SavedViewService(person("arjun")).create({"name": "x", "page": "work", "filters": {}, "is_shared": True})

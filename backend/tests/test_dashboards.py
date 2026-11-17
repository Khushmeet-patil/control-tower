"""Phase 6: personal home, team view, dashboards and the adoption tracker.

Done when: a manager sees only their team's numbers; a dashboard KPI matches the list it drills into.
"""
from sqlalchemy import select

from app.core.audit import AuditEvent
from app.extensions import db
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem
from app.modules.work.service import WorkItemService, portfolio_params
from tests.conftest import person, unit_id


def listed(client, filters):
    """Total of the Portfolio list that these filters open (what a drill-down link shows)."""
    resp = client.get("/api/v1/work-items", query_string={**portfolio_params(filters), "per_page": 1})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["total"]


def item(code):
    return db.session.scalar(select(WorkItem).where(WorkItem.code == code))


def tid():
    return person("asha").tenant_id


# ---------------------------------------------------------------------- team view
def test_manager_sees_only_their_team(demo, as_user):
    c = as_user("karan")
    team = c.get("/api/v1/team").get_json()
    assert team["unit"]["name"] == "Platform Team"
    assert {u["id"] for u in team["units"]} == {unit_id("PLAT")}
    assert {m["person"]["full_name"] for m in team["members"]} == {"Arjun Nair", "Divya Patel", "Rohan Das", "Karan Mehta"}
    assert c.get("/api/v1/team", query_string={"unit_id": unit_id("MOB")}).status_code == 403
    assert c.get("/api/v1/team", query_string={"unit_id": unit_id("SUP")}).status_code == 403


def test_department_manager_sees_teams_below(demo, as_user):
    team = as_user("meera").get("/api/v1/team").get_json()
    assert team["unit"]["name"] == "Engineering"
    assert {s["unit"]["name"] for s in team["subunits"]} == {"Platform Team", "Mobile Team"}
    names = {m["person"]["full_name"] for m in team["members"]}
    assert "Isha Gupta" in names and "Leela Menon" not in names


def test_contributors_have_no_team_view(demo, as_user):
    assert as_user("arjun").get("/api/v1/team").status_code == 403


def test_team_numbers_match_the_lists_they_open(demo, as_user):
    for who in ("karan", "meera", "asha"):
        c = as_user(who)
        team = c.get("/api/v1/team").get_json()
        for k in team["kpis"]:
            if k["filters"]:
                assert k["value"] == listed(c, k["filters"]), (who, k)
        for m in team["members"]:
            for n in m["counts"]:
                assert n["value"] == listed(c, n["filters"]), (who, m["person"]["full_name"], n)
        for s in team["subunits"]:
            for key in ("open", "overdue", "red"):
                assert s[key]["value"] == listed(c, s[key]["filters"]), (who, s["unit"]["name"], key)


def test_load_and_capacity_bands(demo, as_user):
    team = as_user("neha").get("/api/v1/team").get_json()
    isha = next(m for m in team["members"] if m["person"]["full_name"] == "Isha Gupta")
    assert isha["load_pct"] == 50 and isha["status"] == "balanced" and isha["free_pct"] == 30
    # Neha cannot open the portal project behind Isha's load: counted, but not listed.
    assert isha["hidden_items"] == 1


def test_allocated_filter_matches_the_load(demo, as_user):
    c = as_user("asha")
    team = c.get("/api/v1/team", query_string={"unit_id": unit_id("TECH")}).get_json()
    for m in team["members"]:
        allocated = next(n for n in m["counts"] if n["key"] == "allocated")
        assert allocated["value"] + m["hidden_items"] == m["allocated_items"]


# ---------------------------------------------------------------------- dashboards
def test_shared_dashboard_is_seeded(demo, as_user):
    items = as_user("arjun").get("/api/v1/dashboards").get_json()["items"]
    assert any(d["name"] == "Portfolio overview" and d["is_shared"] for d in items)


def test_dashboard_kpis_match_the_lists_they_drill_into(demo, as_user):
    for who in ("asha", "meera", "karan", "arjun"):
        c = as_user(who)
        board = next(d for d in c.get("/api/v1/dashboards").get_json()["items"] if d["name"] == "Portfolio overview")
        data = c.get(f"/api/v1/dashboards/{board['id']}/data").get_json()["widgets"]
        for wid, d in data.items():
            assert "error" not in d, (who, wid, d)
            if "total" in d:
                assert d["total"] == listed(c, d["filters"]), (who, wid)
            if "value" in d:
                assert d["value"] == d["total"]
            for g in d.get("groups", []):
                if g["filters"]:
                    assert g["count"] == listed(c, g["filters"]), (who, wid, g)


def test_dashboard_numbers_are_limited_to_the_viewer(demo, as_user):
    def open_items(who):
        c = as_user(who)
        board = next(d for d in c.get("/api/v1/dashboards").get_json()["items"] if d["name"] == "Portfolio overview")
        return c.get(f"/api/v1/dashboards/{board['id']}/data").get_json()["widgets"]["w1"]["value"]

    assert open_items("asha") > open_items("karan") > 0
    assert open_items("leela") < open_items("asha")


def test_personal_dashboards_and_sharing(demo, as_user):
    c = as_user("arjun")
    body = {"name": "My items", "widgets": [{"type": "kpi", "title": "Mine", "filters": {"level": "all", "mine": "any"}}]}
    resp = c.post("/api/v1/dashboards", json=body)
    assert resp.status_code == 201, resp.get_json()
    mine = resp.get_json()
    assert mine["widgets"][0]["id"]
    assert c.post("/api/v1/dashboards", json={**body, "is_shared": True}).status_code == 403
    assert db.session.scalar(select(AuditEvent.id).where(AuditEvent.entity_type == "dashboard",
                                                         AuditEvent.entity_id == mine["id"]))
    k = as_user("karan")
    assert all(d["id"] != mine["id"] for d in k.get("/api/v1/dashboards").get_json()["items"])
    assert k.get(f"/api/v1/dashboards/{mine['id']}/data").status_code == 404
    assert k.post("/api/v1/dashboards", json={**body, "is_shared": True}).status_code == 201
    shared = next(d for d in k.get("/api/v1/dashboards").get_json()["items"] if d["name"] == "Portfolio overview")
    assert k.patch(f"/api/v1/dashboards/{shared['id']}", json={"name": "Mine now"}).status_code == 403


def test_widgets_are_validated(demo, as_user):
    c = as_user("meera")
    bad = [
        [{"type": "pie"}],
        [{"type": "kpi", "filters": {"no_such_filter": "1"}}],
        [{"type": "chart", "filters": {}, "group_by": "colour"}],
        [{"type": "kpi", "filters": {"a": {"nested": 1}}}],
    ]
    for widgets in bad:
        assert c.post("/api/v1/dashboards", json={"name": "x", "widgets": widgets}).status_code == 422, widgets
    # someone else's personal view cannot be used
    a = as_user("arjun")
    view = a.post("/api/v1/views", json={"name": "Arjun's", "filters": {"mine": "any"}}).get_json()
    c = as_user("meera")
    resp = c.post("/api/v1/dashboards", json={"name": "x", "widgets": [{"type": "kpi", "view_id": view["id"]}]})
    assert resp.status_code == 422


def test_widget_built_on_a_view_follows_the_view(demo, as_user):
    c = as_user("meera")
    view = c.post("/api/v1/views", json={"name": "Overdue", "filters": {"level": "all", "overdue": "1"}}).get_json()
    d = c.post("/api/v1/dashboards", json={"name": "V", "widgets": [{"id": "k", "type": "kpi", "view_id": view["id"]}]}).get_json()
    before = c.get(f"/api/v1/dashboards/{d['id']}/data").get_json()["widgets"]["k"]
    c.patch(f"/api/v1/views/{view['id']}", json={"filters": {"level": "all", "open": "1"}})
    after = c.get(f"/api/v1/dashboards/{d['id']}/data").get_json()["widgets"]["k"]
    assert after["filters"] == {"level": "all", "open": "1"} and after["value"] == listed(c, after["filters"])
    assert before["filters"] != after["filters"]
    c.delete(f"/api/v1/views/{view['id']}", json={})  # falls back to the copy taken when saved
    kept = c.get(f"/api/v1/dashboards/{d['id']}/data").get_json()["widgets"]["k"]
    assert kept["filters"] == {"level": "all", "overdue": "1"}


# ---------------------------------------------------------------------- home and Action Centre
def test_upcoming_deadlines_filter(demo, as_user):
    c = as_user("asha")
    total = listed(c, {"level": "all", "mine": "any", "due_within": "14"})
    rows = c.get("/api/v1/work-items", query_string={"mine": "any", "due_within": "14", "per_page": 100}).get_json()["items"]
    assert total == len(rows)
    assert all(r["planned_end"] and not r["is_overdue"] for r in rows)


def test_action_centre_board_and_monthly_completions_match(demo, as_user):
    c = as_user("asha")
    ac = c.get("/api/v1/action-centre").get_json()
    for m in ac["completed_by_month"]:
        assert m["count"] == listed(c, m["filters"])
    assert ac["board"] and ac["board"][0]["health"]["code"] == "red"
    assert ac["capacity"] and ac["capacity"][0]["load_pct"] >= ac["capacity"][-1]["load_pct"]


# ---------------------------------------------------------------------- adoption
def stage(code):
    return published_value_id(tid(), "adoption_stage", code)


def test_adoption_signals_rank_without_changing_health(demo, as_user, admin):
    c = as_user("asha")
    portal = item("PRJ-001")
    ac = c.get("/api/v1/action-centre").get_json()
    assert {w["rule"] for w in ac["watchlist"]} >= {"Ready for rollout", "Built, not adopted"}
    assert any(e["what"] == "Ready for rollout" for e in ac["needed"])
    colour_before = c.get(f"/api/v1/work-items/{portal.id}").get_json()["health"]["code"]
    # rolling out and adopting clears both signals and leaves the colour alone
    resp = c.patch(f"/api/v1/work-items/{portal.id}", json={
        "adoption_stage_ids": [stage(s) for s in ("dev", "test", "accepted", "trained", "rollout", "adopted")],
        "adoption_evidence": "Usage report Nov"})
    assert resp.status_code == 200, resp.get_json()
    ac = c.get("/api/v1/action-centre").get_json()
    assert not any(w["items"][0]["code"] == "PRJ-001" for w in ac["watchlist"])
    assert c.get(f"/api/v1/work-items/{portal.id}").get_json()["health"]["code"] == colour_before


def test_adoption_stages_are_validated_and_audited(demo, as_user):
    c = as_user("asha")
    portal = item("PRJ-001")
    assert c.patch(f"/api/v1/work-items/{portal.id}", json={"adoption_stage_ids": [999999]}).status_code == 422
    priority = published_value_id(tid(), "priority", "high")
    assert c.patch(f"/api/v1/work-items/{portal.id}", json={"adoption_stage_ids": [priority]}).status_code == 422
    assert c.patch(f"/api/v1/work-items/{portal.id}", json={"adoption_stage_ids": [stage("dev")]}).status_code == 200
    assert db.session.scalar(select(AuditEvent.id).where(AuditEvent.entity_type == "work_item",
                                                         AuditEvent.entity_id == portal.id,
                                                         AuditEvent.field == "adoption_stage_ids"))


def test_contributors_cannot_tick_adoption(demo, as_user):
    rules = item("MS-004")  # Leela is responsible: she may update progress, not adoption
    resp = as_user("leela").patch(f"/api/v1/work-items/{rules.id}", json={"adoption_stage_ids": [stage("dev")]})
    assert resp.status_code == 403


def test_portfolio_params_mirror_the_portfolio_page():
    assert portfolio_params({"level": "all", "unit_id": "3", "view": "1"}) == {"unit_id": "3", "include_descendants": "1"}
    assert portfolio_params({"health": "red"}) == {"health": "red", "top_level": "1"}


def test_count_equals_list_total_for_system_service(demo):
    svc = WorkItemService(person("meera"))
    params = portfolio_params({"level": "all", "open": "1"})
    assert svc.count(params) == svc.list({**params, "per_page": 1})["total"]


# ---------------------------------------------------------------------- the prototype's weekly review
def test_hold_points_follow_the_prototype_order(demo, as_user):
    ac = as_user("asha").get("/api/v1/action-centre").get_json()
    types = [h["type"] for h in ac["hold_points"]]
    assert {"Blocker", "Decision", "Late milestone"} <= set(types)
    ranks = [h["rank"] for h in ac["hold_points"]]
    assert ranks == sorted(ranks)
    assert ac["hold_points"][0]["type"] == "Decision" and ac["hold_points"][0]["when"].startswith("overdue")


def test_approvals_waiting_for_me_are_hold_points_with_review(demo, as_user):
    ac = as_user("sara").get("/api/v1/action-centre").get_json()
    validate = [h for h in ac["hold_points"] if h["type"] == "Validate"]
    assert validate and validate[0]["approval_id"] and ac["hold_points"][0]["type"] == "Validate"


def test_board_names_next_milestone_and_next_action(demo, as_user):
    board = as_user("asha").get("/api/v1/action-centre").get_json()["board"]
    portal = next(b for b in board if b["code"] == "PRJ-001")
    assert portal["next_milestone"]["code"].startswith("MS-") and portal["next_milestone"]["holder"]
    assert portal["next_action"]["code"].startswith("ACT-")
    assert portal["to_validate"] == 1  # the test plan waits for approval


def test_blockers_and_decisions_and_capacity_open_actions(demo, as_user):
    c = as_user("asha")
    ac = c.get("/api/v1/action-centre").get_json()
    assert {(x["is_blocker"], x["is_late"]) for x in ac["blockers_decisions"]} == {(True, False), (False, True)}
    for row in ac["capacity"]:
        assert row["open_actions"] == listed(c, row["open_actions_filters"])


def test_monthly_completions_count_only_validated_milestones(demo, as_user):
    c = as_user("asha")
    month = c.get("/api/v1/action-centre").get_json()["completed_by_month"][-1]
    # two milestones were marked complete this month but still wait for approval
    assert month["count"] == 0 == listed(c, month["filters"])
    pending = listed(c, {"level": "all", "item_type_id": month["filters"]["item_type_id"], "approval_status": "pending"})
    assert pending >= 1


def test_quick_win_signal(demo, as_user, admin):
    from datetime import date

    c = as_user("sara")
    triage = item("PRJ-002")
    rules = item("MS-004")
    # nearly done: the triage project's only milestone at 85%, and Leela (60%) is not underutilised but
    # Sara (30% < 40%) is, so the quick win names her
    WorkItemService(admin).update(rules.id, {"status_id": published_value_id(tid(), "status", "in_progress"),
                                             "progress_manual": 85, "planned_end": date(2027, 1, 15)}, reason="test")
    ac = c.get("/api/v1/action-centre").get_json()
    wins = [w for w in ac["watchlist"] if w["rule"] == "Quick win"]
    assert wins and any(i["code"] in (triage.code, rules.code) for i in wins[0]["items"])


def test_team_figures_equal_the_lists_they_open_for_every_person(demo, as_user):
    """The team table's figures are worked out in bulk; each must still equal its list's total."""
    from app.modules.work.service import WorkItemService, portfolio_params
    from tests.conftest import person

    for who in ("asha", "meera", "karan", "sara"):
        data = as_user(who).get("/api/v1/team").get_json()
        assert data["members"], who
        svc = WorkItemService(person(who))
        for m in data["members"]:
            for c in m["counts"]:
                assert c["value"] == svc.count(portfolio_params(c["filters"])), (who, m["person"]["full_name"], c["key"])
            visible = {w.id for w in svc.rows({})}
            assert {i["id"] for i in m["initiatives"]} <= visible  # never names work the viewer cannot open

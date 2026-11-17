"""Phase 8: snapshots, baseline and trend, presentations (live or locked review packs) and exports."""
from datetime import timedelta
from io import BytesIO

import pytest
from sqlalchemy import select

from app.core.audit import AuditEvent
from app.core.errors import ValidationFailed
from app.extensions import db
from app.modules.config.versioning import published_value_id
from app.modules.dashboards.models import Dashboard
from app.modules.snapshots import frozen
from app.modules.snapshots.models import Snapshot
from app.modules.views.models import SavedView
from app.modules.work.models import WorkItem
from app.modules.work.service import WorkItemService, portfolio_params
from tests.conftest import person, unit_id


def item(title):
    return db.session.scalar(select(WorkItem).where(WorkItem.title == title))


def overview():
    return db.session.scalar(select(Dashboard).where(Dashboard.name == "Portfolio overview"))


def baseline():
    return db.session.scalar(select(Snapshot).where(Snapshot.is_baseline.is_(True)))


def ok(resp, code=200):
    assert resp.status_code == code, resp.get_json()
    return resp.get_json()


def correct_the_data(admin):
    """Corrections made after the review: status, dates, the dashboard and the saved view behind it."""
    svc = WorkItemService(admin)
    tid = admin.tenant_id
    api, gateway = item("API redesign"), item("Payment gateway sandbox access")
    svc.update(api.id, {"status_id": published_value_id(tid, "status", "done"),
                        "actual_end": api.planned_end, "evidence_url": "https://docs.example.com/api"}, reason="Correction")
    svc.update(gateway.id, {"planned_end": gateway.planned_end + timedelta(days=30)}, reason="Correction")
    portal = item("Customer portal revamp")
    svc.update(portal.id, {"priority_id": published_value_id(tid, "priority", "low")}, reason="Correction")
    d = overview()
    d.widgets = [w for w in d.widgets if w["type"] != "kpi"]  # someone edits the dashboard
    view = db.session.scalar(select(SavedView).where(SavedView.name == "Red and amber work"))
    if view is not None:
        view.filters = {"level": "all"}
    db.session.commit()


# ---------------------------------------------------------------------- done when
def test_a_review_from_earlier_weeks_reopens_unchanged_after_corrections(demo, admin, as_user):
    c = as_user("asha")  # executive: may take and approve snapshots
    snap = ok(c.post("/api/v1/snapshots", json={"label": "Week 46 review"}), 201)
    ok(c.post(f"/api/v1/snapshots/{snap['id']}/approve", json={}))
    pres = ok(c.post("/api/v1/presentations", json={
        "name": "Week 46 review", "mode": "snapshot", "snapshot_id": snap["id"], "is_shared": True,
        "pages": [{"dashboard_id": overview().id, "title": "Portfolio", "notes": "Red first."}]}), 201)
    pres = ok(c.post(f"/api/v1/presentations/{pres['id']}/publish", json={}))
    assert pres["status"] == "published"
    page = pres["pages"][0]["id"]
    url = f"/api/v1/presentations/{pres['id']}/pages/{page}/data"
    before_exec = ok(c.get(url))
    before_manager = ok(as_user("meera").get(url))
    assert before_manager["data"] != before_exec["data"]  # each viewer sees only their own scope
    c = as_user("asha")  # as_user re-signs-in the same client: back to Asha before making her live copy
    live = ok(c.post("/api/v1/presentations", json={"name": "Live", "pages": [{"dashboard_id": overview().id}]}), 201)
    live_url = f"/api/v1/presentations/{live['id']}/pages/{live['pages'][0]['id']}/data"
    live_before = ok(c.get(live_url))

    correct_the_data(admin)

    assert ok(as_user("asha").get(url)) == before_exec
    assert ok(as_user("meera").get(url)) == before_manager
    assert ok(as_user("asha").get(live_url))["data"] != live_before["data"]  # live figures did change


def test_frozen_figures_match_the_live_lists_when_taken(demo, admin, as_user):
    """Every Portfolio filter gives the same count from a fresh snapshot as from the live list."""
    from app.modules.snapshots.service import SnapshotService

    s = SnapshotService(admin).take(label="Check")
    tid = admin.tenant_id
    cases = [
        {}, {"level": "all"}, {"level": "all", "open": "1"}, {"level": "all", "overdue": "1"},
        {"level": "all", "health": "red,amber"}, {"level": "all", "health": "na"}, {"level": "all", "unit_id": str(unit_id("PLAT"))},
        {"level": "all", "due_within": "14"}, {"level": "all", "q": "api"}, {"level": "all", "validated": "1"},
        {"level": "all", "status_id__in": f"{published_value_id(tid, 'status', 'in_progress')},{published_value_id(tid, 'status', 'done')}"},
        {"level": "all", "planned_end__lte": "2026-12-01"}, {"level": "all", "involves": str(person("arjun").id)},
        {"level": "all", "responsible_id": str(person("kabir").id)}, {"level": "all", "accountable_id": str(person("karan").id)},
    ]
    for who in ("asha", "meera", "karan", "arjun"):
        user = person(who)
        fs = frozen.FrozenSet(user, s)
        for f in cases + [{"level": "all", "mine": "any"}, {"mine": "accountable", "level": "all"}]:
            assert len(fs.select(portfolio_params(f))) == WorkItemService(user).count(portfolio_params(f)), (who, f)


def test_unknown_filters_are_refused_rather_than_guessed(demo, admin):
    from app.modules.snapshots.service import SnapshotService

    fs = frozen.FrozenSet(admin, SnapshotService(admin).take())
    with pytest.raises(ValidationFailed):
        fs.select({"made_up": "1"})
    with pytest.raises(ValidationFailed):
        fs.select({"planned_end__gte": "not a date"})


# ---------------------------------------------------------------------- snapshots
def test_snapshot_rights_and_life_cycle(demo, as_user):
    assert as_user("arjun").post("/api/v1/snapshots", json={}).status_code == 403
    c = as_user("karan")  # manager: may take, not approve
    snap = ok(c.post("/api/v1/snapshots", json={"label": "Team check"}), 201)
    assert c.post(f"/api/v1/snapshots/{snap['id']}/approve", json={}).status_code == 403
    assert ok(c.patch(f"/api/v1/snapshots/{snap['id']}", json={"notes": "Before the sprint", "version": snap["version"]}))["notes"]
    assert c.patch(f"/api/v1/snapshots/{snap['id']}", json={"label": ""}).status_code == 422

    e = as_user("asha")
    assert e.post(f"/api/v1/snapshots/{snap['id']}/baseline", json={}).status_code == 422  # approve first
    ok(e.post(f"/api/v1/snapshots/{snap['id']}/approve", json={}))
    moved = ok(e.post(f"/api/v1/snapshots/{snap['id']}/baseline", json={}))
    assert moved["is_baseline"] and db.session.scalar(select(Snapshot).where(Snapshot.label == "Baseline")).is_baseline is False
    assert e.delete(f"/api/v1/snapshots/{snap['id']}", json={}).status_code == 409  # approved: kept

    draft = ok(e.post("/api/v1/snapshots", json={}), 201)
    assert ok(e.delete(f"/api/v1/snapshots/{draft['id']}", json={}))["ok"]
    ops = {(a.operation, a.field) for a in db.session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "snapshot",
                                                                                     AuditEvent.entity_id == snap["id"]))}
    assert {("create", None), ("update", "status"), ("update", "is_baseline"), ("update", "notes")} <= ops


def test_weekly_snapshot_is_taken_once_a_week(demo, app):
    from app.modules.snapshots.service import SnapshotService

    tid = person("asha").tenant_id
    first = SnapshotService(None, tenant_id=tid, source="system").take(kind="weekly")
    again = SnapshotService(None, tenant_id=tid, source="system").take(kind="weekly")
    assert first.id == again.id and first.period and first.kind == "weekly"
    result = app.test_cli_runner().invoke(args=["snapshot", "--weekly"])
    assert result.exit_code == 0 and first.label in result.output
    assert db.session.scalar(select(db.func.count()).select_from(Snapshot).where(Snapshot.kind == "weekly")) == 1


def test_snapshot_items_are_scoped_to_the_viewer(demo, as_user):
    everything = ok(as_user("asha").get("/api/v1/snapshots/baseline/items", query_string={"level": "all", "per_page": 100}))
    team = ok(as_user("karan").get("/api/v1/snapshots/baseline/items", query_string={"level": "all", "per_page": 100}))
    assert everything["total"] == baseline().item_count
    assert 0 < team["total"] < everything["total"]
    visible = {w.id for w in WorkItemService(person("karan")).rows({})}
    assert {i["id"] for i in team["items"]} <= visible
    assert ok(as_user("leela").get("/api/v1/snapshots/baseline/items", query_string={"q": "portal"}))["total"] == 0


def test_trend_and_baseline_comparison(demo, admin, as_user):
    from app.modules.snapshots.service import SnapshotService

    gateway = item("Payment gateway sandbox access")
    WorkItemService(admin).update(gateway.id, {"planned_end": gateway.planned_end + timedelta(days=10)}, reason="Slipped")
    SnapshotService(admin).take(label="After the slip")
    trend = ok(as_user("asha").get("/api/v1/snapshots/trend", query_string={"level": "all"}))
    assert [p["label"] for p in trend["points"]] == ["Baseline", "After the slip"]
    assert trend["points"][0]["total"] == baseline().item_count
    team = ok(as_user("karan").get("/api/v1/snapshots/trend", query_string={"level": "all"}))
    assert team["points"][0]["total"] < trend["points"][0]["total"]

    cmp = ok(as_user("asha").get("/api/v1/snapshots/compare", query_string={"level": "all"}))
    row = next(r for r in cmp["items"] if r["id"] == gateway.id)
    assert row["slip_days"] == 10 and row["change"] == "changed"
    assert cmp["summary"]["slipped"] >= 1 and cmp["items"][0]["id"] == gateway.id  # worst slip first


# ---------------------------------------------------------------------- presentations
def test_publishing_needs_an_approved_snapshot_and_locks_the_pack(demo, as_user):
    c = as_user("asha")
    draft_snap = ok(c.post("/api/v1/snapshots", json={}), 201)
    pages = [{"dashboard_id": overview().id, "notes": "Hello"}]
    live = ok(c.post("/api/v1/presentations", json={"name": "Live", "pages": pages}), 201)
    assert c.post(f"/api/v1/presentations/{live['id']}/publish", json={}).status_code == 422
    assert c.post("/api/v1/presentations", json={"name": "No snap", "mode": "snapshot", "pages": pages}).status_code == 422
    p = ok(c.post("/api/v1/presentations", json={"name": "Pack", "mode": "snapshot", "snapshot_id": draft_snap["id"],
                                                 "pages": pages}), 201)
    assert c.post(f"/api/v1/presentations/{p['id']}/publish", json={}).status_code == 422  # snapshot not approved
    ok(c.patch(f"/api/v1/presentations/{p['id']}", json={"snapshot_id": baseline().id, "version": p["version"]}))
    pub = ok(c.post(f"/api/v1/presentations/{p['id']}/publish", json={}))
    assert pub["status"] == "published" and not pub["can_edit"]
    assert c.patch(f"/api/v1/presentations/{p['id']}", json={"name": "Changed"}).status_code == 409
    assert c.delete(f"/api/v1/presentations/{p['id']}", json={}).status_code == 409
    copy = ok(c.post(f"/api/v1/presentations/{p['id']}/duplicate", json={}), 201)
    assert copy["status"] == "draft" and copy["pages"][0]["notes"] == "Hello"
    # The snapshot a presentation uses cannot be deleted.
    assert c.delete(f"/api/v1/snapshots/{draft_snap['id']}", json={}).status_code == 200  # no longer used
    assert db.session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "presentation",
                                                      AuditEvent.field == "status")) is not None


def test_presentation_visibility_and_sharing(demo, as_user):
    pages = [{"dashboard_id": overview().id}]
    mine = ok(as_user("karan").post("/api/v1/presentations", json={"name": "Mine", "pages": pages}), 201)
    assert as_user("arjun").get(f"/api/v1/presentations/{mine['id']}").status_code == 404
    assert as_user("arjun").post("/api/v1/presentations", json={"name": "S", "is_shared": True, "pages": pages}).status_code == 403
    shared = next(p for p in ok(as_user("arjun").get("/api/v1/presentations"))["items"] if p["name"] == "Weekly portfolio review")
    assert as_user("arjun").patch(f"/api/v1/presentations/{shared['id']}", json={"name": "X"}).status_code == 403
    data = ok(as_user("arjun").get(f"/api/v1/presentations/{shared['id']}/pages/{shared['pages'][0]['id']}/data"))
    assert data["page"]["notes"] and data["widgets"]


def test_live_only_widgets_say_so_in_snapshot_mode(demo, as_user):
    c = as_user("asha")
    d = ok(c.post("/api/v1/dashboards", json={"name": "Mixed", "widgets": [
        {"id": "a", "type": "actions", "title": "Top"}, {"id": "k", "type": "kpi", "title": "All", "filters": {"level": "all"}}]}), 201)
    p = ok(c.post("/api/v1/presentations", json={"name": "Mixed", "mode": "snapshot", "snapshot_id": baseline().id,
                                                 "pages": [{"dashboard_id": d["id"]}]}), 201)
    data = ok(c.get(f"/api/v1/presentations/{p['id']}/pages/{p['pages'][0]['id']}/data"))["data"]
    assert "error" in data["a"] and data["k"]["value"] == baseline().item_count


# ---------------------------------------------------------------------- exports
def test_excel_exports_match_the_lists(demo, as_user):
    from openpyxl import load_workbook

    c = as_user("karan")
    resp = c.get("/api/v1/exports/work-items.xlsx", query_string={"level": "all"})
    assert resp.status_code == 200 and resp.mimetype.endswith("spreadsheetml.sheet")
    ws = load_workbook(BytesIO(resp.data))["Work"]
    assert ws.max_row - 1 == WorkItemService(person("karan")).count(portfolio_params({"level": "all"}))
    assert ws["A1"].value == "Code" and ws["D2"].value  # status written as its label

    resp = c.get("/api/v1/snapshots/baseline/export.xlsx", query_string={"level": "all"})
    wb = load_workbook(BytesIO(resp.data))
    assert wb["Work"].max_row - 1 == ok(c.get("/api/v1/snapshots/baseline/items", query_string={"level": "all"}))["total"]
    assert any("Baseline" in str(c.value) for (c,) in wb["About"].iter_rows(min_col=2, max_col=2))


def test_review_pack_exports(demo, as_user):
    from openpyxl import load_workbook
    from pptx import Presentation as Deck

    c = as_user("asha")
    p = next(p for p in ok(c.get("/api/v1/presentations"))["items"] if p["name"] == "Weekly portfolio review")
    pptx = c.get(f"/api/v1/presentations/{p['id']}/export.pptx")
    assert pptx.status_code == 200
    deck = Deck(BytesIO(pptx.data))
    assert len(deck.slides) >= 2
    assert "red" in deck.slides[1].notes_slide.notes_text_frame.text.lower()
    pdf = c.get(f"/api/v1/presentations/{p['id']}/export.pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    xlsx = c.get(f"/api/v1/presentations/{p['id']}/export.xlsx")
    assert "Portfolio at a glance" in load_workbook(BytesIO(xlsx.data)).sheetnames
    assert c.get(f"/api/v1/presentations/{p['id']}/export.doc").status_code == 404

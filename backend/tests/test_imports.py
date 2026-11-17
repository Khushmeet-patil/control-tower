"""Phase 9: Excel/CSV import with preview, invalid-row report, add-only and update modes, external IDs;
CSV and JSON exports."""
import base64
import json
from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.extensions import db
from app.modules.auth.models import User
from app.modules.imports.models import ExternalKey
from app.modules.imports.parsing import CellError, parse_date
from app.modules.work.models import Assignment, WorkItem
from tests.conftest import person

WORK_HEADERS = ["External ID", "Type", "Title", "Parent", "Unit", "Accountable", "Status", "Priority",
                "Planned start", "Planned finish"]


def xlsx(headers, rows, sheet="Work items"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def upload(client, entity, content, mode="add", filename="plan.xlsx"):
    return client.post("/api/v1/imports", json={"entity": entity, "mode": mode, "filename": filename, "content": content})


def ok(resp, code=200):
    assert resp.status_code == code, resp.get_json()
    return resp.get_json()


def by_row(batch):
    return {r["row"]: r for r in batch["results"]}


def work_file(title="Billing revamp"):
    return xlsx(WORK_HEADERS, [
        # the milestone comes before its parent: the import orders them itself
        ["MS-9", "Milestone", "Design signed off", "INI-9", None, None, None, None, "2026-12-01", "31/12/2026"],
        ["INI-9", "Project", title, None, "Engineering", "meera@demo.local", "In progress", "High", date(2026, 12, 1), "30-Jun-2027"],
        ["ACT-9", "Action", "Pick a vendor", "INI-9", None, None, "Started-ish", None, None, "someday"],
        ["EXAMPLE-1", "Project", "Sample", None, None, None, None, None, None, None],
    ])


# ---------------------------------------------------------------------- preview and commit
def test_preview_saves_nothing_and_reports_every_bad_cell(demo, as_user):
    c = as_user("meera")  # manages Engineering
    before = db.session.scalar(select(func.count()).select_from(WorkItem))
    batch = ok(upload(c, "work_items", work_file()), 201)
    assert db.session.scalar(select(func.count()).select_from(WorkItem)) == before
    assert batch["status"] == "previewed"
    s = batch["summary"]
    assert (s["create"], s["invalid"], s["skipped"]) == (2, 1, 1)
    bad = by_row(batch)[4]
    assert bad["action"] == "invalid"
    assert {e["column"] for e in bad["errors"]} == {"Status", "Planned finish"}  # both cells reported, not just the first
    assert by_row(batch)[2]["action"] == "create"  # child row validated after its parent in the same run
    assert not db.session.scalar(select(ExternalKey.id).where(ExternalKey.external_id == "INI-9"))


def test_commit_saves_valid_rows_through_the_audited_services(demo, as_user):
    c = as_user("meera")
    batch = ok(upload(c, "work_items", work_file()), 201)
    done = ok(c.post(f"/api/v1/imports/{batch['id']}/commit", json={}))
    assert done["status"] == "committed" and done["summary"]["create"] == 2
    project = db.session.scalar(select(WorkItem).where(WorkItem.title == "Billing revamp"))
    milestone = db.session.scalar(select(WorkItem).where(WorkItem.title == "Design signed off"))
    assert milestone.parent_id == project.id and project.planned_end == date(2027, 6, 30)
    assert milestone.planned_end == date(2026, 12, 31)  # 31/12/2026 read day first
    assert project.accountable_id == person("meera").id
    assert not db.session.scalar(select(WorkItem.id).where(WorkItem.title == "Pick a vendor"))
    events = db.session.scalars(select(AuditEvent).where(AuditEvent.correlation_id == batch["correlation_id"],
                                                         AuditEvent.entity_type == "work_item")).all()
    assert events and all(e.source == "import" and e.reason == "Imported from plan.xlsx" for e in events)
    assert {e.entity_id for e in events if e.operation == "create"} == {project.id, milestone.id}
    assert c.post(f"/api/v1/imports/{batch['id']}/commit", json={}).status_code == 409


def test_reimport_updates_by_external_id_and_add_only_refuses(demo, as_user):
    c = as_user("meera")
    first = ok(upload(c, "work_items", work_file()), 201)
    ok(c.post(f"/api/v1/imports/{first['id']}/commit", json={}))
    again = ok(upload(c, "work_items", work_file("Billing revamp, phase 1")), 201)
    assert {r["action"] for r in again["results"] if r["row"] in (2, 3)} == {"invalid"}
    assert "Already exists" in by_row(again)[3]["errors"][0]["message"]

    upd = ok(upload(c, "work_items", work_file("Billing revamp, phase 1"), mode="update"), 201)
    assert by_row(upd)[3]["action"] == "update" and by_row(upd)[2]["action"] == "unchanged"
    ok(c.post(f"/api/v1/imports/{upd['id']}/commit", json={}))
    assert db.session.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.title.like("Billing revamp%"))) == 1
    change = db.session.scalar(select(AuditEvent).where(AuditEvent.field == "title", AuditEvent.source == "import"))
    assert change.new_value == '"Billing revamp, phase 1"'


def test_rows_run_with_the_importers_own_rights(demo, as_user):
    assert upload(as_user("arjun"), "work_items", work_file()).status_code == 403  # no imports.run
    c = as_user("karan")  # manages the Platform Team only
    content = xlsx(["Type", "Title", "Unit"], [["Project", "Support rota", "Support Team"], ["Project", "Cache layer", "Platform Team"]])
    batch = ok(upload(c, "work_items", content), 201)
    assert by_row(batch)[2]["action"] == "invalid" and by_row(batch)[3]["action"] == "create"
    assert "within your own area" in by_row(batch)[2]["errors"][0]["message"]  # Support is outside his area


def test_missing_required_column_and_bad_files(demo, as_user):
    c = as_user("meera")
    resp = upload(c, "work_items", xlsx(["Title"], [["Only a title"]]))
    assert resp.status_code == 422 and "Type" in resp.get_json()["error"]["message"]
    assert upload(c, "work_items", base64.b64encode(b"not a workbook").decode()).status_code == 422
    assert upload(c, "work_items", "%%%not base64").status_code == 422
    assert upload(c, "magic", work_file()).status_code == 422
    assert upload(c, "work_items", work_file(), filename="plan.exe").status_code == 422


def test_only_the_uploader_commits_and_discarded_files_stay_discarded(demo, as_user, admin_client):
    batch = ok(upload(as_user("meera"), "work_items", work_file()), 201)
    assert as_user("karan").post(f"/api/v1/imports/{batch['id']}/commit", json={}).status_code == 404  # not his
    c = as_user("meera")
    assert ok(c.post(f"/api/v1/imports/{batch['id']}/discard", json={}))["status"] == "discarded"
    assert c.post(f"/api/v1/imports/{batch['id']}/commit", json={}).status_code == 409
    assert [b["id"] for b in ok(c.get("/api/v1/imports"))["items"]] == [batch["id"]]


# ---------------------------------------------------------------------- other entities
def test_people_import_with_managers_later_in_the_file(demo, admin_client):
    content = xlsx(["Email", "Full name", "Unit", "Reports to", "Roles", "Skills", "Capacity %", "Active"], [
        ["tara@demo.local", "Tara Bose", "PLAT", "nikhil@demo.local", "Contributor", "Testing, Data analysis", "50%", "yes"],
        ["nikhil@demo.local", "Nikhil Rao", "Platform Team", "karan@demo.local", "Manager", None, 100, None],
        ["not-an-email", "Bad Row", None, None, "Wizard", None, 140, "maybe"],
    ], sheet="People")
    batch = ok(upload(admin_client, "people", content, filename="people.xlsx"), 201)
    assert [r["action"] for r in batch["results"]] == ["create", "create", "invalid"]
    assert {e["column"] for e in batch["results"][2]["errors"]} == {"Email", "Roles", "Capacity %", "Active"}
    ok(admin_client.post(f"/api/v1/imports/{batch['id']}/commit", json={}))
    tara = db.session.scalar(select(User).where(User.email == "tara@demo.local"))
    nikhil = db.session.scalar(select(User).where(User.email == "nikhil@demo.local"))
    assert tara.manager_id == nikhil.id and tara.capacity_pct == 50 and len(tara.skill_ids) == 2
    assert tara.password_hash  # a random password; an admin resets it before they sign in


def test_assignments_and_requests(demo, as_user):
    c = as_user("asha")  # accountable for the portal
    content = xlsx(["Item", "Person", "Role", "Allocation %", "Start"], [
        ["PRJ-001", "kabir@demo.local", "Tester", 25, "01/12/2026"],
        ["PRJ-001", "arjun@demo.local", None, 50, None],  # already assigned: add-only refuses
    ], sheet="Assignments")
    batch = ok(upload(c, "assignments", content), 201)
    assert [r["action"] for r in batch["results"]] == ["create", "invalid"]
    ok(c.post(f"/api/v1/imports/{batch['id']}/commit", json={}))
    a = db.session.scalar(select(Assignment).where(Assignment.person_id == person("kabir").id, Assignment.is_deleted.is_(False)))
    assert a.allocation_pct == 25 and a.start_date == date(2026, 12, 1)

    req = xlsx(["External ID", "Request", "Priority", "Effort (points)", "Needed by", "Delivering unit"],
               [["R-1", "Invoice export", "medium", 60, "30.09.2027", "PLAT"]], sheet="Requests")
    batch = ok(upload(c, "demand", req), 201)
    ok(c.post(f"/api/v1/imports/{batch['id']}/commit", json={}))
    assert db.session.scalar(select(ExternalKey.record_id).where(ExternalKey.external_id == "R-1"))


def test_csv_with_semicolons(demo, as_user):
    csv_text = "Type;Title;Unit;Planned finish\nProject;Data platform;Engineering;31-12-2026\n"
    batch = ok(upload(as_user("meera"), "work_items", base64.b64encode(csv_text.encode("utf-8-sig")).decode(),
                      filename="plan.csv"), 201)
    assert batch["results"][0]["action"] == "create"


def test_template_lists_columns_and_allowed_values(demo, as_user):
    resp = as_user("meera").get("/api/v1/imports/templates/work_items.xlsx")
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.data))
    assert [c.value for c in wb["Work items"][1]][:4] == ["External ID", "Code", "Type", "Title"]
    allowed = " ".join(str(c.value) for row in wb["Instructions"].iter_rows() for c in row if c.value)
    assert "In progress" in allowed and "EXAMPLE" in allowed
    # The template itself imports cleanly: its example rows are skipped.
    content = base64.b64encode(resp.data).decode()
    batch = ok(upload(as_user("meera"), "work_items", content), 201)
    assert batch["summary"]["skipped"] == 2 and batch["summary"]["invalid"] == 0


@pytest.mark.parametrize("raw,expected", [
    ("2026-12-31", date(2026, 12, 31)), ("31/12/2026", date(2026, 12, 31)), ("01/02/2026", date(2026, 2, 1)),
    ("31-Dec-2026", date(2026, 12, 31)), ("Dec 31 2026", date(2026, 12, 31)), ("December 31, 2026", date(2026, 12, 31)),
    ("31.12.2026", date(2026, 12, 31)), (46387, date(2026, 12, 31)), ("2026-12-31 10:30", date(2026, 12, 31)),
])
def test_flexible_dates(raw, expected):
    assert parse_date(raw) == expected


def test_unreadable_dates_are_refused():
    with pytest.raises(CellError):
        parse_date("soon")


# ---------------------------------------------------------------------- CSV and JSON exports
def test_csv_and_json_exports_match_the_list(demo, as_user):
    c = as_user("karan")
    from app.modules.work.service import WorkItemService, portfolio_params

    expected = WorkItemService(person("karan")).count(portfolio_params({"level": "all"}))
    csv_resp = c.get("/api/v1/exports/work-items.csv", query_string={"level": "all"})
    lines = csv_resp.data.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("Code,Title") and len(lines) - 1 == expected
    data = c.get("/api/v1/exports/work-items.json", query_string={"level": "all"}).get_json()
    assert len(data["items"]) == expected and "Status" in data["items"][0]
    json.dumps(data)


def test_csv_export_neutralises_formulas(demo, admin):
    from app.modules.snapshots.exports import work_csv
    from app.modules.work.service import WorkItemService

    item = db.session.scalar(select(WorkItem).where(WorkItem.code == "PRJ-001"))
    WorkItemService(admin).update(item.id, {"title": "=HYPERLINK(\"http://evil\")"}, reason="test")
    assert "'=HYPERLINK" in work_csv(admin, {}).decode("utf-8-sig")


def test_excel_exports_never_turn_text_into_formulas(demo, admin, as_user):
    from app.modules.work.service import WorkItemService

    item = db.session.scalar(select(WorkItem).where(WorkItem.code == "PRJ-001"))
    WorkItemService(admin).update(item.id, {"title": "=HYPERLINK(\"http://evil\",\"x\")"}, reason="test")
    resp = as_user("asha").get("/api/v1/exports/work-items.xlsx", query_string={"level": "all"})
    ws = load_workbook(BytesIO(resp.data))["Work"]
    cell = next(r[1] for r in ws.iter_rows(min_row=2) if r[0].value == "PRJ-001")
    assert cell.data_type == "s" and cell.value.startswith("=HYPERLINK")

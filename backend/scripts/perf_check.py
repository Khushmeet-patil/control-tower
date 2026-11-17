"""Performance check against a large data set (Phase 9).

    cd backend && PYTHONPATH=. .venv/bin/python scripts/perf_check.py [--items 20000] [--keep]

Builds a throwaway SQLite database (never the configured one) holding the demo organisation plus
a large synthetic portfolio: programmes → projects → milestones → tasks, spread over 30 teams, with
300 people and assignments. The synthetic rows are bulk-inserted to save time, so they have no audit
history; everything the app calculates (progress, health, scope) is still worked out from them.

It then times the main screens through the real API, as an executive (sees everything) and as a team
manager (sees one branch), three runs each, and prints the median. Anything over the budget is flagged.
"""
import argparse
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

BUDGET_MS = 2000         # a screen
EXPORT_BUDGET_MS = 10000  # a file download of the whole list

parser = argparse.ArgumentParser()
parser.add_argument("--items", type=int, default=20000)
parser.add_argument("--keep", action="store_true", help="Keep the database file afterwards")
args = parser.parse_args()

workdir = Path(tempfile.mkdtemp(prefix="ct-perf-"))
os.environ["TEST_DATABASE_URL"] = f"sqlite:///{workdir / 'perf.db'}"  # read when the config is imported

from sqlalchemy import insert, select  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


def build(app, n_items):
    from app.modules.auth.models import User
    from app.modules.config.versioning import published_value_id
    from app.modules.organisation.models import OrgUnit, OrgUnitType, Tenant
    from app.modules.organisation.service import UnitService
    from app.modules.work.models import Assignment, WorkItem, WorkItemClosure, WorkItemResponsible
    from seed.cli import seed_base, seed_demo

    rnd = random.Random(7)
    tenant, admin = seed_base()
    seed_demo(tenant)
    tid = tenant.id
    sysargs = {"tenant_id": tid, "source": "system"}
    team_type = db.session.scalar(select(OrgUnitType.id).where(OrgUnitType.code == "team"))
    eng = db.session.scalar(select(OrgUnit).where(OrgUnit.code == "ENG"))
    ops = db.session.scalar(select(OrgUnit).where(OrgUnit.code == "OPS"))
    units = UnitService(None, **sysargs)
    teams = [units.create({"name": f"Squad {i:02d}", "code": f"SQ{i:02d}", "unit_type_id": team_type,
                           "parent_id": (eng if i % 2 else ops).id}).id for i in range(30)]
    karan = db.session.scalar(select(User).where(User.email == "karan@demo.local"))
    units.update(teams[1], {"head_id": karan.id})  # karan manages one extra squad: a realistic branch

    pw = karan.password_hash
    db.session.execute(insert(User), [{"tenant_id": tid, "email": f"p{i}@perf.local", "full_name": f"Person {i}",
                                       "unit_id": teams[i % 30], "password_hash": pw, "is_admin": False,
                                       "is_active": True, "capacity_pct": 100, "version": 1, "is_deleted": False}
                                      for i in range(300)])
    people = list(db.session.scalars(select(User.id).where(User.email.like("%@perf.local"))))
    v = lambda lst, code: published_value_id(tid, lst, code)  # noqa: E731
    types = {c: v("item_type", c) for c in ("programme", "project", "milestone", "task")}
    statuses = [v("status", c) for c in ("not_started", "in_progress", "in_progress", "in_progress", "done", "blocked")]
    priorities = [v("priority", c) for c in ("low", "medium", "high", "critical")]
    today = date.today()

    next_id = (db.session.scalar(select(WorkItem.id).order_by(WorkItem.id.desc()).limit(1)) or 0) + 1
    rows, closure, resp, assigns = [], [], [], []
    shape = [("programme", 10), ("project", 20), ("milestone", 10)]
    per_task = max(1, n_items // (10 * 20 * 10) - 1)
    counter = {"n": 0}

    def add(kind, parent, ancestors, unit):
        nonlocal next_id
        i = next_id
        next_id += 1
        counter["n"] += 1
        start = today + timedelta(days=rnd.randint(-200, 100))
        rows.append({"id": i, "tenant_id": tid, "code": f"P{kind[:2].upper()}-{i}", "title": f"{kind.title()} {i}",
                     "item_type_id": types[kind], "parent_id": parent, "status_id": rnd.choice(statuses),
                     "priority_id": rnd.choice(priorities), "unit_id": unit, "accountable_id": rnd.choice(people),
                     "owner_overridden": False, "planned_start": start,
                     "planned_end": start + timedelta(days=rnd.randint(10, 200)), "progress_manual": rnd.randint(0, 100),
                     "weight": 1, "version": 1, "is_deleted": False})
        closure.append({"ancestor_id": i, "descendant_id": i, "depth": 0})
        for depth, a in enumerate(reversed(ancestors), 1):
            closure.append({"ancestor_id": a, "descendant_id": i, "depth": depth})
        resp.append({"work_item_id": i, "user_id": rnd.choice(people)})
        if kind in ("project", "task") and rnd.random() < 0.3:
            assigns.append({"tenant_id": tid, "work_item_id": i, "person_id": rnd.choice(people),
                            "allocation_pct": rnd.choice((10, 20, 30, 40)), "version": 1, "is_deleted": False})
        return i

    for _ in range(shape[0][1]):
        unit = rnd.choice(teams)
        pg = add("programme", None, [], unit)
        for _ in range(shape[1][1]):
            unit = rnd.choice(teams)
            pr = add("project", pg, [pg], unit)
            for _ in range(shape[2][1]):
                ms = add("milestone", pr, [pg, pr], unit)
                for _ in range(per_task):
                    add("task", ms, [pg, pr, ms], unit)
    for table, data in ((WorkItem, rows), (WorkItemClosure, closure), (WorkItemResponsible, resp), (Assignment, assigns)):
        for k in range(0, len(data), 2000):
            db.session.execute(insert(table), data[k:k + 2000])
    db.session.commit()
    return counter["n"], len(assigns), teams


def timed(client, path, runs=3, method="get", **kw):
    times, status = [], None
    for _ in range(runs):
        t = time.perf_counter()
        resp = getattr(client, method)(path, **kw)
        times.append((time.perf_counter() - t) * 1000)
        status = resp.status_code
    return statistics.median(times), status


def main():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        t = time.perf_counter()
        n, n_assign, teams = build(app, args.items)
        print(f"Built {n} work items, {n_assign} assignments, 300 people in {time.perf_counter() - t:.1f}s ({workdir})")

        from app.modules.dashboards.models import Dashboard
        from app.modules.snapshots.service import SnapshotService

        dash = db.session.scalar(select(Dashboard.id).limit(1))
        t = time.perf_counter()
        SnapshotService(None, tenant_id=1, source="system").take(label="Perf")
        snap_ms = (time.perf_counter() - t) * 1000

        checks = [
            ("Portfolio, top level", "/api/v1/work-items?top_level=1"),
            ("Portfolio, every level", "/api/v1/work-items?per_page=50&sort=planned_end"),
            ("Portfolio, red only (health filter)", "/api/v1/work-items?health=red&per_page=50"),
            ("Portfolio search", "/api/v1/work-items?q=Task%2012"),
            ("Item page", "ITEM"),
            ("Action Centre", "/api/v1/action-centre"),
            ("Dashboard data", f"/api/v1/dashboards/{dash}/data"),
            ("My team", "/api/v1/team"),
            ("Approvals", "/api/v1/approvals?box=mine"),
            ("Trend (1 snapshot)", "/api/v1/snapshots/trend?level=all"),
            ("Excel export, every level", "/api/v1/exports/work-items.xlsx?level=all"),
        ]
        results = []
        for who in ("asha", "karan"):
            c = app.test_client()
            assert c.post("/api/v1/auth/login", json={"email": f"{who}@demo.local", "password": "Password123!"}).status_code == 200
            mine = c.get("/api/v1/work-items?per_page=1&sort=-created_at").get_json()["items"]  # an item they can open
            for label, path in checks:
                path = f"/api/v1/work-items/{mine[0]['id']}" if path == "ITEM" else path
                ms, status = timed(c, path)
                results.append((who, label, ms, status))
        print(f"\n{'Who':7} {'Screen':38} {'Median ms':>10}  Status")
        print(f"{'system':7} {'Take a snapshot (all items)':38} {snap_ms:10.0f}  -")
        slow = []
        for who, label, ms, status in results:
            budget = EXPORT_BUDGET_MS if "export" in label.lower() else BUDGET_MS
            flag = "  SLOW" if ms > budget else ""
            print(f"{who:7} {label:38} {ms:10.0f}  {status}{flag}")
            if ms > budget or status != 200:
                slow.append((who, label, ms, status))
        print(f"\nBudget {BUDGET_MS} ms per screen, {EXPORT_BUDGET_MS} ms per export: {len(slow)} over budget or failing.")
    if not args.keep:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())

# Control Tower

An organisation-wide platform for tracking work: one trusted copy of the data, with administrative and functional hierarchies, delegation, configurable approvals, explained health status, role-based access, dashboards, and links to external tools.

- **Build plan and progress:** [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md). Read it first, work phase by phase, and update the progress tracker when a phase's "Done when" checks pass.
- **Coding and UI rules:** [docs/CONVENTIONS.md](docs/CONVENTIONS.md). Follow them for every change.
- **Manager's reference prototype:** `reference/MY Control Tower 1.html`, analysed in [docs/MVP_ANALYSIS.md](docs/MVP_ANALYSIS.md). It is the target for screens, look and rules; build them properly on the platform, never copy its storage or code.
- **Original vision:** `single_source_of_truth_project_control_platform_blueprint (1).md` (reference only; where it conflicts with BUILD_PLAN.md, BUILD_PLAN.md wins).

## Stack
Python Flask + SQLAlchemy 2 + Alembic + Pydantic (`backend/`), MySQL via PyMySQL, and plain HTML/CSS/JS ES modules (`frontend/`, served by Flask).

## Commands (run from `backend/`)
- Install: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Configure: copy `.env.example` to `.env` and set `DATABASE_URL`
- Migrate: `.venv/bin/flask --app run db upgrade`
- Seed: `.venv/bin/flask --app run seed` (add `--demo` for a sample organisation; demo password `Password123!`)
- Run: `.venv/bin/python run.py` → http://localhost:5050 (5000 is taken by macOS AirPlay)
- Test: `.venv/bin/pytest`
- Export the production MySQL schema: `.venv/bin/flask --app run schema-export` → `database/schema_mysql.sql`

## Database rule
Local development uses SQLite (`DATABASE_URL=sqlite:///control_tower_dev.db`). After **every** model change: create the migration, upgrade the local database, then run `schema-export`, so that `backend/database/schema_mysql.sql` always matches the code. A test enforces this. See CONVENTIONS.md.

## Status
Phases 0–6 done. Running on local SQLite; the production MySQL schema is kept in `backend/database/schema_mysql.sql`. Next: Phase 6A (capacity and availability, see docs/CAPABILITY_PHASE_MAP.md) or Phase 7 (tools registry).

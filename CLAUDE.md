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
- Weekly snapshot (schedule it, e.g. Mondays 06:00): `.venv/bin/flask --app run snapshot --weekly`
- Notifications: send queued email and webhooks (schedule every minute) `.venv/bin/flask --app run notify --deliver`; daily checks (due soon, overdue, turned Red; e.g. 07:00) `.venv/bin/flask --app run notify --checks`
- Backup (schedule daily): `.venv/bin/flask --app run backup` · restore: `flask --app run restore <file> --yes`
- Performance check (large synthetic data, throwaway DB): `PYTHONPATH=. .venv/bin/python scripts/perf_check.py`
- Export the production MySQL schema: `.venv/bin/flask --app run schema-export` → `database/schema_mysql.sql`

## Database rule
Local development uses SQLite (`DATABASE_URL=sqlite:///control_tower_dev.db`). After **every** model change: create the migration, upgrade the local database, then run `schema-export`, so that `backend/database/schema_mysql.sql` always matches the code. A test enforces this. See CONVENTIONS.md.

## Status
All phases (0–10, with 6A) done, including everything earlier phases deferred. Running on local SQLite; the production MySQL schema is kept in `backend/database/schema_mysql.sql`. Optional settings for email, Microsoft Entra ID and the public address are in `backend/.env.example`. Security notes: [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md).

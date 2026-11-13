# Control Tower — Phased Build Plan

## Progress tracker
| Phase | Name | Status |
|---|---|---|
| 0 | Foundation | Done (local SQLite; MySQL schema in backend/database/schema_mysql.sql) |
| 1 | Organisation, people and access | Done |
| 2 | Lookups and settings | Done (custom fields wired to People; work items reuse them in Phase 3) |
| 3 | Work items, ownership and delegation | Not started |
| 4 | Configurable approvals and validated progress | Not started |
| 5 | Health rules, saved filters and Action Centre | Not started |
| 6 | Personal home, team view and dashboards | Not started |
| 7 | Tools registry | Not started |
| 8 | Snapshots, exports and presentation | Not started |
| 9 | Import, backup and hardening | Not started |

## Context
Control Tower is an organisation-wide platform for tracking work. It keeps one trusted copy of all work data and is meant to replace spreadsheets. It is based on the blueprint in `single_source_of_truth_project_control_platform_blueprint (1).md`, with the user's confirmed changes:
- A simple stack: plain HTML, CSS and JS, a Python Flask server, and **MySQL**.
- Two hierarchies: **administrative** (the reporting line: company → division → department → team) and **functional** (by discipline, e.g. QA, Dev, Finance). Admins can create and change teams and divisions.
- Work can be assigned to a team or a manager. The manager delegates by creating child tasks and adding employees under them.
- **Behaviour is driven by settings, not code:** lookups with colours, fields, filters, approval chains, health rules and permissions. Default approval chain: functional lead first, then the accountable manager.
- Everything is audit-logged, and settings changes are versioned.
- Access is role-based: managers see their own unit and everything below it, and can filter to items they are accountable or responsible for and to their team's progress.
- Tools are deployed elsewhere and appear as links on each project, opened only by people with access. Passing project data to them may come later.
- The UI should be simple, professional and use calm colours. UI components and backend code should be reused, with backend and frontend kept in separate folders.

No code exists yet. The repo holds only the markdown docs.

---

## Folder structure

```text
Control Tower/
├── backend/
│   ├── app/
│   │   ├── __init__.py            # create_app() factory
│   │   ├── config.py              # Dev/Test/Prod config from .env
│   │   ├── extensions.py          # db, migrate, login_manager
│   │   ├── core/                  # shared code reused by every module
│   │   │   ├── models.py          # BaseModel: id, tenant_id, created/updated, version, soft delete
│   │   │   ├── command.py         # CommandService base: scope → permission → validate → save → audit
│   │   │   ├── audit.py           # audit_event model + writer
│   │   │   ├── scope.py           # unit-scoped query helper (closure table)
│   │   │   ├── permissions.py     # @require_permission, field-level checks
│   │   │   ├── errors.py          # one JSON error format
│   │   │   ├── pagination.py, filters.py   # generic list/filter/sort used by all list APIs
│   │   │   └── schemas.py         # shared Pydantic bases
│   │   └── modules/               # one folder per business area, same 4 files in each
│   │       ├── auth/  organisation/  people/  lookups/  config/
│   │       ├── work/  assignments/  workflows/  rules/
│   │       ├── views/  dashboards/  tools/  snapshots/
│   │       └── <module>/ models.py · schemas.py · service.py · routes.py
│   ├── migrations/                # Alembic
│   ├── seed/                      # demo org, default lookups, default approval chain
│   ├── tests/                     # unit/, service/, api/, permission/
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
├── frontend/
│   ├── index.html                 # login
│   ├── pages/                     # one HTML file per screen (home, work, item, team, admin/*)
│   ├── css/
│   │   ├── tokens.css             # colours, spacing, fonts as CSS variables (one place to restyle)
│   │   ├── base.css  layout.css  components.css
│   ├── js/
│   │   ├── core/   api.js (fetch wrapper) · auth.js · layout.js (sidebar/header) · lookups.js (cache + colour) · utils.js
│   │   ├── components/  data-table · modal · form-builder · filter-bar · tree · badge · toast ·
│   │   │                tabs · select · person-picker · progress-bar · kpi-card · empty-state
│   │   └── pages/       one JS file per page; builds screens only from the components above
│   └── assets/
└── docs/
    ├── BUILD_PLAN.md              # copy of this plan; tick phases off as they are done
    └── CONVENTIONS.md             # coding and UI rules (below)
```
Also add a project `CLAUDE.md` that points to both docs, so future sessions remember them.

**How the two halves connect:** Flask serves the `frontend/` folder as static files and all JSON under `/api/v1/...`, so there is one server to run. The frontend never builds HTML on the server; pages call the API.

## Reuse rules (CONVENTIONS.md)
- **Backend:** every module has the same layout: `models → schemas → service → routes`. Routes are thin: they parse input, call the service and return JSON, and never write to the database themselves. Every write goes through `CommandService`, which runs permission checks and writes the audit record in the same transaction. List endpoints all use the shared `filters.py` and `pagination.py`, so filtering behaves the same everywhere.
- **Frontend:** pages only put components together. One `data-table` handles every list (sorting, column chooser, filter bar, coloured lookup badges). One `form-builder` draws a form from field definitions, so custom fields show up automatically. All requests go through `api.js`.
- **Styling:** colours, spacing and fonts are defined once, as variables in `tokens.css`; components never contain fixed colour values. Status and priority colours come from the lookup settings.

## UI style
- Neutral base: background `#F5F7FA`, white cards, borders `#E2E8F0`, text `#1E293B`, secondary text `#64748B`.
- One accent colour, muted navy `#2F5D8A`. Red, amber, grey and green are used only for status, and their exact shades come from the lookup settings.
- System font stack, 14px base size, 8px spacing grid, light shadows, 6px corner radius.
- Layout: a left sidebar (My Home, Work, Team, Insights, Tools, Admin; admin items hidden by role), a top bar (search, user menu), and a content area with cards and tables. Works on narrow screens.

---

## Phases
Each phase is a complete working feature through every layer: database → service → permission → audit → API → screen → test. A phase is done only when its "Done when" checks pass.

### Phase 0 — Foundation
- Flask app factory, config loaded from `.env`, MySQL connection via SQLAlchemy 2 and PyMySQL, Alembic, pytest using a test MySQL database.
- In `core/`: BaseModel, CommandService, the audit_event table and writer, error handling, pagination and filters.
- Frontend shell: tokens.css, the layout component, api.js, toast, modal, data-table v1, and a login page.
- Sign-in with Flask-Login (sessions) and a seed admin user.

**Done when:** `python run.py` starts the server; the admin logs in and sees an empty home page; migrations run on an empty MySQL database; a test confirms that a failed write leaves no audit row.

### Phase 1 — Organisation, people and access
- **Administrative hierarchy:** a tree of units (company/division/department/team) stored with a closure table, and screens to create, move and rename units (including new teams).
- **Functional hierarchy:** a separate tree of functions with a functional lead for each.
- People: each person has one unit, one function and a reports-to manager.
- Roles and permissions: admin, executive, manager, functional lead, contributor and viewer. Permissions are stored as data and editable.
- A scope service that limits every query to the person's own unit and the units below it, plus items shared with or assigned to them.
- Reusable components: tree, person-picker. Admin screens: Organisation, Functions, People, Roles.

**Done when:** a manager sees only their branch; a contributor cannot open another branch through the API; every change appears in the audit log.

### Phase 2 — Lookups and settings
- Lookup manager covering status, priority, item type, functional role, health and so on. Each value has a label, **colour**, order and an active flag. Retired values stay visible on old records.
- Admin can rename terms (e.g. "Initiative" to "Programme").
- Item types and custom fields: field definitions stored in tables, values stored in MySQL JSON columns. Supported field types: text, number, date, select, multi-select, person and URL.
- Settings versioning: draft, publish and roll back.
- Frontend: `lookups.js` caches lookups and provides badge colours; form-builder draws forms from field definitions.

**Done when:** an admin adds a "Business Impact" select field with colours, and it appears in the form, the list filter and the API without a code change.

### Phase 3 — Work items, ownership and delegation
- Work items with parent and child items (Programme → Project → Milestone → Task), relationships between items, and dependencies.
- Exactly one accountable owner and at least one responsible owner. Child items inherit owners; overriding requires a reason; handovers are logged.
- **Assign to a team or a manager.** The manager then delegates by creating child tasks and adding employees with a role, allocation %, and start and end dates.
- Screens: Work list (data-table with filters), item page (tabs: details, children, people, approvals, history, tools), and My Work.

**Done when:** a company initiative is split down to a department, a team and an employee task, with owners inherited or overridden; a manager assigns three people with different roles; a contributor can edit only the fields they are allowed to.

### Phase 4 — Configurable approvals and validated progress
- A workflow designer: stages, allowed transitions, and **approval chains** per item type or team. For each step: the approver (role, person or owner), what happens if there is no approver (skip or block), and what is required (checklist, evidence, comment).
- Seeded default: **functional lead → accountable manager**.
- Rejection sends the item back with a note. Progress counts only after final approval.
- Progress engine: weighted approved milestones, with roll-up to parent items and to org units.
- Screens: Approvals inbox, approval panel on the item page, workflow admin.

**Done when:** a milestone marked complete goes to the functional lead, then the manager; approval raises the parent's progress; rejection returns the item; every decision is audited; changing the chain in admin changes the behaviour without code.

### Phase 5 — Health rules, saved filters and Action Centre
- Health rules stored as data and edited in admin (e.g. overdue by more than X days = Red, no owner = Grey). Priority order: Red > Amber > Grey > Green.
- Each result explains itself: the rule, the reason, the item that caused it, and a recommended action. Health rolls up to parent items.
- Saved filters and views: personal and shared, list and board.
- Action Centre: a ranked Top 5 per user, showing the scoring factors behind each rank.

**Done when:** an overdue high-priority milestone turns Red with a visible reason; the parent item shows which child caused it; Action Centre counts match the filtered list.

### Phase 6 — Personal home, team view and dashboards
- My Home, depending on role: Accountable for, Responsible for, My tasks, Awaiting my approval, and Upcoming deadlines.
- Team view for managers: members, workload and allocation, progress, and overdue items; drill-down from any number to the records behind it.
- Dashboard builder: widgets (KPI, table, status chart, progress, timeline) built on saved filters, using Chart.js, limited to the user's units.

**Done when:** a manager sees only their team's numbers; a dashboard KPI matches the list it drills into.

### Phase 7 — Tools registry
- Tool records: name, URL, description, icon, and which projects, teams or roles it applies to.
- Shown in the Tool Centre and on the item page's Tools tab. Opening a tool checks access and is logged.
- Built with a field ready for passing project data to the tool later.

**Done when:** a tool linked to a project is visible and opens only for permitted users.

### Phase 8 — Snapshots, exports and presentation
- Weekly and on-demand snapshots that store the figures as they were, not links to live data; a baseline; and trend charts.
- Export to Excel (openpyxl) and PDF; PowerPoint (python-pptx) optional.
- Presentation mode: dashboard pages shown full screen, using live data or a locked snapshot.

**Done when:** a review from earlier weeks reopens unchanged after data has been corrected since.

### Phase 9 — Import, backup and hardening
- Excel import with a preview and a report of invalid rows; imported rows are saved the same audited way as screen edits.
- Scheduled MySQL backups, a performance check against a large test data set, and a security review.
- Later: Microsoft Entra ID sign-in, Teams notifications, capacity planning and what-if scenarios.

---

## Verification (every phase)
- `pytest` passes: service, API and permission tests, including "a manager cannot see another branch" and "every write creates an audit row".
- Run `python run.py` and open the new screens in a browser, signed in as several seeded roles (admin, manager, functional lead, contributor).
- Mark the phase done in `docs/BUILD_PLAN.md`.


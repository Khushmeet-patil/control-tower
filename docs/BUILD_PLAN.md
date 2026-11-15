# Control Tower — Phased Build Plan

## Progress tracker
| Phase | Name | Status |
|---|---|---|
| 0 | Foundation | Done (local SQLite; MySQL schema in backend/database/schema_mysql.sql) |
| 1 | Organisation, people and access | Done |
| 2 | Lookups and settings | Done (custom fields wired to People; work items reuse them in Phase 3) |
| 3 | Work items, ownership and delegation | Done |
| 4 | Configurable approvals and validated progress | Done |
| 5 | Health rules, saved filters and Action Centre | Done |
| 6 | Personal home, team view and dashboards | Done |
| 7 | Tools registry | Not started |
| 8 | Snapshots, exports and presentation | Not started |
| 9 | Import, backup and hardening | Not started |

## Reference prototype
The manager's prototype (`reference/MY Control Tower 1.html`) is the **target for screens, look and business rules**. [MVP_ANALYSIS.md](MVP_ANALYSIS.md) lists every screen and rule, the prototype's defects, and which phase delivers each feature (§7). Each phase below also builds the prototype screens mapped to it, on real data.

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

**As built** (`app/modules/work`, tests in `tests/test_work.py`):
- One `work_items` tree (closure table) for every item type, including the prototype's Actions (decision, approval, blocker, commitment, action) with an action type and severity. Lookups added: category, action type, severity; statuses Ideation, Ongoing, Under validation; item type Action.
- Readable codes per type (PRJ-001, MS-004, ACT-002); deleted codes are never reused.
- Access per item: **manage** (unit managers with `work.manage`, the accountable owner of the item or any item above it, the responsible owner of an item above it), **contribute** (responsible owners and assignees: status, actual dates, progress, evidence and remarks only; responsible owners may also add child items), or **view**. Visibility: unit scope, led functions, and anything a person is named on, plus everything below it.
- Work moves down the hierarchy: a child goes to its parent's unit or one below it.
- Assignments: person, functional role, allocation %, dates and duties; `GET /assignments/load` gives today's total load per person (closed items and past assignments left out).
- Custom fields can be limited to item types; required fields apply only to those types.
- "Today" and "overdue" use the organisation's timezone (`TIMEZONE`, default Asia/Kolkata).
- Progress is interim (share of finished child items, or the manual % for a leaf); Phase 4 replaces it with validated, weighted progress.
- Screens: Portfolio (`work.html`), item workspace (`item.html`: Details, Work breakdown with timeline, People, History), My work, Schedule (timeline plus planned vs actual), real lists on My Home, and search plus "+ New" in the top bar. The Approvals and Tools tabs arrive with Phases 4 and 7.

### Phase 4 — Configurable approvals and validated progress
- A workflow designer: stages, allowed transitions, and **approval chains** per item type or team. For each step: the approver (role, person or owner), what happens if there is no approver (skip or block), and what is required (checklist, evidence, comment).
- Seeded default: **functional lead → accountable manager**.
- Rejection sends the item back with a note. Progress counts only after final approval.
- Progress engine: weighted approved milestones, with roll-up to parent items and to org units.
- Screens: Approvals inbox, approval panel on the item page, workflow admin.

**Done when:** a milestone marked complete goes to the functional lead, then the manager; approval raises the parent's progress; rejection returns the item; every decision is audited; changing the chain in admin changes the behaviour without code.

**As built** (`app/modules/workflows`, `app/modules/work/progress.py`, tests in `tests/test_workflows.py`):
- Approval chains and steps are settings: drafted in admin (Approval chains), used once published, versioned and rolled back with the other settings. The most specific chain wins (unit before organisation-wide, typed before untyped, then order). Work without a chain counts as finished at once.
- Step approvers: functional lead (the item's function, else the responsible owner's; walks up the function tree), accountable owner, unit head (walks up), anyone with a role, or a named person. When nobody fits: skip, or wait (an administrator may then decide, and item managers can "look for an approver again").
- Built-in rules: nobody approves their own work (their line manager does instead); someone who already approved is not asked twice; rejecting needs a note and returns the item to In progress; reopening a completed item cancels its approval; running requests keep the steps they started with.
- Seeded chain = the prototype's validation gate for milestones: functional lead review (evidence link required, two checks), then accountable owner validation (the prototype's four checks).
- "Mark complete" (`POST /work-items/<id>/complete`) is open to contributors; it sets Done and the finish date and starts approval in the same transaction.
- Progress engine: leaf = 100% only when done and approved (or no approval needed), else its manual %; parents = weighted average of children (new `weight` field), all the way up. `GET /work-items/rollup?unit_id=` gives a unit's progress and counts.
- Screens: Approvals inbox (waiting for me, submitted by me, my decisions, nobody to ask) with a count in the sidebar; review dialog with checklist; item page Approvals tab, status banner and "Mark complete"; Approvals on My Home; Approval chains admin.
- **Deferred:** allowed status transitions per item type ("stages and transitions"). Statuses remain free to change; approvals cover the "Done when" checks. Revisit with Phase 5 rules. In-app notifications beyond the sidebar count also wait for a later phase.

### Phase 5 — Health rules, saved filters and Action Centre
- Health rules stored as data and edited in admin (e.g. overdue by more than X days = Red, no owner = Grey). Priority order: Red > Amber > Grey > Green.
- Each result explains itself: the rule, the reason, the item that caused it, and a recommended action. Health rolls up to parent items.
- Saved filters and views: personal and shared, list and board.
- Action Centre: a ranked Top 5 per user, showing the scoring factors behind each rank.

**Done when:** an overdue high-priority milestone turns Red with a visible reason; the parent item shows which child caused it; Action Centre counts match the filtered list.

**As built** (`app/modules/rules`, `app/modules/views`, tests in `tests/test_rules.py`):
- Health rules are settings (drafted in admin, used once published). A rule = a condition type from `rules/catalog.py` (overdue, due soon not started, has status, open action, missing field, no child items, nothing planned next, owner overloaded, approval waiting, approval refused, not updated, nobody assigned) + data: thresholds, colour, item types, Action Centre score, recommended action (with {accountable}, {responsible}, {escalation}, {days}, {item}) and escalation owner (accountable, their manager, parent's accountable, unit head, awaited approver).
- The 17 seeded rules reproduce the prototype's `health()`, `dq()` and `top5()`. Kind "data_quality" raises flags without changing the colour.
- Health is calculated on read, never stored: Red > Amber > Grey > Green; Ideation, On hold, Done and Cancelled are not assessed (except Done work still waiting for approval); parents take their worst child's colour and name the item deep down that caused it. Items a viewer cannot open are not named.
- Health filter on `GET /work-items?health=red` (also `red,amber`, `na`), so Action Centre numbers and Portfolio lists always agree (tested for three roles).
- Action Centre (`GET /action-centre`): KPIs with the Portfolio filter behind each, Top 5 and "also needs me" with scoring factors (rule score + priority + days late or waiting; approvals waiting for you score 88), priority × health, spreads, next 14 days, data-quality flags.
- Saved views: personal, or shared with `views.share` (managers, executives); list or board layout. Seeded shared views bring back the prototype's Actions & Decisions screen (actions, open blockers, pending decisions), plus Red and amber work and a milestones board.
- Screens: Action Centre, Top 5 on My Home, health column and filter, board layout and saved views on Portfolio, "Why it has this health" on the item page, Health rules admin.
- **Deferred:** the prototype's Adoption tracker (Dev → Test → Accepted → Trained → Rollout → Adopted) moves to Phase 6 with the dashboards; drag-and-drop on the board is not built (cards open the item).

### Phase 6 — Personal home, team view and dashboards
- My Home, depending on role: Accountable for, Responsible for, My tasks, Awaiting my approval, and Upcoming deadlines.
- Team view for managers: members, workload and allocation, progress, and overdue items; drill-down from any number to the records behind it.
- Dashboard builder: widgets (KPI, table, status chart, progress, timeline) built on saved filters, using Chart.js, limited to the user's units.

**Done when:** a manager sees only their team's numbers; a dashboard KPI matches the list it drills into.

**As built** (`app/modules/dashboards`, tests in `tests/test_dashboards.py`):
- **One query for numbers and lists.** `WorkItemService.query()` builds the scoped, filtered select behind `GET /work-items`; `count()` and `rows()` reuse it. `portfolio_params()` turns Portfolio-style filters (`level`, `unit_id`…, as in its URL and in saved views) into list parameters, mirroring `toQuery()` in `work.js`. Every KPI on Team, Dashboards, Home and the Action Centre is counted from the exact filters its link opens, and `portfolioUrl()` always states the level. Tests check number = list total for several roles.
- New list filters: `involves=<person>` (accountable, responsible or assigned), `allocated_to=<person>` (assignments counted in today's load), `due_within=<days>`, plus `approval_status` and `actual_end` comparisons.
- **My Home:** KPIs (accountable, responsible, overdue, due in 14 days, awaiting approval), Top 5, my lists, approvals, upcoming deadlines; for managers a "My team" card with exceptions and the units below. For organisation-wide roles this is the executive roll-up by division.
- **Team view** (`GET /team?unit_id=`, `team.html`, nav "My team" for `work.manage`): only units the viewer manages (403 otherwise; contributors have none). People in the unit and below with load %, free %, Overloaded / Balanced / Underutilised (usable capacity = 100 − the published "owner overloaded" rule's buffer, so it matches the health rule), and drill-down counts. Load includes work the manager cannot open, shown as "+N you cannot open" so the list still matches. Units below with weighted progress, plus overdue work.
- **Dashboards** (`dashboards` table; `/dashboards`, `/dashboards/<id>/data`): personal, or shared with the new `dashboards.share` permission (managers and executives). Widgets: KPI, table, status chart (group by status, priority, health, type, category or accountable; bar or doughnut, Chart.js vendored at `frontend/assets/vendor`), progress, timeline, and my top actions. A widget uses a saved view (following its current filters, with a copy kept in case the view is deleted) or its own filters. Filters are checked against the list API on save. Data is calculated for the viewer, so a shared dashboard never shows more than they may see. Seeded shared dashboard: "Portfolio overview".
- **Action Centre additions** from the prototype: a progress board (worst health first, next item, next action), a watchlist, team capacity bars, technical completion vs adoption, and milestones completed per month (each bar opens its list).
- **Matched to the reference prototype** (`app/modules/dashboards/review.py`): the Action Centre follows the prototype's section order and content. That means its 7-tile KPI strip (top-level items with how many are in delivery, Red, overdue milestones, open blockers, pending decisions, awaiting my validation, data-quality flags); Top 5; the initiative progress board (category, next milestone with date and holder, next open action with owner, "⏳ N to validate"); **hold points** (Validate with Review, Blocker, Decision, Late milestone, Setup gap, in the prototype's urgency order); priority × health with the watchlist (signals plus stale updates); distributions by priority, status, category and health; team capacity with each person's open actions; technical completion vs adoption; **validated** milestones per month; upcoming milestones (14 days, with the item they belong to and the holder); blockers and pending decisions, with late rows tinted. My team uses the prototype's Team & Capacity columns: role and function, allocated, free, status, initiatives, open actions. New list filters `validated=1` and `responsible_id=<person>` keep these figures drillable. New signal rule `quick_win` (score 40): at least 80% done, and someone on the item or in its unit is underutilised.
- **Adoption tracker** (`adoption.html`, plus an Adoption section on the item page): the stages are a new lookup list `adoption_stage` (Development, Testing, Business acceptance, Users trained, Rolled out, Adoption achieved), stored as `work_items.adoption_stage_ids` with `adoption_evidence`. Item managers can change them, and every change is audited. New rule kind **signal** (ranks in Top 5 and the watchlist, never changes the colour) and condition `adoption_gap`. Seeded signals: "Ready for rollout" (50) and "Built, not adopted" (45). Missing built-in rules are now added on seed, which is safe because rules are never deleted.
- **Deferred:** to 6A: time-phased capacity, skills, time off, and capacity widgets. Templates (reusable item hierarchies, listed under Phase 6 in CAPABILITY_PHASE_MAP.md but not in this plan) are not built yet. Drag-and-drop widget layout is not built (widgets move left and right instead).

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


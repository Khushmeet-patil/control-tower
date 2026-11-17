# Control Tower — Capabilities, Modules and Phases

This file maps each Control Tower capability to the modules that deliver it and the build phase that delivers each part. It reads alongside [BUILD_PLAN.md](BUILD_PLAN.md), which sets the build order and the "Done when" checks.

- **Capabilities 1–11** are the confirmed list (from `Capability  Modules of Control Tower.txt`).
- **Capabilities 12–17** are additional requirements. They came out of `Ideation.md` and from gaps found while mapping 1–11.
- **Phase status** matches the tracker in BUILD_PLAN.md: every phase (0–10, with 6A) is done.

---

## 1. Phase overview

| Phase | Name | Status | Main modules (backend `app/modules/`) | Capabilities served |
|---|---|---|---|---|
| 0 | Foundation | Done | `core/` (BaseModel, CommandService, audit, errors, filters, pagination), `auth` | 1, 10 |
| 1 | Organisation, people and access | Done | `organisation`, `people`, `access`, `audit` | 3, 4, 11 |
| 2 | Lookups and settings | Done | `lookups`, `config` (terms, item types, custom fields, settings versions) | 9 |
| 3 | Work items, ownership and delegation | Done | `work`, `assignments` | 1, 2, 3 |
| 4 | Configurable approvals and validated progress | Done | `workflows`, progress engine in `rules` | 4, 5, 9 |
| 5 | Health rules, saved filters and Action Centre | Done | `rules`, `views` | 4, 5, 6, 9 |
| 6 | Personal home, team view and dashboards | Done | `dashboards`, `views`, home and team pages | 4, 6, 11 |
| 6A | Capacity and availability *(added)* | Done | `capacity` (new), extends `assignments` | 3, 4, 12 |
| 7 | Tool Centre | Done | `tools` | 8 |
| 8 | Snapshots, exports and presentation | Done | `snapshots`, `presentations` (new) | 7, 10 |
| 9 | Import, backup and hardening | Done | `imports` (new), backup jobs | 1, 14, 17 |
| 10 | Expansion | Done | `notifications`, `scenarios`, `integrations`, `templates` (new) | 13, 15, 16 (and templates from 6) |

---

## 2. Capability by capability

### Capability 1: Trusted source of organisational work
*All programmes, projects, milestones, tasks, requests, assignments, decisions and evidence live in one governed database. Every screen, import, dashboard, tool, API and presentation reads and writes through one service layer.*

| Part | Module | Phase |
|---|---|---|
| One database, BaseModel (tenant, version, soft delete) | `core/models.py` | 0 ✅ |
| One write path: scope → permission → validate → save → audit | `core/command.py` | 0 ✅ |
| Shared list, filter and pagination APIs | `core/filters.py`, `core/pagination.py` | 0 ✅ |
| Universal work item: programme, project, milestone, task, request, action | `work` | 3 |
| Decisions and evidence attached to items | `work` (decisions), `workflows` (evidence on gates) | 3 / 4 |
| Imports go through the same commands, never straight to tables | `imports` | 9 ✅ |
| Tools and presentations read the same records | `tools`, `presentations` | 7 / 8 |

### Capability 2: Clear accountable and responsible ownership
*Each item has exactly one accountable owner and at least one responsible owner. Contributors get functional roles, duties, allocation % and their own accountable milestones or tasks.*

| Part | Module | Phase |
|---|---|---|
| People, units and functions to assign from | `people`, `organisation` | 1 ✅ |
| Functional role lookup | `lookups` | 2 ✅ |
| Exactly one accountable owner and one or more responsible owners (enforced in the service) | `work` | 3 |
| Assignment record: person, role, duties, allocation %, start and end dates | `assignments` | 3 |
| Accountable owner on a single child milestone or task | `work` | 3 |
| Logged handover of ownership, with a reason | `work` + `audit` | 3 |

### Capability 3: Work distribution down the hierarchy and by availability
*Leaders create work at company, division or programme level and push it down to departments, teams and people. Managers split work into child items and assign by role, skill, current allocation, usable capacity and availability. Child items inherit ownership unless it is overridden.*

| Part | Module | Phase |
|---|---|---|
| Administrative and functional trees | `organisation` | 1 ✅ |
| Create work at any level; assign to a unit or a manager | `work` | 3 |
| Manager breaks work into child items and adds people | `work`, `assignments` | 3 |
| Child items inherit owners; an override needs a reason | `work` | 3 |
| Person picker shows current allocation % while assigning | `assignments` | 3 |
| **Skills on people, usable capacity, availability and time off** | `capacity` *(new)* | **6A** |
| **Assignment suggestions by role, skill and free capacity** | `capacity` | **6A** |

> **Gap closed:** BUILD_PLAN.md put capacity planning under "Later". Capability 3 needs assignment by skill and availability, so this file adds **Phase 6A** (see Capability 12).

### Capability 4: Progress and capacity roll-up upward
*Validated progress, health, overdue work, allocations and free capacity roll up from employee to team, department, division and executive level, with drill-down to the exact items and people behind each figure.*

| Part | Module | Phase |
|---|---|---|
| Closure tables for unit roll-ups | `organisation` | 1 ✅ |
| Weighted progress roll-up from approved milestones to parent items and units | `rules` (progress engine) | 4 |
| Health and overdue roll-up, showing which child caused it | `rules` | 5 |
| Team view: workload, allocation, progress, overdue | `dashboards` / team page | 6 |
| Drill-down from any number to its records | `views` | 6 |
| Capacity roll-up: used and free capacity by team, department and division | `capacity` | 6A |

### Capability 5: Validated, explainable progress
*A contributor can declare work complete, but configured milestones count toward progress only after gate checks and approval. Every Red, Amber, Grey or Green status shows the rule, source record, reason, recommended action and escalation owner.*

| Part | Module | Phase |
|---|---|---|
| Health lookup with colours | `lookups` | 2 ✅ |
| Workflow stages, transitions, gates (checklist, evidence, comment) | `workflows` | 4 |
| Approval chain; default is functional lead → accountable manager | `workflows` | 4 |
| Progress counts only after final approval; rejection returns the item with a note | `workflows`, `rules` | 4 |
| Health rules stored as data; priority Red > Amber > Grey > Green | `rules` | 5 |
| Each status explains itself: rule, source record, reason, recommended action, **escalation owner** | `rules` | 5 |
| Grey is never silently treated as Green | `rules` | 5 |

> **Added detail:** BUILD_PLAN.md Phase 5 did not list the **escalation owner**. It is added here so that every health result names who to escalate to.

### Capability 6: Configurable dashboards inside the platform
*Authorised users build dashboards from saved queries and reusable widgets (KPI, table, status chart, timeline, capacity chart, Action Centre list). Every widget uses governed data and supports filters, hierarchy scope and drill-down, with no separate reporting database.*

| Part | Module | Phase |
|---|---|---|
| Saved filters and views (personal and shared; list and board) | `views` | 5 |
| Action Centre: ranked Top 5 per user, with the scoring factors shown | `views` / `rules` | 5 |
| Dashboard builder: KPI, table, status chart, progress, timeline widgets on saved filters | `dashboards` | 6 |
| Widgets limited to the viewer's units; drill-down to the list | `dashboards` + `core/scope.py` | 6 |
| Capacity chart widget | `dashboards` + `capacity` | 6A |
| Timeline / Gantt and calendar views | `views` | 6 (basic), later (advanced) |

### Capability 7: Presentation mode using the same live data
*Dashboard pages arranged into a full-screen management review with notes, shown on live data or locked to an approved weekly snapshot, and exported to PowerPoint, PDF or Excel without copying numbers by hand.*

| Part | Module | Phase |
|---|---|---|
| Weekly and on-demand snapshots (stored figures, never live links); baseline; trend charts | `snapshots` | 8 ✅ |
| **Snapshot approval** before a presentation can lock to it | `snapshots` + `workflows` | 8 ✅ |
| Presentation: ordered dashboard pages + **speaker notes**, full screen | `presentations` *(new)* | 8 ✅ |
| Live mode or locked-to-snapshot mode | `presentations` | 8 ✅ |
| Export to Excel (openpyxl) and PDF | `snapshots` | 8 ✅ |
| **PowerPoint export (python-pptx)** | `presentations` | 8 ✅ |
| Published review packs that cannot change afterwards | `snapshots` | 8 ✅ |

> **Gaps closed:** BUILD_PLAN.md marked PowerPoint as optional and did not mention notes or approved snapshots. Capability 7 requires all three, so they are part of Phase 8.

### Capability 8: Tools for the same work, accessible from the platform
*Forms, checklists, calculators, readiness assessments, automations and approved plugins, found in a Tool Centre and on the relevant item page. Tools use platform permissions and commands, write back to the same records and create audit entries.*

| Part | Module | Phase |
|---|---|---|
| Tool registry: name, URL, description, icon; scope by project, team or role | `tools` | 7 ✅ |
| Tool Centre page and the Tools tab on the item page | `tools` | 7 ✅ |
| Opening a tool checks access and is audited | `tools` + `audit` | 7 ✅ |
| **Built-in tools: configurable forms, checklists, readiness assessments** that save to the work item through CommandService | `tools` (reuses form-builder and custom fields) | 7 ✅ |
| Field reserved for passing project data to external tools | `tools` | 7 ✅ |
| External tools writing back through a scoped API token | `integrations` | 10 |
| Calculators, automations, approved plugins | `tools` | 10 |

> **Gap closed:** BUILD_PLAN.md Phase 7 covered links only. Capability 8 needs tools that write back to records, so Phase 7 now includes built-in forms and checklists. External write-back waits for API tokens in Phase 10.

### Capability 9: No-code configuration
*PMO and admin users rename terms, maintain the organisation tree, define item types and fields, manage lookups, design workflows and gates, set health rules and thresholds, and build views, dashboards and templates, all without code. Configuration is versioned, audited and publishable.*

| Part | Module | Phase |
|---|---|---|
| Organisation designer (units, functions) | `organisation` | 1 ✅ |
| Roles and permissions stored as data | `access` | 1 ✅ |
| Lookup manager with colours | `lookups` | 2 ✅ |
| Rename terms | `config` | 2 ✅ |
| Item types and custom fields | `config` | 2 ✅ |
| Settings versioning: draft, publish, roll back | `config` | 2 ✅ |
| Workflow and gate designer | `workflows` | 4 |
| Rules studio: health rules and thresholds | `rules` | 5 |
| Shared views | `views` | 5 |
| Dashboard builder | `dashboards` | 6 |
| **Templates**: reusable item hierarchies, such as a standard project with its milestones | `work` (templates) | 6 |
| Tool manager | `tools` | 7 ✅ |

> **Added:** templates were in the capability but missing from BUILD_PLAN.md. They are placed in Phase 6, once item types, workflows and views exist.

### Capability 10: Complete change and decision traceability
*Every create, update, reassignment, handover, gate decision, import, tool action and scenario application records who, what, old and new values, when, reason, source and correlation ID. Snapshots and published review packs keep exactly what was reported.*

| Part | Module | Phase |
|---|---|---|
| Audit event: actor, time, entity, field, old/new value, reason, source, correlation ID | `core/audit.py` | 0 ✅ |
| Audit log screen | `audit` | 2 ✅ |
| Reassignment and handover events | `work`, `assignments` | 3 |
| Gate decisions | `workflows` | 4 |
| Tool actions | `tools` | 7 ✅ |
| Append-only snapshots and review packs | `snapshots` | 8 ✅ |
| Import events (source = `import`, one correlation ID per file) | `imports` | 9 ✅ |
| Scenario application (one correlation ID per scenario) | `scenarios` | 10 |

### Capability 11: RBAC and a personal dashboard for every login
*Access combines tenant, org unit, designation, platform role, assignment and field permissions. Each member gets a personal home: accountable for, responsible for, assigned work, pending approvals, upcoming deadlines, team exceptions. Executives see roll-ups, managers their unit and below, contributors their work, PMO/admin the configuration, viewers read-only.*

| Part | Module | Phase |
|---|---|---|
| Roles: admin, executive, manager, functional lead, contributor, viewer | `access` | 1 ✅ |
| Unit scope (own unit and descendants) | `core/scope.py` | 1 ✅ |
| Sidebar admin items hidden by role | frontend `layout.js` | 1 ✅ |
| Assignment-based access (see items you are assigned to) | `assignments` + `scope` | 3 |
| **Field-level permissions** (a contributor edits only allowed fields) | `core/permissions.py` + `work` | 3 |
| **Designation** (job title) as an access factor | `people` + `access` | 3 |
| Pending approvals widget | `workflows` | 4 |
| My Home by role: accountable for, responsible for, my tasks, awaiting approval, deadlines, team exceptions | home page + `dashboards` | 6 |
| Executive roll-up home | `dashboards` | 6 |

---

## 3. Additional requirements (12–17)

These are not in the confirmed list of 11. They are needed to deliver it fully, or they were in `Ideation.md` and are worth keeping in scope.

| # | Requirement | Why it is needed | Module | Phase |
|---|---|---|---|---|
| 12 | **Capacity and availability**: work calendars, skills on people, time off, time-phased allocation (e.g. 40% Jan–Mar), usable capacity after buffers, overloaded and underused thresholds | Capabilities 3 and 4 rely on "availability" and "usable capacity", which need their own data | `capacity` | 6A |
| 13 | **Notifications**: in-app first (new assignment, approval needed, item turned Red, deadline due), then email and Microsoft Teams | Approvals and escalations stall if people are not told about them | `notifications` | 10 ✅ (in-app, email, Teams) |
| 14 | **Excel import**: template, preview, invalid-row report, add-only and update modes, external ID mapping | Moving off spreadsheets is the platform's main purpose | `imports` | 9 ✅ |
| 15 | **What-if scenarios**: store only the proposed changes; on apply, recheck permissions and versions and audit under one correlation ID | Planning before committing changes | `scenarios` | 10 ✅ |
| 16 | **Integrations and API**: Microsoft Entra ID sign-in, Outlook calendar, webhooks, API tokens, read API for Power BI | Wider rollout, and tools that write back (capability 8) | `integrations` | 10 ✅ |
| 17 | **Data quality and hardening**: data-quality view (missing owners, stale updates), scheduled MySQL backup and restore, performance test on a large data set, security review | Trust in the "single source of truth" depends on it | `rules` (data quality), ops | 5 (data-quality rules), 9 (rest) ✅ |

---

## 4. Changes this file suggests to BUILD_PLAN.md

1. **Phase 3:** add field-level permissions, designation-based access and showing current allocation % in the person picker.
2. **Phase 4:** add in-app notifications for approvals.
3. **Phase 5:** add the escalation owner to each health result, plus data-quality rules.
4. **Phase 6:** add templates.
5. **New Phase 6A, Capacity and availability:** skills, calendars, time off, time-phased allocation, capacity roll-up and capacity widget.
6. **Phase 7:** add built-in forms, checklists and assessments that write back through CommandService.
7. **Phase 8:** PowerPoint export becomes required; add presentation notes and snapshot approval.
8. **Phase 10, Expansion:** scenarios, email and Teams notifications, Entra ID, webhooks and API tokens.

These are suggestions only. BUILD_PLAN.md has not been changed.

---

## 5. Module → phase index

| Module | Phase(s) |
|---|---|
| `core` (models, command, audit, scope, permissions, filters) | 0, extended in 3 |
| `auth` | 0 (Entra ID in 10) |
| `organisation` | 1 |
| `people` | 1 (skills in 6A) |
| `access` | 1 (field-level and designation in 3) |
| `audit` | 0–2 |
| `lookups` | 2 |
| `config` | 2 |
| `work` | 3 (templates in 6) |
| `assignments` | 3 (time-phased in 6A) |
| `workflows` | 4 |
| `rules` (progress, health, data quality) | 4–5 |
| `views` (saved filters, Action Centre) | 5 |
| `dashboards` | 6 |
| `capacity` *(new)* | 6A |
| `tools` | 7 |
| `snapshots` | 8 |
| `presentations` *(new)* | 8 |
| `imports` *(new)* | 9 |
| `notifications` *(new)* | 4 (in-app), 10 |
| `scenarios` *(new)* | 10 |
| `integrations` *(new)* | 10 |

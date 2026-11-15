# Reference MVP — Analysis

Source: `reference/MY Control Tower 1.html`, the manager's single-file prototype.
This file records what the prototype does, which parts are worth keeping, what is wrong with it, and where each feature lands in [BUILD_PLAN.md](BUILD_PLAN.md).

**In short:** keep the prototype's **screens, look and business rules**. Replace its **storage, identity, IDs and hard-coded lists** with the platform we are building: MySQL, the audited CommandService, RBAC, lookups and the settings stored as data.

---

## 1. What the prototype is

| Aspect | Prototype |
|---|---|
| Delivery | One HTML file, about 900 lines; inline CSS and JS; SheetJS from a CDN for Excel |
| Storage | Browser `localStorage` under key `ct_v1`. Nothing reaches a server, and the data is lost if browser data is cleared |
| Users | None. One implicit manager ("You"); no login, no roles, no scope |
| Rendering | Every change re-renders the whole page with `innerHTML` strings |
| Records | `init` (Initiatives), `team`, `ms` (Schedule / milestones), `demand`, `act` (Actions), `hist` (change log), `views`, `cfg` |

## 2. Screens

| # | Screen | What it does |
|---|---|---|
| 1 | **Action Centre** (home) | KPI strip · **Top 5 Actions for Me** (ranked, with why / next / owner / due) · initiative progress board (worst health first) · **Hold points – where I am needed** · priority × health matrix · watchlist · distributions by priority, status, category and health · team capacity bars · technical completion vs adoption · milestones completed per month · upcoming milestones (14 days) · blockers and pending decisions · data-quality flags |
| 2 | **Portfolio** | Initiative list with filters (text, priority, owner, category, status, health), sort, **saved views**, edit and delete |
| 2a | **Initiative workspace** | Header with health pill and reasons, next milestone, people and allocation, risks and dependencies, adoption checklist, schedule with Gantt, actions, change history |
| 3 | **Schedule** | Milestones for all initiatives or one, a simple Gantt with a "today" line, planned vs actual dates, evidence link, Complete and Validate buttons |
| 4 | **Validation Gate** | Milestones declared done and awaiting validation, with a 4-point checklist; validate, or reject with a required note; recent decisions |
| 5 | **Team & Capacity** | Per person: allocated %, free %, Overloaded / Balanced / Underutilised, initiatives, open actions, backlog; find people by skill |
| 6 | **What-if** | Sandbox of changes (priority, target, status, allocation, or a new initiative) → per-person load impact and warnings → apply all after confirmation |
| 7 | **Demand Intake** | Requests with urgency, priority and effort; **Assess & decide** shows free capacity, any shortfall and lower-priority work that could be deferred; Accept creates a draft initiative |
| 8 | **Actions & Decisions** | Decision, Approval, Blocker, Commitment, Action; severity; raised and due dates; age |
| 9 | **Adoption** | Per initiative: Dev → Test → Accepted → Trained → Rollout → Adopted; "Built, not adopted" flag |
| 10 | **Data & Backup** | Excel and CSV templates; import with preview, invalid-row report, add-only or update mode; export to xlsx, csv and json; backup and restore; settings for thresholds; change history |
| 11 | **User Manual** | Static help text |
| — | Header | Global search, Quick add, last-backup label and backup reminder banner |

## 3. Data captured

- **Initiative:** id, name, category, category lead, description, business objective, sponsor, priority, accountable owner, team allocation (`EMP-001:40, EMP-002:20`), planned start, target, status, manual progress %, remarks, key risks, dependencies, six adoption yes/no flags plus adoption evidence, last update.
- **Team member:** id, name, designation, role, skills, primary and secondary responsibilities, backlog (person-days).
- **Milestone:** initiative, name, planned start and finish, actual start and finish, status, action holder, dependencies, remarks, evidence link, validation gate (Pending / Validated / Rejected), validation date, validation note.
- **Request:** name, description, requester, sponsor, business value, urgency, priority, effort, requested date, dependencies, remarks, decision (New / Accepted / Rejected / Deferred / Clarification required).
- **Action:** initiative, type, title, owner, due date, status (Open / Done), severity (Minor / Critical), raised date, remarks.

## 4. Business rules (the part to keep)

Thresholds are set in `cfg`: **buffer 20%**, **stale after 14 days**, **escalate a blocker after 7 days**, **"soon" = 7 days**, **backup reminder 7 days**.

- **In delivery** = status is In progress, Enhancement, Blocked, Under Validation or Ongoing. Only these items count for health, load and the Top 5.
- **Progress** = validated milestones ÷ all milestones. If an initiative has no milestones, the manual % is used. A milestone a developer marks Done counts only **after validation**.
- **Load** (per person) = sum of their allocation % on initiatives in delivery. Usable capacity = 100 − buffer. A person is **Overloaded** above usable capacity and **Underutilised** below half of it.
- **Health** (Red > Amber > Grey > Green; Grey is never shown as Green):
  - **Red:** an overdue milestone on a Critical or High initiative · a Critical blocker, or one open longer than `blockerDays` · status Blocked · target date passed with progress below 100%.
  - **Amber:** an overdue milestone on a lower-priority initiative · a minor blocker · a milestone due within `soon` days that has not started · the owner is overloaded.
  - **Grey:** missing information, such as no owner, priority, target, milestones, open milestone, or next-milestone holder.
  - Every result lists its reasons, shown in a tooltip and on the workspace.
- **Data-quality flags:** no owner, priority, target or next milestone; last update older than `stale` days; a milestone with no holder; a blocker with no resolution owner.
- **Top 5 scoring:** Red initiative 80–104 (higher for high priority) · Critical or ageing blocker 90+ · milestones awaiting validation 88 · overdue decision or approval 85 · milestone due soon but not started or without a holder 70 · overloaded person 60 · ready for rollout 50 · rolled out but not adopted 45 · quick win (≥80% done and someone has spare capacity) 40.
- **Hold points:** items to validate, blockers, pending decisions, late milestones, new requests and setup gaps, ordered by urgency.
- **Validation gate:** four checks (reviewed the deliverable · checked tests and evidence · verified data and outputs · accept accountability). All four are required to validate; rejecting needs a note and sends the milestone back to In progress.
- **Demand assessment:** free capacity = Σ max(0, usable − load). If effort exceeds free capacity, it shows the shortfall and the lower-priority initiatives in delivery that could be deferred.
- **What-if warnings:** a milestone falls after the new target · pausing a High or Critical initiative · one owner ends up holding several items of the same priority · someone becomes overloaded · an unknown person ID.
- **Change log** tracks these fields: initiative priority, owner, target, start, status, team and category lead; milestone finish, status and gate; action status, owner and due date.
- **Import:** flexible dates (ISO, dd/mm with day first, `31-Dec-2026`, Excel serial numbers); headers matched by key or label; rows with IDs starting `EXAMPLE` are skipped; duplicates within the file are rejected; add-only mode never overwrites existing records.

## 5. Look and feel (to adopt)

Soft, raised ("neumorphic") cards on a cool grey background. In detail:
- Background `#eef1f5`, a light sidebar, and the active nav item as a raised white chip with blue text.
- One blue accent (`#2563eb`); 14px radius cards; KPI tiles with large numbers.
- Pill badges for status and health; thin horizontal bars for progress and distributions; late rows tinted red.
- Dense 13px tables.

The platform keeps its own component structure. Only the tokens and layout CSS change, so the whole look sits in `css/tokens.css`.

## 6. Problems in the prototype (what "proper" fixes)

| Problem | Effect | Platform fix |
|---|---|---|
| `localStorage` only | Data lives on one laptop; easy to lose; no sharing | MySQL, a single source of truth (Phase 0 ✅) |
| No users, no roles; everything is "You" | No accountability; anyone can validate their own work | Login, RBAC, unit scope (Phase 0–1 ✅); approval chain functional lead → manager (Phase 4) |
| Hard-coded lists (status, priority, category, action types, decisions) | Changing them means editing code | Lookups with colours (Phase 2 ✅) |
| **Bug:** a rejected milestone is set to `"In progress"`, but the allowed list is `"In Progress"` | Editing a rejected milestone shows a blank Status, and Save fails with "Status is required" until one is picked again | Statuses stored as lookup IDs, never labels |
| People referenced by ID **or** name (`nm()`); category lead stored as a name, owner as an ID | Renaming a person breaks links; lookups can return the wrong match | Integer foreign keys |
| Allocation stored as the text `"EMP-001:40,EMP-002:20"` | Cannot query it; no dates or roles; parsing errors | `assignments` table: person, role, %, start and end dates (Phase 3) |
| Load ignores dates | Future and past allocations count as current | Time-phased allocation (Phase 6A) |
| Some values not escaped (`a.id`, `p.id`, `a.type`, `x.m`…) | An imported ID containing HTML runs as script (stored XSS) | `el()` and `textContent` only (CONVENTIONS) |
| What-if apply and backup restore skip validation | Bad data can enter the live portfolio | Every write goes through CommandService validation |
| Change log capped at 2,000 entries; no reasons; no actor | History is lost; you cannot see who changed what | Append-only `audit_event` with actor, reason, source and correlation ID (✅) |
| `TODAY()` uses the UTC date | In India before 05:30 it is "yesterday", so overdue checks are off by a day | Dates computed on the server in the tenant's timezone |
| Progress is unweighted; no roll-up above an initiative | A large and a small milestone count the same; no division or company view | Weighted progress with roll-up to parent items and units (Phase 4) |
| Deleting an initiative silently deletes its milestones and actions | Irreversible loss | Soft delete with audit |
| No concurrency control | Two people editing overwrite each other (once shared) | `version` column with expected-version checks (✅) |
| Thresholds edited without history | Nobody knows why health changed | Rule parameters versioned in settings (Phase 5) |
| `alert`, `confirm` and `prompt` dialogs | Clumsy; cannot be styled | Modal, toast and form-builder components (✅) |

## 7. Where each feature lands

| Prototype feature | Platform concept | Phase |
|---|---|---|
| Initiative | Work item of type **Initiative** (rename via Terminology); category becomes a lookup | 3 |
| Category lead | Person field on the item (or the functional lead of the category's function) | 3 |
| Accountable owner / action holder | Accountable owner / responsible owner | 3 |
| Team allocation | Assignment records (person, role, %, dates) | 3 (dates used in 6A) |
| Milestones (planned and actual dates, evidence link, dependencies) | Child work items of type Milestone | 3 |
| Actions: Decision, Approval, Blocker, Commitment, Action; severity | Work items of type Action, with `action_type` and `severity` lookups | 3 |
| Initiative workspace (header, people, risks, schedule, actions, history) | Item page tabs: Details, Children, People, Actions, History | 3 |
| Simple Gantt | Timeline component on the item page and the Schedule screen | 3 (basic), 6 |
| Quick add and global search | Top-bar Quick add and search over permitted records | 3 |
| Validation Gate with 4-point checklist and rejection note | Approval chain with a checklist gate; seeded with these 4 checks | 4 |
| Progress = validated milestones | Progress engine (weighted, rolls up) | 4 |
| Health rules, reasons, thresholds | Rules engine; the prototype's rules are seeded as the default rule set | 5 |
| Data-quality flags | Data-quality rules | 5 |
| Top 5 Actions with scoring | Action Centre per user; the prototype's scores are the default weights | 5 |
| Saved views | Saved filters (personal and shared) | 5 |
| Action Centre KPIs, board, hold points, matrix, watchlist, distributions, monthly completions, upcoming | My Home and dashboard widgets, scoped to the user's units | 6 |
| Team & Capacity (buffer, load, Overloaded/Underutilised, skills, backlog) | Capacity module | 6 (basic load) → 6A |
| Adoption pipeline (6 stages and evidence) | Configurable stage checklist on Initiatives; "ready for rollout" and "built, not adopted" rules | 5 |
| Demand Intake and Assess & decide | Item type Request with a decision workflow; capacity impact check; Accept creates an Initiative | 4 (workflow), 6A (capacity impact) |
| Export xlsx, csv, json | Exports | 8 |
| Templates, import preview, add-only and update modes, flexible dates | Import module, through CommandService | 9 |
| Backup and restore, backup banner | Scheduled MySQL backups (not needed in the browser) | 9 |
| What-if scenarios | Scenarios module | 10 |
| User manual | Help page | 9 |

## 8. Recommended build order

Follow BUILD_PLAN.md, and use the prototype as the target screen for each phase:

1. **Restyle** the shell and components to the prototype's look (tokens and layout only).
2. **Phase 3:** Initiatives, milestones and actions as work items; assignments; Portfolio list; Initiative workspace; Schedule with a basic Gantt; Quick add.
3. **Phase 4:** Validation Gate (approval chain plus the 4-point checklist); validated progress.
4. **Phase 5:** health, data-quality and Top 5 rules (the prototype's rules as seed data); saved views; adoption checklist.
5. **Phase 6 / 6A:** Action Centre home with all the prototype's widgets; Team & Capacity; Demand Intake assessment.
6. **Phases 8–10:** export, import, what-if.

When Phase 6 is done, every screen in the prototype except What-if and Import exists, working on shared, audited, permissioned data.

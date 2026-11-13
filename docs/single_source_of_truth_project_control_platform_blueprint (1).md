# Redesigned Build Blueprint: Single-Source-of-Truth Project Control Platform

Your current blueprint has the right vision, especially around hierarchy, accountability, validation, explainable health, capacity, dashboards, and configurable workflows. The main problem is sequencing: the plan builds a large generic data model first, while dashboards, presentations, tools, snapshots, and real operational testing arrive too late.

The redesigned plan below makes the platform usable much earlier and ensures that **every screen, dashboard, tool, export, snapshot, and presentation uses the same trusted data and calculation services**.

---

# 1. Final product definition

The platform should be an **organisation-wide control system**, not just a project-tracking application.

Its purpose is to provide the following core capabilities. The original list contained ten capabilities; role-based access and personalised dashboards are included below as an additional eleventh capability because they affect every member's experience.

| # | Capability | How it will work |
|---:|---|---|
| 1 | **One trusted source of organisational work** | All programmes, projects, milestones, tasks, requests, assignments, decisions and evidence will be stored in one governed database. Screens, imports, dashboards, tools, APIs and presentations will read from and update the same records through one controlled service layer, preventing conflicting spreadsheet or screen-level copies. |
| 2 | **Clear accountable and responsible ownership** | Every managed work item will have exactly one accountable owner who answers for the outcome and at least one responsible owner who leads delivery. Contributors can also be assigned functional roles, duties, allocation percentages and individually accountable milestones or tasks. |
| 3 | **Work distribution down the hierarchy and as per availability** | Senior leaders can create work at company, division or programme level and distribute it to departments, teams and employees. Managers can break parent work into child items and assign it using role, skill, current allocation, usable capacity and availability, while ownership is inherited unless deliberately overridden. |
| 4 | **Progress and capacity roll-up upward** | Validated milestone progress, health, overdue work, employee allocations and available capacity will aggregate from employee to team, department, division and executive levels. Leaders can drill down from a rolled-up figure to the exact child items and people contributing to it. |
| 5 | **Validated, explainable progress** | A contributor or responsible owner can declare work complete, but configured milestones count toward progress only after the required gate checks and approval. Every Red, Amber, Grey or Green result will show the rule, source record, reason, recommended action and escalation owner so users can understand and trust the result. |
| 6 | **Configurable dashboards inside the platform** | Authorised users can create dashboards from saved queries and reusable widgets such as KPIs, tables, status charts, timelines, capacity charts and Action Centre lists. Each widget uses the same governed data and supports filters, hierarchy scope and drill-down without creating a separate reporting database. |
| 7 | **Presentation mode using the same live data** | Dashboard pages can be arranged into a full-screen management review with notes. The presenter can use current live data or lock the presentation to an approved weekly snapshot, then export the same results to PowerPoint, PDF or Excel without manually copying numbers. |
| 8 | **Tools for the same work, easily accessible from the platform** | Forms, checklists, calculators, readiness assessments, automations and approved plugins will be available through a central Tool Centre and may also appear inside the relevant work-item page. Tools will use platform permissions and commands, write back to the same source records, and create audit entries instead of maintaining separate data copies. |
| 9 | **No-code configuration** | PMO or administrator users can rename terms, maintain the organisation tree, define item types and fields, manage lookups, design workflows and gates, configure health rules and thresholds, and build reusable views, dashboards and templates without changing Python or JavaScript code. Configuration will be versioned, audited and publishable. |
| 10 | **Complete change and decision traceability** | Every material create, update, reassignment, handover, gate decision, import, tool action and scenario application will record who acted, what changed, previous and new values, date and time, reason, source and correlation ID. Historical snapshots and published review packs preserve exactly what was reported at that time. |
| 11 | **RBAC and a custom dashboard for every member login** | Role-based access control will combine tenant, organisation unit, designation, platform role, assignment and field permissions. After login, each member receives a personalised home dashboard showing only authorised information, such as “I am accountable for,” “I am responsible for,” “My assigned work,” pending approvals, upcoming deadlines and team exceptions. Executives see organisation roll-ups, managers see their unit and descendants, contributors see assigned work, PMO/Admin users see configuration controls, and viewers receive read-only access. |

The platform should support this flow:

```text
Organisation Strategy
        ↓
Portfolio / Programme
        ↓
Project / Initiative
        ↓
Workstream
        ↓
Milestone / Deliverable
        ↓
Task / Action
        ↓
Employee Assignment
```

Information moves in both directions:

```text
Assignments and updates move downward
Progress, health and capacity roll upward
```

---

# 2. Corrected core model

The platform should use **six platform primitives**, not five.

| Primitive | Purpose | Examples |
|---|---|---|
| Organisation unit | Represents organisational hierarchy | Company, division, department, team |
| Person | Represents users, capacity and membership | Executive, manager, contributor |
| Work item | Represents every unit of managed work | Portfolio, project, milestone, task, request |
| Assignment | Connects people to work | Owner, contributor, tester, approver |
| Workflow | Controls lifecycle and validation | Intake, delivery, testing, approval, adoption |
| Rule | Calculates status or generates attention | Health, escalation, data quality, Top 5 |

**Assignment must remain a separate primitive.** It should not be hidden inside Person or Work Item because it contains operational information such as:

- Functional role
- Allocation percentage
- Reports-to person
- Start and end dates
- Responsibility
- Accountable child items
- Assignment status
- Capacity contribution

Views, dashboards, presentations and tools are not business primitives. They are configuration layers over these six primitives.

---

# 3. What “one source of truth” should mean

A single source of truth does not mean storing everything in one database table. It means that every fact has **one authoritative location and one authorised write path**.

## 3.1 Four categories of platform data

### A. Authoritative facts

Entered or approved by users.

Examples:

- Work-item name
- Target date
- Accountable owner
- Responsible owner
- Assignment allocation
- Milestone status
- Gate approval
- Adoption evidence

These are the original business facts.

### B. Configuration

Defines how the platform behaves.

Examples:

- Organisation terminology
- Item types
- Custom fields
- Workflow stages
- Gate definitions
- Health rules
- Capacity thresholds
- Dashboard definitions
- Tool permissions

### C. Derived information

Calculated from authoritative facts and configuration.

Examples:

- Progress percentage
- Health status
- Capacity utilisation
- Overdue status
- Portfolio roll-up
- Top 5 actions
- Critical-path status

A user must not manually enter these values unless the configured calculation mode explicitly allows manual entry.

### D. Historical evidence

Preserves what was true at a point in time.

Examples:

- Audit events
- Approval decisions
- Weekly snapshots
- Published review packs
- Configuration versions
- Ownership handovers

---

## 3.2 One-write-path architecture

Every data change must follow the same sequence:

```text
Screen / Import / API / Integration / Tool
                    ↓
              Command service
                    ↓
          Authentication and scope
                    ↓
             Permission check
                    ↓
              Business validation
                    ↓
             Database transaction
                    ↓
       Audit record + outbox event
                    ↓
       Derived values and notification
```

No Flask route, plugin, import script or administration page should write directly to a SQLAlchemy model.

A standard operation should look conceptually like:

```python
work_item_service.update(
    actor=current_user,
    item_id=item_id,
    changes=payload,
    reason="Target date revised following steering review"
)
```

The service must:

1. Check tenant
2. Check organisation-unit scope
3. Check role and field permission
4. Validate the change
5. Apply ownership and workflow rules
6. Save the authoritative change
7. Write an audit event
8. Write an outbox event
9. Commit everything in one database transaction

---

# 4. Proposed platform architecture

```text
Browser
  |
  |-- Workspaces
  |-- Dashboards
  |-- Presentation mode
  |-- Admin Studio
  |-- Tool Centre
  |
JSON API / Command API
  |
Application Services
  |
  |-- Work service
  |-- Organisation service
  |-- Assignment service
  |-- Workflow service
  |-- Dashboard service
  |-- Tool service
  |-- Import service
  |
Domain Engines
  |
  |-- Progress engine
  |-- Health engine
  |-- Roll-up engine
  |-- Capacity engine
  |-- Attention engine
  |-- Scenario engine
  |
PostgreSQL
  |
  |-- Authoritative records
  |-- Configuration
  |-- Audit events
  |-- Outbox events
  |-- Snapshots
  |-- Published presentations
```

## Recommended technology

| Layer | Recommended choice |
|---|---|
| Backend | Python Flask application factory |
| ORM | SQLAlchemy 2.x |
| Database | PostgreSQL production, SQLite only for local development |
| Migrations | Alembic |
| Validation | Pydantic |
| Authentication | Flask-Login initially, Microsoft Entra ID later |
| Background processing | APScheduler initially; Celery with Redis when workload requires it |
| Frontend | HTML, CSS, JavaScript ES modules |
| Templates | Jinja only for application shell and initial page bootstrapping |
| Charts | Chart.js |
| Gantt | SVG or a vendored lightweight JavaScript component |
| Excel | openpyxl |
| PowerPoint | python-pptx |
| PDF | WeasyPrint |
| Tests | pytest, Playwright smoke tests |
| Production server | Gunicorn on Linux; Waitress if the production target must remain Windows |
| CI/CD | Azure DevOps Pipelines or GitHub Actions |

If hosting on a long-running Windows VM without administrator rights, **Waitress plus Task Scheduler or NSSM where permitted** is more practical than Gunicorn, because Gunicorn does not run natively on Windows.

---

# 5. Revised product structure

The user interface should not be divided into many hard-coded modules. Use five stable areas and produce specialised views inside them.

## 5.1 My Control Centre

The user’s weekly and daily attention area.

Contains:

- My Top 5
- Awaiting my approval
- I am accountable for
- I am responsible for
- My assigned work
- My functional tasks
- Red and ageing items
- Upcoming commitments
- My team’s capacity exceptions

## 5.2 Work

The universal work-management area.

Contains:

- Portfolio view
- List view
- Board view
- Timeline/Gantt
- Calendar
- Hierarchy view
- Milestone view
- Action and decision view
- Demand or intake view

These are saved views over the same Work Item records.

## 5.3 Insights

Contains:

- Organisation dashboards
- Progress trends
- Capacity and demand
- Adoption
- Risk and issue reporting
- Data quality
- Presentation mode
- Published review packs

## 5.4 Tools

Contains:

- Configurable forms
- Checklists
- Calculators
- Surveys or assessments
- Automations
- Approved plugin tools
- Tool catalogue

## 5.5 Administration

Contains:

- Organisation Designer
- Role and permission management
- Item Type Designer
- Field Designer
- Lookup Manager
- Workflow Designer
- Rules Studio
- Dashboard Builder
- Tool Manager
- Templates
- Import and backup
- Audit explorer

---

# 6. Redesigned build strategy

Do not build all tables first and all screens afterward. Build the platform as **thin, complete vertical slices**.

Each increment should include:

```text
Database → service → permission → audit → API → screen → test
```

A feature is not finished merely because a database table exists.

---

# 7. Redesigned 12-increment build plan

## Release 0: Product and architecture foundation

### Increment 1: Platform kernel

**Build**

- Repository structure
- Flask application factory
- Development and production configuration
- SQLAlchemy and Alembic
- Pydantic request validation
- pytest
- Seed system
- Error handling
- Structured logging
- Health endpoint
- Basic HTML application shell
- CI pipeline

**Important decision**

Create one database session and transaction boundary for each command.

**Done when**

- Application starts from one command
- Empty PostgreSQL database can be migrated
- Seed data loads
- Test database is created automatically
- One API endpoint and one HTML page work
- CI runs migration and tests

**Target duration:** 1 to 2 weeks.

---

## Release 1: Trusted work foundation

### Increment 2: Organisation, users and scoped security

**Build**

- Tenant
- Organisation-unit tree
- Person
- Unit membership
- Role
- Permission
- Unit-scoped query service
- Sign-in
- Active tenant and unit context
- Soft deletion
- Record versioning

**Scope rule**

A user can see:

- Their unit
- Descendant units
- Items explicitly shared with them
- Items assigned to them
- Additional scope granted through a role

**Done when**

- Company → division → department → team can be created
- Manager can see descendants
- Contributor cannot see a separate organisation branch
- Executive can see the full authorised hierarchy
- Every API query uses the scope service
- Cross-tenant access tests fail safely

**Target duration:** 2 weeks.

---

### Increment 3: Universal Work Item and ownership

**Build**

- Work Item
- Work Item Type
- Parent-child relationships
- Accountable owner
- One or more responsible owners
- Work-item sharing
- Basic fields
- Work-item status
- Universal item workspace
- List view
- Personal ownership views

**Critical rules**

- Exactly one accountable owner for active managed work
- At least one responsible owner
- Accountable owner cannot be hierarchically below the responsible owner without an approved exception
- Child items inherit ownership by default
- Ownership override requires a reason
- Handover records old owner, new owner, date, actor and reason

**Done when**

A company-level initiative can be split into:

```text
Initiative
  └── Department workstream
       └── Team milestone
            └── Employee action
```

Each level can have inherited or overridden owners.

**Target duration:** 2 to 3 weeks.

---

### Increment 4: Assignments and functional responsibility

**Build**

- Assignment record
- Functional role
- Functional duties
- Allocation percentage
- Reports-to relationship
- Assignment dates
- Personal accountable items
- Contributor update screen
- “My Work” page
- Manager assignment screen

**Done when**

- A responsible owner assigns three people to a project
- Each person has a different functional role
- One employee is accountable for a particular milestone
- Allocation contributes to the employee’s capacity
- Contributor can update only assigned records and permitted fields

**Target duration:** 2 weeks.

---

### Increment 5: One write path, audit and event infrastructure

The earlier build plan introduced the write path before meaningful features. In the revised plan, basic service patterns begin in Increment 1, but this increment formalises and enforces them across the application.

**Build**

- Command service base
- Audit event table
- Outbox event table
- Field-change history
- Reason-for-change support
- Optimistic concurrency control
- Background event consumer
- Audit Explorer
- Automated architectural test preventing direct route writes

**Every audit record should include**

- Tenant
- Actor
- Date and time
- Entity type
- Entity ID
- Operation
- Field
- Previous value
- New value
- Reason
- Source: screen, import, API, integration or tool
- Correlation ID

**Done when**

- Every create, update, approval and deletion generates audit and outbox entries
- Failed transactions generate neither
- Concurrent edits produce a safe conflict message
- A test detects direct SQLAlchemy writes inside route files

**Target duration:** 1 to 2 weeks.

---

## Release 2: Plan, deliver and validate

### Increment 6: Configurable fields, terms and lookups

**Build**

- Terminology settings
- Lookup definitions
- Lookup values
- Item-type definitions
- Custom field definitions
- Field packs
- Formula fields
- Unit-level extension rules
- Configuration versions
- Draft and publish process for configuration changes

**Supported custom-field types**

- Text
- Rich text
- Number
- Currency
- Percentage
- Date
- Date and time
- Boolean
- Single select
- Multi-select
- Person reference
- Unit reference
- Work-item reference
- URL
- Formula

**Important recommendation**

Do not place all custom data in one ungoverned JSON object. Use:

- Standard relational columns for core fields
- JSONB for configurable field values
- Field-definition tables for schema
- Validation and indexing services
- Optional generated indexes for frequently filtered custom fields

**Done when**

- “Initiative” can be renamed “Programme”
- Admin creates a “Business Impact” field without code
- The field appears in form, list filter, API and export
- Retired lookup values remain visible on historical records
- Configuration can be rolled back

**Target duration:** 2 to 3 weeks.

---

### Increment 7: Workflow, gates and validated progress

**Build**

- Workflow definition
- Workflow stages
- Allowed transitions
- Gate definitions
- Gate checklist
- Approver rules
- Rejection and return
- Evidence attachment or evidence link
- Milestone achievement conditions
- Progress calculation modes

**Progress calculation options**

1. Validated milestone count
2. Weighted validated milestones
3. Child-item roll-up
4. Manual progress with approval
5. Formula based on configured fields

**Recommended default**

```text
Progress =
Sum of weights of validated milestones
÷
Sum of weights of all applicable milestones
```

A milestone marked complete by a contributor should not affect progress until validation.

**Done when**

- Responsible owner declares a milestone complete
- Accountable owner validates or rejects it
- Validation changes progress
- Rejection returns the milestone with a note
- Decision is recorded in the audit and approval log
- Parent progress updates through an event

**Target duration:** 2 to 3 weeks.

---

### Increment 8: Rules, health and roll-up engine

**Build**

- Visual rule definitions stored as data
- Rule conditions
- Rule results
- Rule priority
- Explanation template
- Health calculation
- Parent-child roll-ups
- Data-quality rules
- Attention ranking
- Rule execution history

**Health precedence**

```text
Red > Amber > Grey > Green
```

However, missing critical information should remain Grey unless another genuine condition makes the item Red or Amber.

**Each health result should contain**

```json
{
  "status": "Red",
  "rule_code": "MILESTONE_OVERDUE_HIGH_PRIORITY",
  "reason": "Testing milestone is 8 days overdue",
  "source_item_id": "MS-0042",
  "evaluated_at": "2026-11-12T08:00:00Z",
  "recommended_action": "Confirm a recovery date",
  "escalation_owner": "accountable_owner"
}
```

**Done when**

- No owner produces Grey
- High-priority overdue milestone produces Red
- Status visibly explains why it is Red
- Parent health identifies the child generating the issue
- A source change triggers recalculation
- Each rule has automated examples

**Target duration:** 3 weeks.

---

## Release 3: See, control and present

### Increment 9: Saved views and Action Centre

**Build**

- Saved-query model
- Filter builder
- Column selection
- Sort and group
- List view
- Board view
- Calendar view
- Basic timeline
- Personal and shared views
- Action Centre
- Top N ranking
- Escalation queue

**Action ranking formula**

Start with a transparent scoring model:

```text
Attention score =
Severity weight
+ Priority weight
+ Age weight
+ Due-date weight
+ Hierarchy impact
+ Capacity impact
+ Gate importance
```

Example:

| Factor | Example points |
|---|---:|
| Red health | 100 |
| Critical priority | 40 |
| High priority | 25 |
| Overdue more than 14 days | 25 |
| Blocks three child items | 20 |
| Awaiting accountable-owner approval | 15 |
| Missing responsible owner | 15 |

The interface should display both the score factors and the human-readable reason.

**Done when**

- Manager builds and saves a view without development
- Action Centre numbers equal the corresponding filtered list
- Top 5 can be traced to source records and rules
- Different management levels receive different Top 5 results

**Target duration:** 2 to 3 weeks.

---

### Increment 10: Dashboard Builder

**Build**

- Dashboard definition
- Dashboard pages
- Widget instances
- Saved-query binding
- Unit scope
- Filters
- Date context
- Widget registry
- Drill-down
- Sharing
- Dashboard permissions
- Dashboard templates

**Initial widget library**

- KPI
- Table
- Status distribution
- Progress bar
- Trend chart
- Milestone timeline
- Capacity chart
- Health matrix
- Action list
- Data-quality list
- Adoption funnel
- Organisation roll-up

A widget must reference:

```text
saved_query_id
visualisation_type
field_mapping
scope
date_context
display_options
```

It must not contain its own duplicate project data.

**Done when**

- Manager creates a dashboard without code
- Dashboard KPI drills into the exact records
- Dashboard is unit-scoped
- Dashboard and list view return the same number
- Dashboard configuration is versioned and audited

**Target duration:** 2 to 3 weeks.

---

### Increment 11: Snapshots, baselines and progress history

**Build**

- On-demand snapshot
- Weekly scheduled snapshot
- Baseline
- Snapshot facts
- “As at” controls
- Variance
- Trend
- Published review period
- Snapshot retention rules

**Snapshot principle**

Snapshots should keep the result that was presented, not merely pointers to current data.

A snapshot should include:

- Query definition version
- Configuration version
- Rule version
- Effective scope
- Derived values
- Record references
- Snapshot time
- Person who created or published it

**Done when**

- A review from six weeks ago reopens exactly
- Current corrections do not alter the historical pack
- Trend charts use saved snapshot values
- Users can compare baseline, previous snapshot and current position

**Target duration:** 2 weeks.

---

### Increment 12: Presentation mode and controlled extensions

This increment combines presentation and the initial tool framework because both should consume the same dashboard and API contracts.

#### A. Presentation mode

**Build**

- Presentation definition
- Ordered dashboard pages
- Speaker notes
- Full-screen mode
- Live or snapshot mode
- PDF export
- PowerPoint export
- Excel supporting-data export
- Publish and lock
- Shared review link

A presentation page should store a reference to the dashboard page, not copied numbers.

#### B. Tool framework

**Build**

- Tool manifest
- Tool catalogue
- Tool permissions
- Tool enablement per unit
- Tool input and output contracts
- Tool API token
- Widget registration
- Tool event subscription
- Tool execution log

Example manifest:

```json
{
  "code": "project_readiness_check",
  "name": "Project Readiness Check",
  "version": "1.0.0",
  "reads": [
    "work_item.name",
    "work_item.target_date",
    "assignment.functional_role"
  ],
  "writes": [
    "custom.readiness_score",
    "custom.readiness_comment"
  ],
  "commands": [
    "work_item.update_custom_fields"
  ],
  "widgets": [
    "readiness_summary"
  ],
  "allowed_item_types": [
    "project"
  ]
}
```

A tool must never receive direct database access.

**Done when**

- A review pack is generated from live or snapshot data
- Every number matches its dashboard
- A sample checklist tool is enabled for one department
- Tool updates pass through the command service
- Tool changes appear in the audit log
- Removing the tool leaves shared records intact

**Target duration:** 3 to 4 weeks.

---

# 8. Later expansion releases

After the 12 increments, add the following as controlled expansions.

## Expansion A: Capacity and demand

- Work calendars
- Usable capacity
- Buffers
- Person allocation
- Unit capacity
- Role demand
- Skill demand
- Demand assessment
- Overloaded and underused thresholds
- Time-phased capacity

Allocation should eventually be time-phased:

```text
Person 101
Project A: 40% from January to March
Project B: 30% from February to May
Operational buffer: 20%
Usable remaining capacity in February: 10%
```

A single permanent percentage is insufficient for real planning.

---

## Expansion B: Scenarios

Scenarios should not copy the full live database.

Store only proposed changes:

```text
Scenario
  ├── Change: Project A target 30 Jun → 31 Aug
  ├── Change: Person X allocation 30% → 50%
  ├── Change: Project B priority High → Medium
  └── New draft demand
```

At evaluation time:

```text
Scenario result = Live data + proposed changes
```

Applying the scenario:

1. Revalidates permissions
2. Rechecks current versions
3. Detects conflicts
4. Shows final diff
5. Applies changes through the command service
6. Audits each change under one scenario correlation ID

---

## Expansion C: Import, integrations and API

- Excel template import
- Preview
- Invalid-row report
- Add-only mode
- Update mode
- External ID mapping
- JSON backup
- Restore
- Microsoft Teams notifications
- Microsoft Outlook calendar integration
- Microsoft Entra ID
- Webhooks
- API tokens
- Power BI read API if required

Imports must create normal service commands. They must not bypass validation.

---

# 9. Key database entities

A practical starting entity model is:

## Identity and structure

- `tenant`
- `org_unit`
- `org_unit_closure`
- `person`
- `unit_membership`
- `role`
- `permission`
- `role_permission`
- `person_role`
- `record_share`

Use an **organisation closure table** for efficient descendant access and roll-ups across deep hierarchies.

## Work management

- `work_item`
- `work_item_type`
- `work_item_relation`
- `work_item_owner`
- `assignment`
- `dependency`
- `attachment`
- `comment`

`work_item_relation` supports relationships such as:

- Parent-child
- Blocks
- Depends on
- Relates to
- Duplicates
- Replaces

## Configuration

- `term_definition`
- `lookup_definition`
- `lookup_value`
- `field_definition`
- `field_pack`
- `item_type_field`
- `threshold_definition`
- `configuration_version`

## Workflow and governance

- `workflow_definition`
- `workflow_stage`
- `workflow_transition`
- `gate_definition`
- `gate_instance`
- `gate_check`
- `approval_decision`

## Rules and derived values

- `rule_definition`
- `rule_condition`
- `rule_action`
- `rule_evaluation`
- `derived_metric`
- `attention_item`

## Views and presentation

- `saved_query`
- `dashboard`
- `dashboard_page`
- `widget_instance`
- `presentation`
- `presentation_page`
- `published_pack`

## History

- `audit_event`
- `outbox_event`
- `snapshot`
- `snapshot_metric`
- `snapshot_record`
- `baseline`

## Tools

- `tool_definition`
- `tool_version`
- `tool_permission`
- `tool_unit_enablement`
- `tool_execution`
- `tool_widget`

## Scenarios

- `scenario`
- `scenario_change`
- `scenario_evaluation`
- `scenario_application`

---

# 10. Progress calculation hierarchy

Progress must be calculated differently at different layers, but through one engine.

## Milestone

```text
0% before validation
100% after validation
```

Or staged progress where configured.

## Project

```text
Sum(validated milestone weight)
÷
Sum(applicable milestone weight)
```

## Programme

```text
Weighted progress of child projects
```

Weight may use:

- Equal weighting
- Budget
- Strategic weight
- Effort
- Configured weight

## Department or portfolio

Do not show only an averaged percentage. Show:

- Weighted progress
- Red/Amber/Grey/Green distribution
- Number of overdue commitments
- Forecast variance
- Validation backlog
- Capacity pressure

A portfolio containing one completed small project and one severely delayed strategic project must not misleadingly display “50% complete and healthy.”

---

# 11. Progress reporting and presentation flow

```text
Contributor updates work
        ↓
Responsible owner reviews delivery
        ↓
Accountable owner validates milestones
        ↓
Progress engine recalculates
        ↓
Roll-up engine updates parent levels
        ↓
Rule engine recalculates health
        ↓
Action Centre ranks exceptions
        ↓
Dashboard displays live position
        ↓
Weekly snapshot freezes reported position
        ↓
Presentation mode uses that snapshot
```

This provides a complete trace from employee update to executive presentation.

---

# 12. How the platform tracks its own build

The build plan should become the first real initiative immediately after Increment 3.

## Top-level item

```text
Platform Development
```

## Child workstreams

1. Platform Kernel
2. Organisation and Security
3. Work and Ownership
4. Assignment and Capacity
5. Workflow and Governance
6. Rules and Health
7. Views and Dashboards
8. Snapshots and Presentations
9. Tools and Integrations
10. Release Hardening

## Every increment becomes a milestone

Example:

```text
Milestone: Configurable Workflow and Validation Gates
Accountable owner: Product sponsor
Responsible owner: Platform development lead
Target: 31 January
Validation gate:
  - Workflow created without code
  - Rejection returns milestone
  - Validated milestone changes progress
  - Audit entry created
  - Automated tests pass
```

This is a strong product test because the platform must successfully manage its own development.

---

# 13. Improvements required in the supplied HTML prototype

The supplied single-file prototype is useful as a **behavioural reference**, but it should not become the production foundation.

## Reuse from the prototype

- Health concepts
- Grey for missing information
- Top 5 ranking concept
- Validation checklist
- Capacity buffer
- Demand assessment
- Adoption stages
- Import preview
- Saved filters
- Data-quality checks
- What-if diff concept
- Action Centre layout

## Replace completely

| Current prototype | Production replacement |
|---|---|
| Browser localStorage | PostgreSQL |
| One user | Authenticated multi-user application |
| Flat team | Organisation hierarchy |
| Owner stored as ID string | Person and ownership relationship |
| Team allocation text such as `EMP-001:30` | Assignment table |
| Free-text dependencies | Work-item dependency table |
| Fixed arrays in JavaScript | Admin-managed lookups |
| Hard-coded health function | Versioned rule engine |
| Hard-coded views | Saved-query engine |
| Direct JavaScript mutation | Command service |
| Browser-only history | Immutable audit events |
| Full scenario copy in memory | Scenario change set |
| One large HTML file | Flask modules and ES modules |
| Manual backup | Scheduled PostgreSQL backup |
| Hard-coded dashboard | Dashboard definition and widgets |

The prototype should be treated as:

```text
User experience reference
+
Rule discovery document
+
Acceptance-test source
```

It should not be incrementally expanded into the final product.

---

# 14. Revised folder structure

```text
control_tower/
├── app/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── identity/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── permissions.py
│   │   └── routes.py
│   │
│   ├── organisation/
│   ├── work/
│   ├── assignments/
│   ├── workflows/
│   ├── rules/
│   ├── views/
│   ├── dashboards/
│   ├── snapshots/
│   ├── presentations/
│   ├── tools/
│   ├── scenarios/
│   ├── imports/
│   ├── integrations/
│   │
│   ├── platform/
│   │   ├── audit/
│   │   ├── events/
│   │   ├── database/
│   │   ├── security/
│   │   └── tenancy/
│   │
│   ├── api/
│   │   └── v1/
│   │
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       │   ├── core/
│       │   ├── pages/
│       │   └── widgets/
│       └── vendor/
│
├── migrations/
├── tests/
│   ├── unit/
│   ├── service/
│   ├── api/
│   ├── permission/
│   ├── rule_examples/
│   └── browser/
│
├── seed/
├── scripts/
├── pyproject.toml
├── alembic.ini
└── run.py
```

Organise code primarily by business capability, not by putting every model in one giant `models` folder.

---

# 15. Release gates

Every release should pass these gates.

## Data gate

- No duplicated authoritative facts
- Database migration tested
- Restore tested
- Referential integrity verified

## Permission gate

- Tenant isolation verified
- Branch-level scope verified
- Field-level restrictions verified
- Tool and API permissions verified

## Calculation gate

- Progress matches validated milestones
- Health explanation matches triggered rules
- Roll-up identifies contributing children
- Cache can be rebuilt from source records

## Audit gate

- Every material write has actor, time, before, after and source
- Approval and handover history is complete
- Import and tool changes are traceable

## Presentation gate

- Dashboard and list show matching values
- Historical snapshot can be reopened
- Export numbers match the selected live or historical context

## Performance gate

Test against a representative large structure, for example:

- 1 tenant
- 1,000 organisation units
- 10,000 users
- 100,000 work items
- 500,000 assignments
- 2 million audit events

Initial target:

- Common list queries under 1 second
- Dashboard load under 3 seconds
- Background roll-up completed within 30 seconds after a large update batch
- Normal command save under 500 milliseconds, excluding file uploads

---

# 16. Realistic release sequence

| Release | Increments | Result | Approximate duration |
|---|---|---|---:|
| Foundation | 1–2 | Platform, hierarchy, sign-in and scope | 3–4 weeks |
| Trusted Work MVP | 3–5 | Work, ownership, assignments, audit | 5–7 weeks |
| Governed Delivery | 6–8 | No-code fields, workflows, health and roll-ups | 7–9 weeks |
| Control Tower Release | 9–10 | Views, Action Centre and dashboards | 4–6 weeks |
| Reporting and Extension | 11–12 | Snapshots, presentation and tools | 5–6 weeks |
| Planning Expansion | Capacity, demand, scenarios | Planning and what-if | 4–6 weeks |
| Enterprise Expansion | SSO, Teams, API, performance | Wider organisational rollout | 4–8 weeks |

A practical first production release is approximately **16 to 22 weeks** for a small focused team, depending on UI quality, security expectations and integration requirements.

---

# 17. Most important architectural rules

1. **A fact has one authoritative owner and storage location.**
2. **Every change passes through the command service.**
3. **Routes, imports, tools and integrations never write directly to tables.**
4. **Progress is derived from approved evidence.**
5. **Health always shows its reason.**
6. **Grey is never silently treated as Green.**
7. **Permissions are enforced in services and queries, not only in the interface.**
8. **Organisation hierarchy is built before widespread feature development.**
9. **Assignment is a proper record, not a comma-separated field.**
10. **Dashboards are saved queries and widgets, not separate reporting data.**
11. **Presentations use live data or an immutable snapshot.**
12. **Tools use the platform API and never own copies of shared facts.**
13. **Configuration is versioned data.**
14. **Historical snapshots are append-only.**
15. **Derived caches can always be rebuilt from authoritative facts.**
16. **Each increment includes database, service, permission, audit, UI and tests.**

---

# Final recommended scope

The first serious release should include:

- Organisation hierarchy
- Sign-in and scoped permissions
- Universal work items
- Parent-child distribution
- Accountable and responsible owners
- Employee assignments
- Basic configurable fields and lookups
- Workflow and validation gates
- Validated progress
- Explainable health
- Roll-ups
- Saved list and board views
- Action Centre
- Dashboard Builder
- Audit trail
- Import and export

Do not include the following in the initial MVP unless required by an immediate pilot:

- Advanced critical-path scheduling
- Marketplace
- Complex formula language
- Full plugin execution
- AI recommendations
- Advanced scenario optimisation
- Large integration catalogue
- Real-time collaborative editing

The correct order is:

```text
Trust the records
      ↓
Control ownership and access
      ↓
Validate progress
      ↓
Calculate health and roll-ups
      ↓
Create views and dashboards
      ↓
Freeze historical snapshots
      ↓
Present the information
      ↓
Allow tools and integrations to extend it
```

This revised structure produces a smaller and more reliable platform while preserving the full enterprise vision. The major changes are the addition of **Assignment as a core primitive**, earlier delivery of a usable vertical slice, strict separation of authoritative/configuration/derived/historical data, and making dashboards, presentations and tools formal consumers of the same query and command services.

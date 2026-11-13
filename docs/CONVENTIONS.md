# Control Tower — Conventions

Rules every change must follow. They keep the code reusable and the platform driven by settings rather than code.

## Golden rules
1. **Settings, not code.** Lookups, colours, fields, filters, approval chains, health rules, permissions and terminology are stored as data and edited by admins. Never hard-code a status, colour, role name or approval step.
2. **One write path.** Every create, update or delete goes through a service that extends `app.core.command.CommandService`. Routes never call `db.session.add/commit` themselves.
3. **Audit everything.** Every write records an `audit_event` in the same transaction: actor, entity, field, old value, new value, reason, source and correlation ID. If the transaction fails, there is no audit row.
4. **Scope every read.** List and get queries go through the scope helper (`app.core.scope`), so users see only what their role and unit allow. Checks are enforced on the server, not just hidden in the UI.
5. **Derived values are calculated, not typed in.** Progress, health and roll-ups come from engines and can always be rebuilt.

## Backend (`backend/`)
- Each module in `app/modules/<name>/` has the same files:
  - `models.py`: SQLAlchemy models, inheriting from `app.core.models.BaseModel`.
  - `schemas.py`: Pydantic input/output models, inheriting from `app.core.schemas`.
  - `service.py`: business logic; writes go through `CommandService`.
  - `routes.py`: a Flask blueprint under `/api/v1/<name>` that is thin: parse input → call the service → return JSON.
- **Hierarchies:** any tree (units, functions, later work items) uses `app.core.tree`: a closure model from `make_closure_model()` plus a service extending `TreeService`, which handles closure rows, moves and cycle checks.
- **Scope** (`app.modules.access.scope`):
  - `managed_unit_ids(user)` is the area a person may see the people and work of, and manage.
  - `visible_unit_ids(user)` adds their own unit, so it appears in the tree.
  - `person_visibility_clause(user)` limits any people query.

  Every list, count and detail must apply scope, and counts must match the lists they lead to.
- **Linked values** (e.g. a person's `role_ids`) are declared in `CommandService.extra_fields`, so they are validated, compared and audited like columns.
- **Permissions:** new permission codes go in `app/modules/access/catalog.py`. Which roles hold them is data.
- **Lookups and settings** (`app.modules.lookups`, `app.modules.config`):
  - Statuses, priorities, item types and other choice lists are lookup values. Store the value **id**, never a label or colour. The frontend gets the label and colour from `js/core/lookups.js`.
  - Lookup values, lists and field definitions are never deleted. They are retired (`is_active = False`), so old records keep their labels.
  - The settings tables are the **draft**. Everything outside the admin settings screens reads the **published** version through `app.modules.config.versioning` (`published_snapshot`, `published_fields`, `published_values`) or `GET /api/v1/settings`. Publishing, discarding and rolling back go through `SettingsService`.
  - A new kind of settings record joins versioning by adding it to `COLLECTIONS` in `versioning.py`.
- **Custom fields:** to give a record custom fields, add a `custom_fields` JSON column to its model, set `custom_entity = "<entity>"` on its service, add the entity to `ENTITY_TYPES`, and call `apply_custom_filters` in its list method. Validation, merging and per-field audit (`custom_fields.<code>`) then come from `CommandService`. JSON column queries go through `app.core.json_query`, the only place that knows the MySQL and SQLite differences.
- Errors: raise `AppError` subclasses from `app.core.errors` (`NotFound`, `Forbidden`, `ValidationFailed`, `Conflict`). They are rendered as `{"error": {"code", "message", "details"}}`.
- Lists: use `app.core.filters.apply_filters` and `app.core.pagination.paginate`. Responses look like `{"items": [...], "page", "per_page", "total"}`.
- Database: SQLAlchemy 2 style (`db.select(...)`). The target is MySQL (via PyMySQL); SQLite is acceptable for quick local tests. Avoid features that only one database supports.
- **Databases:** local development uses a SQLite file (`backend/control_tower_dev.db`), and production uses MySQL.
- **Every schema change follows these steps, in the same change:**
  1. Edit the models.
  2. `flask --app run db migrate -m "<what changed>"` → review the generated file.
  3. `flask --app run db upgrade` (applies it to the local database).
  4. `flask --app run schema-export` → regenerates `backend/database/schema_mysql.sql`.

  `tests/test_schema_file.py` fails if step 4 was missed. Never edit an already-applied migration or the generated SQL file by hand.
- **Moving to production MySQL:** for a new database, load `database/schema_mysql.sql`. It records the Alembic revision, so later changes are applied with `flask db upgrade` against MySQL.
- Tests live in `backend/tests/`, and each feature needs service, API and permission tests.

## Frontend (`frontend/`)
- Plain HTML, CSS and JavaScript ES modules. No framework and no build step.
- **Pages only combine components.** `js/pages/<page>.js` builds the screen from `js/components/*`. If something is needed twice, it becomes a component.
- All HTTP calls go through `js/core/api.js`; never call `fetch` directly from a page.
- `js/core/layout.js` renders the sidebar and top bar for every page. A page calls `initLayout({ active: '<nav-key>', title, permission })`. `permission` guards the page, and nav items declare `perm`. Use `can(user, code)` to show or hide buttons. The server still enforces every check.
- **Forms:** always use `createForm` / `openFormModal` from `components/form-builder.js`. Edit forms include a "Reason for change" field, which goes to the audit log.
- **Settings on screens:** `initLayout` loads the published settings first. Use `lookupBadge(id)` and `lookupOptions(list, current)` for lookup values, `term(key)` for renameable words, and `components/custom-fields.js` (`customFormFields`, `withCustomValues`, `customColumns`, `customFilterFields`) so custom fields show up on a screen with no extra code.
- **Settings screens** show `createSettingsBanner()` from `components/settings-banner.js` and call `banner.refresh()` after each draft edit.
- **Hierarchy screens:** reuse `pages/hierarchy-page.js` with a config (see `organisation.js` and `functions.js`).
- Components export a factory function that returns a DOM element, such as `createDataTable(options)` or `openModal(options)`. They never reach into page globals.
- Escape user text: use `el()` from `js/core/utils.js` or `textContent`, never `innerHTML` with data.

## UI and styling
- Colours, spacing, radius, shadows and fonts are defined only as CSS variables in `css/tokens.css`. Components never contain hex values.
- Palette: neutral greys plus one accent (muted navy). Red, amber, grey and green are for status only, and the actual colours come from lookup values.
- 14px base font, 8px spacing grid, 6px radius, light shadows. Keep screens calm, with plenty of white space and no decorative colour.
- File roles: `base.css` (reset and elements), `layout.css` (shell, grid), `components.css` (buttons, cards, table, forms, badges, modal, toast).

## Naming
- Python: `snake_case`. JS: `camelCase` functions and `kebab-case.js` file names. CSS classes: `ct-` prefix, BEM-like (`ct-table__row`).
- API routes use plural nouns: `/api/v1/units`, `/api/v1/work-items/<id>`.

"""The catalogue of permission codes the platform understands.

Codes are defined here because each one guards a piece of code; WHICH roles hold them
is data that admins edit. Add new codes as features arrive.
"""
PERMISSIONS = [
    # (code, group, label)
    ("org.view", "Organisation", "View organisation units"),
    ("org.manage", "Organisation", "Create, edit and move units (within scope)"),
    ("functions.view", "Functions", "View functions"),
    ("functions.manage", "Functions", "Create, edit and move functions"),
    ("people.view", "People", "View people (within scope)"),
    ("people.manage", "People", "Add and edit people (within scope)"),
    ("work.view", "Work", "View work items (within scope) and update the ones you are responsible or assigned on"),
    ("work.create", "Work", "Create top-level work items"),
    ("work.manage", "Work", "Edit, delegate, assign and delete work in your units"),
    ("views.share", "Work", "Share saved views with everyone"),
    ("dashboards.share", "Work", "Share dashboards with everyone"),
    ("demand.decide", "Demand", "Assess and decide requests for new work in your units (accept, reject, defer, clarify)"),
    ("snapshots.manage", "Reporting", "Take snapshots of the figures and edit their labels and notes"),
    ("snapshots.approve", "Reporting", "Approve snapshots for reporting and choose the baseline"),
    ("imports.run", "Data", "Import people, work, assignments and requests from Excel or CSV (each row still needs the usual rights)"),
    ("scenarios.use", "Planning", "Plan what-if scenarios for work you manage and apply them (each change is checked again)"),
    ("templates.share", "Planning", "Share work templates with everyone and edit shared ones"),
    ("api.tokens", "Integrations", "Make personal API tokens (for Power BI, scripts and tools that write back)"),
    ("integrations.manage", "Integrations", "Manage webhooks and Teams channels, see deliveries, and revoke anyone's API tokens"),
    ("tools.manage", "Tools", "Manage the tools registry: add, change and retire tools, and who may use them"),
    ("roles.manage", "Access", "Manage roles and assign them to people"),
    ("audit.view", "Audit", "View the audit log"),
    ("settings.manage", "Settings", "Manage lookups, custom fields and terminology; publish and roll back settings"),
]

PERMISSION_CODES = frozenset(code for code, _, _ in PERMISSIONS)


def catalog() -> list[dict]:
    return [{"code": c, "group": g, "label": l} for c, g, l in PERMISSIONS]

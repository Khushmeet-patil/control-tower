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
    ("roles.manage", "Access", "Manage roles and assign them to people"),
    ("audit.view", "Audit", "View the audit log"),
    ("settings.manage", "Settings", "Manage lookups, custom fields and terminology; publish and roll back settings"),
]

PERMISSION_CODES = frozenset(code for code, _, _ in PERMISSIONS)


def catalog() -> list[dict]:
    return [{"code": c, "group": g, "label": l} for c, g, l in PERMISSIONS]

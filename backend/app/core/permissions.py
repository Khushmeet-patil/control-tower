"""Permission checks used by services and routes.

Phase 0: admins can do everything; other users have only the permission codes their
User.permission_codes() returns. Phase 1 replaces that with roles stored in the database.
"""
from functools import wraps

from flask_login import current_user

from app.core.errors import Forbidden, Unauthorized


def actor_can(actor, permission: str | None) -> bool:
    if permission is None:
        return True
    if actor is None:  # system actions (seed, background jobs)
        return True
    if getattr(actor, "is_admin", False):
        return True
    return permission in actor.permission_codes()


def ensure_can(actor, permission: str | None, message: str = "You do not have permission to do this"):
    if not actor_can(actor, permission):
        raise Forbidden(message)


def require_permission(permission: str | None = None):
    """Route decorator: requires a signed-in user, and the permission if one is given."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                raise Unauthorized("Please sign in")
            ensure_can(current_user, permission)
            return view(*args, **kwargs)

        return wrapper

    return decorator


login_required = require_permission()

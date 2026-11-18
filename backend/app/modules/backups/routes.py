from flask import Blueprint

from app.core.permissions import require_permission
from app.modules.backups import service

bp = Blueprint("backups", __name__, url_prefix="/api/v1/backups")


@bp.get("")
@require_permission("settings.manage")
def backup_status():
    """When the last backup was taken, whether that is too long ago, and the recent backups.
    Backups are taken by the scheduled `flask backup` job, not from the browser."""
    return service.status()

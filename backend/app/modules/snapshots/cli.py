"""`flask --app run snapshot [--weekly]`: take a snapshot from the command line or a scheduler.

Weekly snapshots are taken at most once per ISO week, so a cron line can run it daily or weekly:
    0 6 * * 1  cd /path/to/backend && .venv/bin/flask --app run snapshot --weekly
"""
import click
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.modules.organisation.models import Tenant
from app.modules.snapshots.service import SnapshotService


@click.command("snapshot")
@click.option("--weekly", is_flag=True, help="This week's snapshot (skipped if it already exists).")
@click.option("--label", default=None, help="Label for an on-demand snapshot.")
@with_appcontext
def snapshot_command(weekly, label):
    for tenant in db.session.scalars(select(Tenant)):
        s = SnapshotService(None, tenant_id=tenant.id, source="system").take(
            kind="weekly" if weekly else "on_demand", label=label)
        click.echo(f"{tenant.name}: “{s.label}” as of {s.as_of} ({s.item_count} items)")

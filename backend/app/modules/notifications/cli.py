"""flask --app run notify [--checks] [--deliver]

    --checks   the daily checks: deadlines coming up, overdue work, work that turned Red (schedule daily, e.g. 07:00)
    --deliver  send queued email and webhook messages (schedule every minute or two)
With neither option, both run.
"""
import click
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db


@click.command("notify")
@click.option("--checks", is_flag=True, help="Run the daily checks (due soon, overdue, turned Red).")
@click.option("--deliver", is_flag=True, help="Send queued email and webhook messages.")
@with_appcontext
def notify_command(checks, deliver):
    from app.modules.notifications.delivery import deliver_pending
    from app.modules.notifications.service import run_checks
    from app.modules.organisation.models import Tenant

    if not checks and not deliver:
        checks = deliver = True
    if checks:
        for tenant in db.session.scalars(select(Tenant)):
            counts = run_checks(tenant.id)
            click.echo(f"{tenant.name}: {counts['due_soon']} due soon, {counts['overdue']} overdue, "
                       f"{counts['item_red']} turned Red (notifications)")
    if deliver:
        total = {"tried": 0, "sent": 0, "failed": 0}
        while True:
            result = deliver_pending()
            for k in total:
                total[k] += result[k]
            if result["tried"] < 200:
                break
        click.echo(f"Delivered {total['sent']} of {total['tried']} messages ({total['failed']} will be retried or failed).")

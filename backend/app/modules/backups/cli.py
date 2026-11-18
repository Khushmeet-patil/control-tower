"""`flask --app run backup` and `flask --app run restore` (see service.py)."""
import click
from flask.cli import with_appcontext

from app.modules.backups import service


@click.command("backup")
@click.option("--list", "show", is_flag=True, help="List backups instead of taking one.")
@click.option("--verify", "verify_file", default=None, help="Check a backup file.")
@with_appcontext
def backup_command(show, verify_file):
    try:
        if show:
            for b in service.list_backups():
                click.echo(f"{b['created_at']}  {b['file']}  {b['bytes'] // 1024} KB  verified={b['verified']}")
            return
        if verify_file:
            result = service.verify(verify_file if "/" in verify_file else service.backup_dir() / verify_file)
            click.echo("OK" if result["ok"] else "PROBLEMS:\n  " + "\n  ".join(result["problems"]))
            raise SystemExit(0 if result["ok"] else 1)
        m = service.create_backup()
        removed = service.prune()
        click.echo(f"Backup {m['file']} ({m['bytes'] // 1024} KB, verified={m['verified']}) in {service.backup_dir()}")
        if removed:
            click.echo(f"Removed {len(removed)} old backup(s)")
        if not m["verified"]:
            raise SystemExit(1)
    except service.BackupError as exc:
        raise click.ClickException(str(exc)) from exc


@click.command("restore")
@click.argument("file")
@click.option("--yes", is_flag=True, help="Confirm: the current data is replaced (after a safety backup).")
@with_appcontext
def restore_command(file, yes):
    if not yes:
        raise click.ClickException("Restoring replaces all current data. Stop the app, then run again with --yes.")
    try:
        result = service.restore(file)
    except service.BackupError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Restored {result['restored']}. The data before the restore is in {result['safety_backup']}.")

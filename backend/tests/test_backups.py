"""Phase 9: backups are taken, verified, listed, pruned and restored; admins see how old the last one is."""
import gzip
import json
import sqlite3
from datetime import timedelta

import pytest
from sqlalchemy.engine import make_url

from app.core.models import utcnow
from app.modules.backups import service


@pytest.fixture()
def file_db(app, tmp_path, monkeypatch):
    """A Control Tower-shaped SQLite file standing in for the live database."""
    path = tmp_path / "live.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE users (id INTEGER); CREATE TABLE work_items (id INTEGER, title TEXT);"
                      "CREATE TABLE audit_events (id INTEGER); INSERT INTO work_items VALUES (1, 'Portal'), (2, 'Triage');")
    con.commit()
    con.close()
    monkeypatch.setattr(service, "_url", lambda: make_url(f"sqlite:///{path}"))
    monkeypatch.setattr(service, "_release_connections", lambda: None)
    app.config["BACKUP_DIR"] = str(tmp_path / "backups")
    return path


def titles(path):
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT title FROM work_items ORDER BY id")]
    finally:
        con.close()


def test_backup_is_verified_and_restores(app, file_db):
    m = service.create_backup()
    assert m["verified"] and m["sha256"] and m["file"].endswith(".sqlite3.gz")
    assert service.list_backups()[0]["file"] == m["file"]

    con = sqlite3.connect(file_db)
    con.execute("DELETE FROM work_items")
    con.commit()
    con.close()
    result = service.restore(m["file"])
    assert titles(file_db) == ["Portal", "Triage"]
    assert result["safety_backup"] != m["file"]  # the data before the restore was kept too
    assert len(service.list_backups()) == 2


def test_damaged_backups_are_caught_and_not_restored(app, file_db):
    m = service.create_backup()
    path = service.backup_dir() / m["file"]
    path.write_bytes(path.read_bytes()[:-20])
    check = service.verify(path)
    assert not check["ok"] and any("checksum" in p for p in check["problems"])
    with pytest.raises(service.BackupError):
        service.restore(m["file"])
    assert titles(file_db) == ["Portal", "Triage"]


def test_old_backups_are_pruned_but_the_newest_kept(app, file_db):
    folder = service.backup_dir()
    for days in (90, 80, 70, 60, 50):
        stamp = utcnow() - timedelta(days=days)
        name = f"{service.PREFIX}{stamp:%Y%m%d-%H%M%S}.sqlite3.gz"
        with gzip.open(folder / name, "wb") as f:
            f.write(b"x")
        (folder / f"{name}.json").write_text(json.dumps({"created_at": stamp.isoformat(timespec="seconds")}))
    app.config.update(BACKUP_KEEP_DAYS=30, BACKUP_KEEP_MIN=3)
    removed = service.prune()
    assert len(removed) == 2 and len(service.list_backups()) == 3
    s = service.status()
    assert s["overdue"] and s["age_days"] >= 50  # the newest is 50 days old: past the 7-day reminder


def test_backup_status_is_for_admins(demo, file_db, admin_client, as_user):
    service.create_backup()
    data = admin_client.get("/api/v1/backups").get_json()
    assert data["count"] == 1 and data["overdue"] is False and data["last"]["verified"]
    assert as_user("meera").get("/api/v1/backups").status_code == 403


def test_cli_refuses_restore_without_confirmation(app, file_db):
    m = service.create_backup()
    result = app.test_cli_runner().invoke(args=["restore", m["file"]])
    assert result.exit_code != 0 and "--yes" in result.output

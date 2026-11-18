"""Database backups: take, verify, list, prune and restore.

    flask --app run backup              take a backup now (then verify it and prune old ones)
    flask --app run backup --list       list backups
    flask --app run backup --verify F   check a backup file
    flask --app run restore F --yes     restore a backup (a safety backup of the current data is taken first)

Schedule `backup` daily (cron, systemd timer or Task Scheduler), e.g.
    30 1 * * *  cd /path/to/backend && .venv/bin/flask --app run backup

- SQLite (local development): the online backup API copies a consistent database while the app runs.
- MySQL (production): `mysqldump --single-transaction` (a consistent snapshot without locking InnoDB
  tables). The password is passed in the environment, never on the command line.
Each backup is gzipped and gets a manifest (.json): time, size, SHA-256, schema revision and row
counts, so a restore can be checked before it is used. Backups older than BACKUP_KEEP_DAYS are
deleted, but the newest BACKUP_KEEP_MIN are always kept. Store BACKUP_DIR on another disk or copy it
off the server: a backup on the same disk does not survive the disk.
"""
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.models import utcnow
from app.extensions import db

PREFIX = "control-tower-"
COUNTED = ("users", "work_items", "assignments", "audit_events", "snapshots")


class BackupError(RuntimeError):
    pass


def backup_dir() -> Path:
    path = Path(current_app.config["BACKUP_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _url():
    return make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _facts() -> dict:
    """Schema revision and row counts of the live database, recorded in the manifest."""
    names = set(inspect(db.engine).get_table_names())
    revision = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() \
        if "alembic_version" in names else None
    counts = {t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in COUNTED if t in names}
    return {"schema_revision": revision, "row_counts": counts}


# ---------------------------------------------------------------------- taking
def create_backup() -> dict:
    url = _url()
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    folder = backup_dir()
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            raise BackupError("An in-memory database cannot be backed up")
        target = _unique(folder, stamp, ".sqlite3.gz")
        _backup_sqlite(Path(url.database), target)
        kind = "sqlite"
    elif url.get_backend_name() == "mysql":
        target = _unique(folder, stamp, ".sql.gz")
        _backup_mysql(url, target)
        kind = "mysql"
    else:
        raise BackupError(f"Backups are not supported for {url.get_backend_name()}")
    manifest = {"file": target.name, "kind": kind, "created_at": utcnow().isoformat(timespec="seconds"),
                "bytes": target.stat().st_size, "sha256": _sha256(target), **_facts()}
    _write_manifest(target, manifest)  # verify() checks the file against this checksum
    manifest["verified"] = verify(target)["ok"]
    _write_manifest(target, manifest)
    return manifest


def _unique(folder: Path, stamp: str, suffix: str) -> Path:
    """A new file name, never an existing one (two backups in the same second, e.g. a restore's safety backup)."""
    target, n = folder / f"{PREFIX}{stamp}{suffix}", 2
    while target.exists():
        target, n = folder / f"{PREFIX}{stamp}-{n}{suffix}", n + 1
    return target


def _write_manifest(target: Path, manifest: dict):
    target.with_suffix(target.suffix + ".json").write_text(json.dumps(manifest, indent=2))


def _backup_sqlite(source: Path, target: Path):
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.sqlite3"
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)  # consistent, even while the app is writing
        finally:
            dst.close()
            src.close()
        with open(copy, "rb") as fin, gzip.open(target, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout)


def _mysql_env(url):
    env = dict(os.environ)
    if url.password:
        env["MYSQL_PWD"] = str(url.password)
    return env


def _mysql_args(url):
    args = ["--host", url.host or "localhost", "--port", str(url.port or 3306)]
    if url.username:
        args += ["--user", url.username]
    return args


def _backup_mysql(url, target: Path):
    dump = shutil.which("mysqldump")
    if not dump:
        raise BackupError("mysqldump was not found; install the MySQL client tools on this server")
    cmd = [dump, *_mysql_args(url), "--single-transaction", "--quick", "--routines", "--triggers",
           "--no-tablespaces", "--default-character-set=utf8mb4", url.database]
    with gzip.open(target, "wb", compresslevel=6) as out:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_mysql_env(url))
        shutil.copyfileobj(proc.stdout, out)
        _, err = proc.communicate()
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupError(f"mysqldump failed: {err.decode(errors='replace').strip()[:500]}")


# ---------------------------------------------------------------------- checking
def _manifest(path: Path) -> dict | None:
    m = path.with_suffix(path.suffix + ".json")
    try:
        return json.loads(m.read_text()) if m.exists() else None
    except ValueError:
        return None


def verify(path) -> dict:
    """Is this backup complete and usable? Checks the checksum, that it unzips, and the contents."""
    path = Path(path)
    problems = []
    manifest = _manifest(path)
    if not path.exists():
        return {"ok": False, "problems": ["The file does not exist"]}
    if manifest and manifest.get("sha256") and manifest["sha256"] != _sha256(path):
        problems.append("The checksum does not match the manifest: the file has changed or is damaged")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            with gzip.open(path, "rb") as fin, open(raw, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            if path.name.endswith(".sqlite3.gz"):
                con = sqlite3.connect(raw)
                try:
                    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        problems.append("SQLite integrity check failed")
                    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {"users", "work_items", "audit_events"} <= tables:
                        problems.append("Control Tower tables are missing")
                finally:
                    con.close()
            else:
                with open(raw, "rb") as f:
                    f.seek(max(0, raw.stat().st_size - 200))
                    if b"Dump completed" not in f.read():
                        problems.append("The dump is incomplete (no “Dump completed” line)")
    except (OSError, EOFError, sqlite3.DatabaseError) as exc:
        problems.append(f"The file cannot be read: {exc}")
    return {"ok": not problems, "problems": problems}


def list_backups() -> list[dict]:
    out = []
    for path in sorted(backup_dir().glob(f"{PREFIX}*.gz"), reverse=True):
        m = _manifest(path) or {}
        out.append({"file": path.name, "kind": m.get("kind") or ("sqlite" if ".sqlite3" in path.name else "mysql"),
                    "created_at": m.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "bytes": path.stat().st_size, "verified": m.get("verified"), "schema_revision": m.get("schema_revision"),
                    "row_counts": m.get("row_counts") or {}})
    return out


def prune() -> list[str]:
    keep_days = int(current_app.config["BACKUP_KEEP_DAYS"])
    keep_min = int(current_app.config["BACKUP_KEEP_MIN"])
    cutoff = utcnow() - timedelta(days=keep_days)
    removed = []
    for i, b in enumerate(list_backups()):
        if i < keep_min:
            continue  # always keep the newest few, however old
        if datetime.fromisoformat(b["created_at"]) < cutoff:
            path = backup_dir() / b["file"]
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".json").unlink(missing_ok=True)
            removed.append(b["file"])
    return removed


def status() -> dict:
    """For the admin screen: when the last backup was taken, and whether that is too long ago."""
    backups = list_backups()
    remind = int(current_app.config["BACKUP_REMIND_DAYS"])
    last = backups[0] if backups else None
    age = (utcnow() - datetime.fromisoformat(last["created_at"])).days if last else None
    return {"last": last, "age_days": age, "remind_after_days": remind, "overdue": age is None or age > remind,
            "count": len(backups), "total_bytes": sum(b["bytes"] for b in backups), "items": backups[:30],
            "keep_days": current_app.config["BACKUP_KEEP_DAYS"]}


# ---------------------------------------------------------------------- restoring
def _release_connections():
    """Close this process's connections so the database file can be replaced."""
    db.session.remove()
    db.engine.dispose()


def restore(path) -> dict:
    """Replace the current database with a backup. A safety backup is taken first."""
    path = Path(path)
    if not path.is_absolute():
        path = backup_dir() / path
    check = verify(path)
    if not check["ok"]:
        raise BackupError("Not restoring an unusable backup: " + "; ".join(check["problems"]))
    url = _url()
    safety = create_backup()
    _release_connections()
    if path.name.endswith(".sqlite3.gz"):
        if url.get_backend_name() != "sqlite":
            raise BackupError("This is a SQLite backup; the app is using MySQL")
        target = Path(url.database)
        tmp = target.with_suffix(".restoring")
        with gzip.open(path, "rb") as fin, open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        os.replace(tmp, target)
    else:
        if url.get_backend_name() != "mysql":
            raise BackupError("This is a MySQL backup; the app is using SQLite")
        client = shutil.which("mysql")
        if not client:
            raise BackupError("The mysql client was not found")
        with gzip.open(path, "rb") as fin:
            proc = subprocess.run([client, *_mysql_args(url), url.database], stdin=fin, capture_output=True,
                                  env=_mysql_env(url), check=False)
        if proc.returncode != 0:
            raise BackupError(f"mysql failed: {proc.stderr.decode(errors='replace').strip()[:500]}")
    return {"restored": path.name, "safety_backup": safety["file"]}

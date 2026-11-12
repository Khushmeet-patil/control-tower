"""Generates database/schema_mysql.sql — the full MySQL schema for production — from the models.

Local development runs on SQLite; this file is what gets loaded into production MySQL.
It is regenerated after every model change with:

    flask --app run schema-export

and tests/test_schema_file.py fails if it is out of date, so it can never drift from the code.
The file also records the Alembic revision, so later migrations can be applied on top of it.
"""
from pathlib import Path

import click
from alembic.config import Config
from alembic.script import ScriptDirectory
from flask.cli import with_appcontext
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import BACKEND_DIR
from app.extensions import db

SCHEMA_FILE = BACKEND_DIR / "database" / "schema_mysql.sql"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
TABLE_OPTIONS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"


def alembic_head() -> str | None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def render_mysql_schema() -> str:
    dialect = mysql.dialect()
    head = alembic_head()
    out = [
        "-- Control Tower — MySQL schema (generated; do not edit by hand).",
        "-- Regenerate after any model change:  flask --app run schema-export",
        f"-- Alembic revision: {head}",
        "--",
        "-- Load into an empty database:",
        "--   CREATE DATABASE control_tower CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        "--   mysql -u <user> -p control_tower < schema_mysql.sql",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]
    for table in db.metadata.sorted_tables:
        out.append(f"-- {table.name}")
        out.append(f"DROP TABLE IF EXISTS `{table.name}`;")
        create = str(CreateTable(table).compile(dialect=dialect)).strip()
        out.append(f"{create} {TABLE_OPTIONS};")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            out.append(f"{str(CreateIndex(index).compile(dialect=dialect)).strip()};")
        out.append("")

    # Lets `flask db upgrade` apply future migrations on top of this schema.
    out += [
        "-- alembic_version (migration bookkeeping)",
        "DROP TABLE IF EXISTS `alembic_version`;",
        "CREATE TABLE alembic_version (\n\tversion_num VARCHAR(32) NOT NULL,\n\t"
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)\n) " + TABLE_OPTIONS + ";",
    ]
    if head:
        out.append(f"INSERT INTO alembic_version (version_num) VALUES ('{head}');")
    out += ["", "SET FOREIGN_KEY_CHECKS = 1;", ""]
    return "\n".join(out)


def write_schema_file(path: Path = SCHEMA_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_mysql_schema(), encoding="utf-8")
    return path


@click.command("schema-export")
@with_appcontext
def schema_export_command():
    """Write database/schema_mysql.sql from the current models."""
    path = write_schema_file()
    click.echo(f"MySQL schema written to {path}")

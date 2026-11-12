"""Guards the production MySQL schema file: it must always match the models and latest migration."""
from app.core.schema_export import SCHEMA_FILE, alembic_head, render_mysql_schema


def test_mysql_schema_file_is_up_to_date(app):
    assert SCHEMA_FILE.exists(), "Run: flask --app run schema-export"
    assert SCHEMA_FILE.read_text(encoding="utf-8") == render_mysql_schema(), (
        "database/schema_mysql.sql is out of date. Run: flask --app run schema-export"
    )


def test_schema_file_records_latest_migration(app):
    assert f"VALUES ('{alembic_head()}')" in SCHEMA_FILE.read_text(encoding="utf-8")

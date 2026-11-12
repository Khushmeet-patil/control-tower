"""Settings that shape the platform without code changes.

- FieldDefinition: an admin-defined custom field on a kind of record (people now, work items
  from Phase 3). Values live in the record's `custom_fields` JSON column, keyed by `code`.
- Term: renameable words used across the UI (e.g. "Person/People", "Work item/Work items").
- ConfigVersion: a published, frozen copy of all settings (lookups, fields, terms).

How versioning works: admins edit the settings tables, which act as the DRAFT. Publishing
freezes the draft into a new ConfigVersion, and the rest of the platform reads only the
current published version. Rolling back restores the tables from an older version and
publishes the result as a new version, so history is never rewritten.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel

ENTITY_TYPES = {"person": "People", "work_item": "Work items"}
FIELD_TYPES = {
    "text": "Text", "number": "Number", "date": "Date", "select": "Select (one)",
    "multi_select": "Select (many)", "person": "Person", "url": "Link (URL)",
}
LIST_FIELD_TYPES = ("select", "multi_select")


class FieldDefinition(BaseModel):
    __tablename__ = "field_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "code", name="uq_field_definitions_entity_code"),)

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # The lookup list that supplies options (and colours) for select / multi_select fields.
    lookup_type_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_types.id"), nullable=True)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_in_list: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Work items only: limit the field to some item types (lookup value ids); empty = all types.
    item_type_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Term(BaseModel):
    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_terms_tenant_key"),)

    key: Mapped[str] = mapped_column(String(50), nullable=False)
    singular: Mapped[str] = mapped_column(String(100), nullable=False)
    plural: Mapped[str] = mapped_column(String(100), nullable=False)
    default_singular: Mapped[str] = mapped_column(String(100), nullable=False)
    default_plural: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConfigVersion(BaseModel):
    __tablename__ = "config_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_config_versions_tenant_number"),)

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    published_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Set when this version was created by rolling back to an earlier one.
    restored_from_id: Mapped[int | None] = mapped_column(ForeignKey("config_versions.id"), nullable=True)

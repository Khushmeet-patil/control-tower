from typing import Literal

from pydantic import Field

from app.core.schemas import InputSchema

EntityType = Literal["person", "work_item"]
FieldType = Literal["text", "number", "date", "select", "multi_select", "person", "url"]


class FieldCreateIn(InputSchema):
    entity_type: EntityType
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType
    lookup_type_id: int | None = None
    help_text: str | None = None
    is_required: bool = False
    is_filterable: bool = True
    show_in_list: bool = False
    sort_order: int | None = None
    item_type_ids: list[int] | None = None
    reason: str | None = None


class FieldUpdateIn(InputSchema):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    help_text: str | None = None
    is_required: bool | None = None
    is_filterable: bool | None = None
    show_in_list: bool | None = None
    sort_order: int | None = None
    item_type_ids: list[int] | None = None
    is_active: bool | None = None
    version: int | None = None
    reason: str | None = None


class TermUpdateIn(InputSchema):
    singular: str | None = Field(default=None, min_length=1, max_length=100)
    plural: str | None = Field(default=None, min_length=1, max_length=100)
    version: int | None = None
    reason: str | None = None


class PublishIn(InputSchema):
    note: str | None = Field(default=None, max_length=500)


class ReasonIn(InputSchema):
    reason: str | None = Field(default=None, max_length=500)

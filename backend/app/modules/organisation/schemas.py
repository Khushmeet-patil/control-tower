from pydantic import Field

from app.core.schemas import InputSchema

Name = Field(min_length=1, max_length=200)
Code = Field(default=None, max_length=50)


class UnitCreateIn(InputSchema):
    name: str = Name
    code: str | None = Code
    unit_type_id: int
    parent_id: int | None = None
    head_id: int | None = None
    description: str | None = None
    reason: str | None = None


class UnitUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Code
    unit_type_id: int | None = None
    parent_id: int | None = None
    head_id: int | None = None
    description: str | None = None
    version: int | None = None
    reason: str | None = None


class FunctionCreateIn(InputSchema):
    name: str = Name
    code: str | None = Code
    parent_id: int | None = None
    lead_id: int | None = None
    description: str | None = None
    reason: str | None = None


class FunctionUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Code
    parent_id: int | None = None
    lead_id: int | None = None
    description: str | None = None
    version: int | None = None
    reason: str | None = None

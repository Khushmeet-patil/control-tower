from pydantic import Field

from app.core.schemas import InputSchema

Code = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
Color = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class LookupTypeCreateIn(InputSchema):
    code: str = Code
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    sort_order: int | None = None
    reason: str | None = None


class LookupTypeUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    version: int | None = None
    reason: str | None = None


class LookupValueCreateIn(InputSchema):
    lookup_type_id: int
    code: str = Code
    label: str = Field(min_length=1, max_length=100)
    color: str = Color
    description: str | None = None
    sort_order: int | None = None
    is_default: bool = False
    reason: str | None = None


class LookupValueUpdateIn(InputSchema):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str | None = None
    sort_order: int | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    version: int | None = None
    reason: str | None = None

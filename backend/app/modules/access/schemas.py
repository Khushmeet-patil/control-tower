from typing import Literal

from pydantic import Field

from app.core.schemas import InputSchema

Scope = Literal["own", "unit", "all"]


class RoleCreateIn(InputSchema):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    scope: Scope = "own"
    permission_codes: list[str] = []
    is_default: bool = False
    reason: str | None = None


class RoleUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    scope: Scope | None = None
    permission_codes: list[str] | None = None
    is_default: bool | None = None
    version: int | None = None
    reason: str | None = None

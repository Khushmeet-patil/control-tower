from pydantic import Field

from app.core.schemas import InputSchema

Email = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PersonCreateIn(InputSchema):
    email: str = Email
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employee_code: str | None = Field(default=None, max_length=50)
    unit_id: int | None = None
    function_id: int | None = None
    manager_id: int | None = None
    role_ids: list[int] = []
    is_admin: bool = False
    is_active: bool = True
    custom_fields: dict | None = None
    reason: str | None = None


class PersonUpdateIn(InputSchema):
    email: str | None = Field(default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employee_code: str | None = Field(default=None, max_length=50)
    unit_id: int | None = None
    function_id: int | None = None
    manager_id: int | None = None
    role_ids: list[int] | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    custom_fields: dict | None = None
    version: int | None = None
    reason: str | None = None


class PasswordResetIn(InputSchema):
    password: str = Field(min_length=8, max_length=200)
    reason: str | None = None

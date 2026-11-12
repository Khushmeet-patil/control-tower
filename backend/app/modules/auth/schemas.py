from pydantic import Field

from app.core.schemas import InputSchema


class LoginIn(InputSchema):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class PasswordChangeIn(InputSchema):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

"""Shared Pydantic bases for request and response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InputSchema(BaseModel):
    """Request bodies: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputSchema(BaseModel):
    """Responses: can be built straight from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class RecordOut(OutputSchema):
    """Common system fields returned with every record."""

    id: int
    version: int
    created_at: datetime
    updated_at: datetime


def parse_body(schema: type[InputSchema], payload) -> tuple[dict, int | None, str | None]:
    """Validate a request body and split it into (changes, expected_version, reason).

    Only fields the client actually sent are included, so PATCH can clear a value with null
    without touching fields it did not mention.
    """
    body = schema.model_validate(payload or {})
    data = body.model_dump(exclude_unset=True)
    version = data.pop("version", None)
    reason = data.pop("reason", None) or None
    return data, version, reason

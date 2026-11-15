from pydantic import Field

from app.core.schemas import InputSchema


class ChainCreateIn(InputSchema):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    item_type_ids: list[int] | None = None
    unit_id: int | None = None
    sort_order: int | None = None
    is_active: bool = True
    reason: str | None = None


class ChainUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    item_type_ids: list[int] | None = None
    unit_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    version: int | None = None
    reason: str | None = None


class _StepFields(InputSchema):
    sort_order: int | None = None
    approver_role_id: int | None = None
    approver_person_id: int | None = None
    checklist: list[str] | None = None
    require_evidence: bool | None = None
    require_comment: bool | None = None
    reason: str | None = None


class StepCreateIn(_StepFields):
    chain_id: int
    name: str = Field(min_length=1, max_length=100)
    approver_kind: str
    when_missing: str = "skip"
    require_evidence: bool = False
    require_comment: bool = False
    is_active: bool = True


class StepUpdateIn(_StepFields):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    approver_kind: str | None = None
    when_missing: str | None = None
    is_active: bool | None = None
    version: int | None = None


class DecisionIn(InputSchema):
    comment: str | None = Field(default=None, max_length=4000)
    checklist: list[str] | None = None
    version: int | None = None


class ReasonIn(InputSchema):
    reason: str | None = Field(default=None, max_length=1000)

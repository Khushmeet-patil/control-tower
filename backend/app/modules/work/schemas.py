from datetime import date

from pydantic import Field

from app.core.schemas import InputSchema

Title = Field(min_length=1, max_length=300)
Url = Field(default=None, max_length=500, pattern=r"^https?://\S+$")
Percent = Field(default=None, ge=0, le=100)


class _WorkItemFields(InputSchema):
    description: str | None = None
    status_id: int | None = None
    priority_id: int | None = None
    category_id: int | None = None
    action_type_id: int | None = None
    severity_id: int | None = None
    unit_id: int | None = None
    function_id: int | None = None
    accountable_id: int | None = None
    responsible_ids: list[int] | None = None
    depends_on_ids: list[int] | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress_manual: int | None = Percent
    weight: int | None = Field(default=None, ge=0, le=1000)
    objective: str | None = None
    risks: str | None = None
    remarks: str | None = None
    evidence_url: str | None = Url
    custom_fields: dict | None = None
    adoption_stage_ids: list[int] | None = None
    adoption_evidence: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=1000)


class WorkItemCreateIn(_WorkItemFields):
    title: str = Title
    item_type_id: int
    parent_id: int | None = None


class WorkItemUpdateIn(_WorkItemFields):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    item_type_id: int | None = None
    parent_id: int | None = None
    version: int | None = None


class AssignmentCreateIn(InputSchema):
    person_id: int
    role_id: int | None = None
    allocation_pct: int = Field(default=0, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    duties: str | None = None
    reason: str | None = None


class AssignmentUpdateIn(InputSchema):
    person_id: int | None = None
    role_id: int | None = None
    allocation_pct: int | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    duties: str | None = None
    version: int | None = None
    reason: str | None = None


class CompleteIn(InputSchema):
    evidence_url: str | None = Url
    actual_end: date | None = None
    remarks: str | None = None
    reason: str | None = Field(default=None, max_length=1000)

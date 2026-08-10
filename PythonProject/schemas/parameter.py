from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.model import ModelVersionRead


class EditableField(BaseModel):
    key: str
    section: str
    field: str
    label: str
    unit: str
    value: str
    minimum: float
    maximum: float
    step: float


class EditableObject(BaseModel):
    target: str
    element_type: str
    fields: list[EditableField]


class EditableGroup(BaseModel):
    id: str
    label: str
    map_layer: str
    objects: list[EditableObject]


class ParameterCatalogResponse(BaseModel):
    version_id: UUID
    groups: list[EditableGroup]


class ParameterChangeInput(BaseModel):
    section: str = Field(max_length=64)
    target: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=100)
    new_value: str = Field(min_length=1, max_length=100)


class CreateAdjustedVersionRequest(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=500)
    created_by: Optional[str] = Field(default=None, max_length=100)
    changes: list[ParameterChangeInput] = Field(min_length=1, max_length=5000)


class AppliedParameterChange(BaseModel):
    operation: str
    section: str
    target: str
    field: str
    old_value: str
    new_value: str
    label: str
    unit: str


class CreateAdjustedVersionResponse(BaseModel):
    version: ModelVersionRead
    changes: list[AppliedParameterChange]

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


class SimulationOptions(BaseModel):
    start_datetime: str
    end_datetime: str
    duration_seconds: int
    report_step_seconds: int
    routing_step_seconds: float
    duration_min_seconds: int
    duration_max_seconds: int
    report_step_min_seconds: int
    max_output_steps: int
    require_report_step_divisible: bool


class RainfallOptions(BaseModel):
    start_seconds: int
    duration_seconds: int
    end_seconds: int
    total_rainfall_mm: float
    peak_rainfall_mm_h: float
    gage_name: str
    series_name: str
    time_step_seconds: int
    peak_ratio: float
    formula: str


class ParameterCatalogResponse(BaseModel):
    version_id: UUID
    groups: list[EditableGroup]
    simulation_options: SimulationOptions
    rainfall_options: RainfallOptions


class ParameterChangeInput(BaseModel):
    section: str = Field(max_length=64)
    target: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=100)
    new_value: str = Field(min_length=1, max_length=100)


class SimulationOptionsInput(BaseModel):
    duration_seconds: int = Field(strict=True)
    report_step_seconds: int = Field(strict=True)


class RainfallOptionsInput(BaseModel):
    start_seconds: int = Field(strict=True, ge=0)
    duration_seconds: int = Field(strict=True, gt=0)
    total_rainfall_mm: float = Field(strict=True, gt=0, allow_inf_nan=False)


class CreateAdjustedVersionRequest(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=500)
    created_by: Optional[str] = Field(default=None, max_length=100)
    changes: list[ParameterChangeInput] = Field(default_factory=list, max_length=5000)
    simulation_options: Optional[SimulationOptionsInput] = None
    rainfall_options: Optional[RainfallOptionsInput] = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.changes and self.simulation_options is None and self.rainfall_options is None:
            raise ValueError("至少需要提交一项参数修改")
        return self


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

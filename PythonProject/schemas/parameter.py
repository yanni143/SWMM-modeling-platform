import math
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class RealRainfallEvent(BaseModel):
    event_id: str
    label: str
    start_datetime: str
    end_datetime: str
    simulation_duration_seconds: int
    report_step_seconds: int
    start_seconds: int
    duration_seconds: int
    total_rainfall_mm: float
    peak_rainfall_mm_h: float
    time_step_seconds: int
    values_mm: list[float]


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
    mode: Literal["design", "real", "custom"] = "design"
    event_id: str | None = None
    read_only: bool = False
    real_event: RealRainfallEvent | None = None
    values_mm: list[float]
    series_checksum: str


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
    model_config = ConfigDict(extra="forbid")
    mode: Literal["design", "real", "custom"] = "design"
    event_id: str | None = Field(default=None, max_length=100)
    start_seconds: int | None = Field(default=None, strict=True, ge=0)
    duration_seconds: int | None = Field(default=None, strict=True, gt=0)
    total_rainfall_mm: float | None = Field(default=None, strict=True, gt=0, allow_inf_nan=False)
    time_step_seconds: int | None = Field(default=None, strict=True, gt=0)
    values_mm: list[Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]] | None = Field(
        default=None, min_length=1, max_length=10000
    )

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "design":
            if self.event_id is not None:
                raise ValueError("模拟降雨不能指定真实降雨事件")
            if any(
                value is None
                for value in (self.start_seconds, self.duration_seconds, self.total_rainfall_mm)
            ):
                raise ValueError("模拟降雨必须提供开始时间、时长和总雨量")
            if self.values_mm is not None or self.time_step_seconds is not None:
                raise ValueError("芝加哥雨型不接受自定义序列")
        elif self.mode == "real":
            if not self.event_id:
                raise ValueError("请选择真实降雨事件")
            if any(
                value is not None
                for value in (
                    self.duration_seconds,
                    self.total_rainfall_mm,
                    self.time_step_seconds,
                    self.values_mm,
                )
            ):
                raise ValueError("真实降雨序列不可修改；如需编辑请使用自定义序列")
        else:
            if (
                self.start_seconds is None
                or self.time_step_seconds is None
                or self.values_mm is None
            ):
                raise ValueError("自定义降雨必须提供开始时间、记录间隔和分段雨量序列")
            if any(
                value is not None
                for value in (
                    self.event_id,
                    self.duration_seconds,
                    self.total_rainfall_mm,
                )
            ):
                raise ValueError("自定义降雨的时长和总雨量由序列计算")
            if any(not math.isfinite(value) or value < 0 for value in self.values_mm):
                raise ValueError("分段雨量必须是不小于 0 的有限数值")
        return self


class RainfallPreviewRequest(BaseModel):
    study_area: Literal["LC", "JJ"]
    simulation_duration_seconds: int = Field(strict=True, gt=0)
    rainfall_options: RainfallOptionsInput


class RainfallPreview(BaseModel):
    mode: Literal["design", "real", "custom"]
    event_id: str | None
    start_seconds: int
    duration_seconds: int
    end_seconds: int
    time_step_seconds: int
    values_mm: list[float]
    total_rainfall_mm: float
    peak_rainfall_mm_h: float
    series_checksum: str


class CreateAdjustedVersionRequest(BaseModel):
    summary: str | None = Field(default=None, max_length=500)
    created_by: str | None = Field(default=None, max_length=100)
    changes: list[ParameterChangeInput] = Field(default_factory=list, max_length=5000)
    simulation_options: SimulationOptionsInput | None = None
    rainfall_options: RainfallOptionsInput | None = None

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

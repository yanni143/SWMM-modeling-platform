from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from schemas.model import GeoJsonLayer


class RunResponse(BaseModel):
    run_id: UUID
    model_version_id: UUID
    version: int
    status: str
    layers: list[GeoJsonLayer]
    artifacts: list[dict[str, Any]]


class ModelResultSummary(BaseModel):
    version_id: UUID
    version: int
    effective_run_id: UUID
    created_at: datetime
    finished_at: datetime | None


class VersionResultLayers(BaseModel):
    version_id: UUID
    version: int
    effective_run_id: UUID
    created_at: datetime
    finished_at: datetime | None
    layers: list[GeoJsonLayer]


class TimelineStep(BaseModel):
    time_index: int
    timestamp: str | None


class ResultValueRange(BaseModel):
    minimum: float
    maximum: float


class ResultFieldMetadata(BaseModel):
    unit: str | None = None


class ResultTimeSeries(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    field_metadata: dict[str, ResultFieldMetadata]


class ResultTimeline(BaseModel):
    version_id: UUID
    version: int
    effective_run_id: UUID
    steps: list[TimelineStep]
    result_ranges: dict[str, dict[str, ResultValueRange]]
    result_metadata: dict[str, dict[str, ResultFieldMetadata]]

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


class DepthTimeline(BaseModel):
    version_id: UUID
    version: int
    effective_run_id: UUID
    steps: list[TimelineStep]
    max_depths: dict[str, float]

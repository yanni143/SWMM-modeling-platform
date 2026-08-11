from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ModelVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: UUID
    parent_version_id: Optional[UUID]
    version: int
    checksum: Optional[str]
    size_bytes: Optional[int]
    change_summary: Optional[dict[str, Any]]
    created_by: Optional[str]
    created_at: datetime


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class ModelListItem(ModelRead):
    version_count: int
    latest_version: Optional[int]


class SectionSummary(BaseModel):
    name: str
    record_count: int
    editable: bool
    fields: list[str]


class VersionSectionsResponse(BaseModel):
    version_id: UUID
    sections: list[SectionSummary]


class SectionDetailResponse(BaseModel):
    version_id: UUID
    section: dict[str, Any]


class GeoJsonLayer(BaseModel):
    id: str
    name: str
    geometry_type: str
    source: str
    source_crs: Optional[str] = None
    display_crs: str = "EPSG:4326"
    geojson: dict[str, Any]


class VersionLayersResponse(BaseModel):
    version_id: UUID
    layers: list[GeoJsonLayer]

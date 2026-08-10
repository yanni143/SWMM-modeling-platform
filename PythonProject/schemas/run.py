from typing import Any
from uuid import UUID

from pydantic import BaseModel

from schemas.model import GeoJsonLayer


class RunResponse(BaseModel):
    run_id: UUID
    status: str
    layers: list[GeoJsonLayer]
    artifacts: list[dict[str, Any]]

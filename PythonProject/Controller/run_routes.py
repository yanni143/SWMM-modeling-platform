from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from minio.error import S3Error
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from database.session import get_db
from schemas.model import GeoJsonLayer
from schemas.run import RunResponse
from Service.SimulationService import SimulationRunError, SimulationService


router = APIRouter(prefix="/api", tags=["runs"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, (S3Error, Urllib3HTTPError, ConnectionError, TimeoutError, OSError)):
        return HTTPException(status_code=503, detail="MinIO 对象存储当前不可用")
    if isinstance(exc, SimulationRunError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="工程运行服务执行失败")


@router.post("/model-versions/{version_id}/runs", response_model=RunResponse)
def run_version(version_id: UUID, session: Session = Depends(get_db)) -> RunResponse:
    service = SimulationService()
    try:
        run, layers = service.run_version(session, version_id)
        return RunResponse(
            run_id=run.id,
            status=run.status,
            layers=[GeoJsonLayer.model_validate(layer) for layer in layers],
            artifacts=service.artifact_payload(run),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/runs/{run_id}/layers", response_model=list[GeoJsonLayer])
def get_run_layers(run_id: UUID, session: Session = Depends(get_db)) -> list[GeoJsonLayer]:
    try:
        return [
            GeoJsonLayer.model_validate(layer)
            for layer in SimulationService().list_layer_artifacts(session, run_id)
        ]
    except Exception as exc:
        raise _translate(exc) from exc

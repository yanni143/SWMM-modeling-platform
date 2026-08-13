from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from minio.error import S3Error
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from database.session import get_db
from schemas.model import GeoJsonLayer
from schemas.run import (
    DepthTimeline,
    ModelResultSummary,
    ResultTimeline,
    ResultTimeSeries,
    RunResponse,
    VersionResultLayers,
)
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
            model_version_id=run.model_version_id,
            version=run.model_version.version,
            status=run.status,
            layers=[GeoJsonLayer.model_validate(layer) for layer in layers],
            artifacts=service.artifact_payload(run),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/model-results", response_model=list[ModelResultSummary])
def list_model_results(session: Session = Depends(get_db)) -> list[ModelResultSummary]:
    try:
        return [
            ModelResultSummary(
                version_id=version.id,
                version=version.version,
                effective_run_id=run.id,
                created_at=run.created_at,
                finished_at=run.finished_at,
            )
            for run, version in SimulationService().list_latest_successful_results(session)
        ]
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/layers",
    response_model=VersionResultLayers,
)
def get_latest_version_layers(
    version_id: UUID, session: Session = Depends(get_db)
) -> VersionResultLayers:
    try:
        run, version, layers = SimulationService().get_latest_version_layers(session, version_id)
        return VersionResultLayers(
            version_id=version.id,
            version=version.version,
            effective_run_id=run.id,
            created_at=run.created_at,
            finished_at=run.finished_at,
            layers=[GeoJsonLayer.model_validate(layer) for layer in layers],
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/timeseries",
    response_model=ResultTimeSeries,
)
def get_latest_version_timeseries(
    version_id: UUID,
    layer_id: str = Query(min_length=1, max_length=100),
    feature_name: str = Query(min_length=1, max_length=200),
    session: Session = Depends(get_db),
) -> ResultTimeSeries:
    try:
        return ResultTimeSeries.model_validate(
            SimulationService().get_latest_version_timeseries(
                session, version_id, layer_id, feature_name
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/timeline",
    response_model=ResultTimeline,
)
def get_latest_version_result_timeline(
    version_id: UUID, session: Session = Depends(get_db)
) -> ResultTimeline:
    try:
        run, version, timeline = SimulationService().get_latest_version_result_timeline(
            session, version_id
        )
        return ResultTimeline(
            version_id=version.id,
            version=version.version,
            effective_run_id=run.id,
            **timeline,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/steps/{time_index}",
    response_model=VersionResultLayers,
)
def get_latest_version_result_step(
    version_id: UUID,
    time_index: int,
    session: Session = Depends(get_db),
) -> VersionResultLayers:
    try:
        run, version, layers = SimulationService().get_latest_version_result_step(
            session, version_id, time_index
        )
        return VersionResultLayers(
            version_id=version.id,
            version=version.version,
            effective_run_id=run.id,
            created_at=run.created_at,
            finished_at=run.finished_at,
            layers=[GeoJsonLayer.model_validate(layer) for layer in layers],
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/depth-timeline",
    response_model=DepthTimeline,
)
def get_latest_version_depth_timeline(
    version_id: UUID, session: Session = Depends(get_db)
) -> DepthTimeline:
    try:
        run, version, timeline = SimulationService().get_latest_version_depth_timeline(
            session, version_id
        )
        return DepthTimeline(
            version_id=version.id,
            version=version.version,
            effective_run_id=run.id,
            **timeline,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/model-versions/{version_id}/latest-result/depth-steps/{time_index}",
    response_model=VersionResultLayers,
)
def get_latest_version_depth_step(
    version_id: UUID,
    time_index: int,
    session: Session = Depends(get_db),
) -> VersionResultLayers:
    try:
        run, version, layers = SimulationService().get_latest_version_depth_step(
            session, version_id, time_index
        )
        return VersionResultLayers(
            version_id=version.id,
            version=version.version,
            effective_run_id=run.id,
            created_at=run.created_at,
            finished_at=run.finished_at,
            layers=[GeoJsonLayer.model_validate(layer) for layer in layers],
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

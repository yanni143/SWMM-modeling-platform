from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from database.session import get_db
from schemas.model import (
    ModelListItem,
    ModelRead,
    ModelVersionRead,
    SectionDetailResponse,
    SectionSummary,
    VersionLayersResponse,
    VersionSectionsResponse,
)
from schemas.parameter import (
    AppliedParameterChange,
    CreateAdjustedVersionRequest,
    CreateAdjustedVersionResponse,
    EditableGroup,
    ParameterCatalogResponse,
)
from Service.ModelService import ModelNotFoundError, ModelService, SectionNotFoundError
from Tools.InpTools.InpValidator import InvalidInpFile

router = APIRouter(prefix="/api", tags=["projects"])


def translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ModelNotFoundError, SectionNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, InvalidInpFile):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (S3Error, Urllib3HTTPError, ConnectionError, TimeoutError, OSError)):
        return HTTPException(status_code=503, detail="MinIO 对象存储当前不可用")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="工程服务执行失败")

@router.get("/models", response_model=list[ModelListItem])
def list_models(session: Session = Depends(get_db)) -> list[dict]:
    return ModelService().list_models(session)


@router.get("/models/{model_id}", response_model=ModelRead)
def get_model(model_id: UUID, session: Session = Depends(get_db)) -> ModelRead:
    try:
        return ModelRead.model_validate(ModelService().get_model(session, model_id))
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get("/models/{model_id}/versions", response_model=list[ModelVersionRead])
def list_versions(model_id: UUID, session: Session = Depends(get_db)) -> list[ModelVersionRead]:
    try:
        return [
            ModelVersionRead.model_validate(version)
            for version in ModelService().list_versions(session, model_id)
        ]
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get("/model-versions/{version_id}/sections", response_model=VersionSectionsResponse)
def list_version_sections(
    version_id: UUID, session: Session = Depends(get_db)
) -> VersionSectionsResponse:
    try:
        sections = ModelService().list_sections(session, version_id)
        return VersionSectionsResponse(
            version_id=version_id,
            sections=[SectionSummary.model_validate(item) for item in sections],
        )
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get(
    "/model-versions/{version_id}/sections/{section_name}",
    response_model=SectionDetailResponse,
)
def get_version_section(
    version_id: UUID,
    section_name: str,
    session: Session = Depends(get_db),
) -> SectionDetailResponse:
    try:
        section = ModelService().get_section(session, version_id, section_name)
        return SectionDetailResponse(version_id=version_id, section=section)
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get(
    "/model-versions/{version_id}/layers",
    response_model=VersionLayersResponse,
)
def get_version_layers(
    version_id: UUID, session: Session = Depends(get_db)
) -> VersionLayersResponse:
    try:
        layers = ModelService().get_geometry_layers(session, version_id)
        return VersionLayersResponse(version_id=version_id, layers=layers)
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get(
    "/model-versions/{version_id}/editable-parameters",
    response_model=ParameterCatalogResponse,
)
def get_editable_parameters(
    version_id: UUID, session: Session = Depends(get_db)
) -> ParameterCatalogResponse:
    try:
        groups = ModelService().get_parameter_catalog(session, version_id)
        return ParameterCatalogResponse(
            version_id=version_id,
            groups=[EditableGroup.model_validate(group) for group in groups],
        )
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.post(
    "/model-versions/{version_id}/versions",
    response_model=CreateAdjustedVersionResponse,
    status_code=201,
)
def create_adjusted_version(
    version_id: UUID,
    payload: CreateAdjustedVersionRequest,
    session: Session = Depends(get_db),
) -> CreateAdjustedVersionResponse:
    try:
        version, changes = ModelService().create_adjusted_version(
            session=session,
            parent_version_id=version_id,
            changes=[change.model_dump() for change in payload.changes],
            summary=payload.summary,
            created_by=payload.created_by,
        )
        return CreateAdjustedVersionResponse(
            version=ModelVersionRead.model_validate(version),
            changes=[AppliedParameterChange.model_validate(change) for change in changes],
        )
    except Exception as exc:
        raise translate_service_error(exc) from exc


@router.get("/model-versions/{version_id}/download")
def download_version(
    version_id: UUID, session: Session = Depends(get_db)
) -> StreamingResponse:
    try:
        service = ModelService()
        version = service.get_version(session, version_id)
        response = service.storage.client.get_object(
            version.inp_bucket,
            version.inp_object_key,
        )

        def stream_object():
            try:
                yield from response.stream(amt=1024 * 1024)
            finally:
                response.close()
                response.release_conn()

        return StreamingResponse(
            stream_object(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="model-v{version.version}.inp"'
            },
        )
    except Exception as exc:
        raise translate_service_error(exc) from exc

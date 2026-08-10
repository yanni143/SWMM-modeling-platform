import tempfile
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from minio.error import S3Error
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from config import get_settings
from database.session import get_db
from schemas.model import (
    DownloadUrlResponse,
    ModelImportResponse,
    ModelListItem,
    ModelRead,
    ModelVersionRead,
    SectionDetailResponse,
    SectionSummary,
    VersionSectionsResponse,
)
from Service.ModelService import (
    ModelNameConflictError,
    ModelNotFoundError,
    ModelService,
    SectionNotFoundError,
)
from Tools.InpTools.InpInspector import summarize_sections
from Tools.InpTools.InpValidator import InvalidInpFile


router = APIRouter(prefix="/api", tags=["models"])
settings = get_settings()


async def save_upload(upload: UploadFile, destination: Path) -> int:
    filename = upload.filename or ""
    if Path(filename).suffix.lower() != ".inp":
        raise HTTPException(status_code=422, detail="仅支持上传 .inp 文件")

    size = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_inp_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"INP 文件不能超过 {settings.max_inp_upload_bytes} 字节",
                )
            output.write(chunk)

    if size == 0:
        raise HTTPException(status_code=422, detail="上传文件为空")
    return size


def translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ModelNameConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (ModelNotFoundError, SectionNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, InvalidInpFile):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (S3Error, Urllib3HTTPError, ConnectionError, TimeoutError, OSError)):
        return HTTPException(status_code=503, detail="MinIO 对象存储当前不可用")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="模型服务执行失败")


@router.post("/models", response_model=ModelImportResponse, status_code=201)
async def import_model(
    name: Annotated[str, Form(min_length=1, max_length=200)],
    file: Annotated[UploadFile, File()],
    description: Annotated[Optional[str], Form(max_length=2000)] = None,
    created_by: Annotated[Optional[str], Form(max_length=100)] = None,
    session: Session = Depends(get_db),
) -> ModelImportResponse:
    runtime_dir = settings.resolved_runtime_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="inp-upload-", dir=runtime_dir) as directory:
            inp_path = Path(directory) / "model.inp"
            await save_upload(file, inp_path)
            model, version, validation = ModelService().import_inp(
                session=session,
                name=name,
                description=description,
                inp_path=inp_path,
                original_filename=file.filename or "model.inp",
                created_by=created_by,
            )
        return ModelImportResponse(
            model=ModelRead.model_validate(model),
            version=ModelVersionRead.model_validate(version),
            sections=[
                SectionSummary.model_validate(item)
                for item in summarize_sections(validation.sections)
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise translate_service_error(exc) from exc
    finally:
        await file.close()


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
    "/model-versions/{version_id}/download-url",
    response_model=DownloadUrlResponse,
)
def get_version_download_url(
    version_id: UUID, session: Session = Depends(get_db)
) -> DownloadUrlResponse:
    try:
        url = ModelService().get_download_url(session, version_id)
        return DownloadUrlResponse(
            version_id=version_id,
            expires_seconds=settings.presigned_url_expires_seconds,
            url=url,
        )
    except Exception as exc:
        raise translate_service_error(exc) from exc

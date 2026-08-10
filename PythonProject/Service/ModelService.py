import tempfile
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import get_settings
from models.domain import ModelVersion, SwmmModel
from storage.artifact_storage import ArtifactStorageService
from Tools.InpTools.InpInspector import inspect_section, summarize_sections
from Tools.InpTools.InpGeoJson import build_geojson_layers
from Tools.InpTools.InpValidator import InpValidationResult, validate_inp_file


class ModelNotFoundError(LookupError):
    pass


class ModelNameConflictError(ValueError):
    pass


class SectionNotFoundError(LookupError):
    pass


class ModelService:
    def __init__(self, storage: Optional[ArtifactStorageService] = None) -> None:
        self.settings = get_settings()
        self.storage = storage or ArtifactStorageService()

    def import_inp(
        self,
        session: Session,
        name: str,
        description: Optional[str],
        inp_path: str | Path,
        original_filename: str,
        created_by: Optional[str] = None,
    ) -> tuple[SwmmModel, ModelVersion, InpValidationResult]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("工程名称不能为空")

        existing = session.scalar(select(SwmmModel.id).where(SwmmModel.name == clean_name))
        if existing:
            raise ModelNameConflictError(f"工程名称已存在：{clean_name}")

        validation = validate_inp_file(inp_path)
        model_id = uuid.uuid4()
        version_id = uuid.uuid4()
        stored = self.storage.upload_model_version(inp_path, model_id, version_id)

        model = SwmmModel(
            id=model_id,
            name=clean_name,
            description=description.strip() if description else None,
            dataset_id=None,
            status="active",
        )
        version = ModelVersion(
            id=version_id,
            model_id=model_id,
            version=1,
            inp_bucket=stored.bucket,
            inp_object_key=stored.object_key,
            checksum=stored.checksum,
            size_bytes=stored.size_bytes,
            change_summary={
                "source": "user_upload",
                "original_filename": original_filename,
                "section_count": len(validation.sections),
            },
            created_by=created_by,
        )

        try:
            session.add_all([model, version])
            session.commit()
            session.refresh(model)
            session.refresh(version)
        except IntegrityError as exc:
            session.rollback()
            self._delete_uploaded_object(stored.object_key)
            raise ModelNameConflictError(f"工程名称已存在：{clean_name}") from exc
        except Exception:
            session.rollback()
            self._delete_uploaded_object(stored.object_key)
            raise

        return model, version, validation

    def list_models(self, session: Session) -> list[dict]:
        version_count = func.count(ModelVersion.id)
        latest_version = func.max(ModelVersion.version)
        rows = session.execute(
            select(SwmmModel, version_count, latest_version)
            .outerjoin(ModelVersion, ModelVersion.model_id == SwmmModel.id)
            .group_by(SwmmModel.id)
            .order_by(SwmmModel.created_at.desc())
        ).all()
        return [
            {
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "status": model.status,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
                "version_count": count,
                "latest_version": latest,
            }
            for model, count, latest in rows
        ]

    def get_model(self, session: Session, model_id: uuid.UUID) -> SwmmModel:
        model = session.get(SwmmModel, model_id)
        if not model:
            raise ModelNotFoundError("工程不存在")
        return model

    def list_versions(self, session: Session, model_id: uuid.UUID) -> list[ModelVersion]:
        self.get_model(session, model_id)
        return list(
            session.scalars(
                select(ModelVersion)
                .where(ModelVersion.model_id == model_id)
                .order_by(ModelVersion.version.desc())
            )
        )

    def get_version(self, session: Session, version_id: uuid.UUID) -> ModelVersion:
        version = session.get(ModelVersion, version_id)
        if not version:
            raise ModelNotFoundError("工程版本不存在")
        return version

    def list_sections(self, session: Session, version_id: uuid.UUID) -> list[dict]:
        version, validation = self._download_and_validate(session, version_id)
        return summarize_sections(validation.sections)

    def get_section(self, session: Session, version_id: uuid.UUID, section: str) -> dict:
        version, validation = self._download_and_validate(session, version_id)
        section_name = section.upper()
        if section_name not in validation.sections:
            raise SectionNotFoundError(f"INP 中不存在 [{section_name}] 节")
        return inspect_section(section_name, validation.sections[section_name])

    def get_geometry_layers(self, session: Session, version_id: uuid.UUID) -> list[dict]:
        _, validation = self._download_and_validate(session, version_id)
        return build_geojson_layers(
            validation.sections,
            source_crs=self.settings.swmm_input_crs,
        )

    def get_download_url(self, session: Session, version_id: uuid.UUID) -> str:
        version = self.get_version(session, version_id)
        return self.storage.presigned_url(
            version.inp_object_key,
            bucket=version.inp_bucket,
        )

    def _download_and_validate(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[ModelVersion, InpValidationResult]:
        version = self.get_version(session, version_id)
        runtime_dir = self.settings.resolved_runtime_dir
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="inp-inspect-", dir=runtime_dir) as directory:
            path = Path(directory) / "model.inp"
            self.storage.download_to(
                version.inp_object_key,
                path,
                bucket=version.inp_bucket,
            )
            validation = validate_inp_file(path)
        return version, validation

    def _delete_uploaded_object(self, object_key: str) -> None:
        try:
            self.storage.delete(object_key)
        except Exception:
            # Keep the original database error; orphan cleanup can be retried separately.
            pass

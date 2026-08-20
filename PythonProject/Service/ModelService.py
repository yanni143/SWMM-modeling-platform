import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import get_settings
from models.domain import ModelParameterChange, ModelVersion, SwmmModel
from storage.artifact_storage import ArtifactStorageService
from Tools.InpTools.InpFileHandler import INPFileHandler
from Tools.InpTools.InpGeoJson import build_geojson_layers
from Tools.InpTools.InpInspector import inspect_section, summarize_sections
from Tools.InpTools.InpParameterEditor import (
    apply_parameter_changes,
    apply_simulation_options,
    build_parameter_catalog,
    build_simulation_options,
)
from Tools.InpTools.InpRainfallEditor import apply_rainfall_options, build_rainfall_options
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.InpValidator import InpValidationResult, validate_inp_file


class ModelNotFoundError(LookupError):
    pass


class SectionNotFoundError(LookupError):
    pass


class ModelService:
    def __init__(self, storage: Optional[ArtifactStorageService] = None) -> None:
        self.settings = get_settings()
        self.storage = storage or ArtifactStorageService()

    def ensure_fixed_model(
        self, session: Session
    ) -> tuple[SwmmModel, ModelVersion, InpValidationResult]:
        """Create the built-in study area and its immutable V1 exactly once."""
        inp_path = self.settings.resolved_fixed_inp_path
        if not inp_path.is_file():
            raise FileNotFoundError(f"系统内置 INP 不存在：{inp_path}")
        validation = validate_inp_file(inp_path)

        model = session.get(SwmmModel, self.settings.fixed_model_id)
        if model:
            version = session.get(ModelVersion, self.settings.fixed_version_id)
            if not version or version.model_id != model.id or version.version != 1:
                raise RuntimeError("固定研究区存在，但基线 V1 记录缺失或不一致")
            return model, version, validation

        name_conflict = session.scalar(
            select(SwmmModel.id).where(SwmmModel.name == self.settings.fixed_model_name)
        )
        if name_conflict:
            raise RuntimeError("固定研究区名称已被其他工程占用")

        stored = self.storage.upload_model_version(
            inp_path,
            self.settings.fixed_model_id,
            self.settings.fixed_version_id,
        )
        model = SwmmModel(
            id=self.settings.fixed_model_id,
            name=self.settings.fixed_model_name,
            description=self.settings.fixed_model_description,
            dataset_id="fixed-study-area",
            status="active",
        )
        version = ModelVersion(
            id=self.settings.fixed_version_id,
            model_id=model.id,
            version=1,
            inp_bucket=stored.bucket,
            inp_object_key=stored.object_key,
            checksum=stored.checksum,
            size_bytes=stored.size_bytes,
            change_summary={
                "source": "system_seed",
                "original_filename": inp_path.name,
                "section_count": len(validation.sections),
            },
            created_by="system",
        )
        try:
            session.add_all([model, version])
            session.commit()
            session.refresh(model)
            session.refresh(version)
        except IntegrityError as exc:
            session.rollback()
            raise RuntimeError("固定研究区初始化发生数据冲突") from exc
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
            .where(SwmmModel.id == self.settings.fixed_model_id)
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
        if model_id != self.settings.fixed_model_id:
            raise ModelNotFoundError("工程不存在")
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
        version = session.scalar(
            select(ModelVersion).where(
                ModelVersion.id == version_id,
                ModelVersion.model_id == self.settings.fixed_model_id,
            )
        )
        if not version:
            raise ModelNotFoundError("工程版本不存在")
        return version

    def list_sections(self, session: Session, version_id: uuid.UUID) -> list[dict]:
        _, validation = self._download_and_validate(session, version_id)
        return summarize_sections(validation.sections)

    def get_section(self, session: Session, version_id: uuid.UUID, section: str) -> dict:
        _, validation = self._download_and_validate(session, version_id)
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

    def get_parameter_catalog(self, session: Session, version_id: uuid.UUID) -> dict:
        _, validation = self._download_and_validate(session, version_id)
        simulation_options = build_simulation_options(validation.sections, self.settings)
        return {
            "groups": build_parameter_catalog(validation.sections),
            "simulation_options": simulation_options,
            "rainfall_options": build_rainfall_options(
                validation.sections, simulation_options["duration_seconds"]
            ),
        }

    def create_adjusted_version(
        self,
        session: Session,
        parent_version_id: uuid.UUID,
        changes: list[dict[str, str]],
        simulation_options: Optional[dict[str, int]] = None,
        rainfall_options: Optional[dict[str, Any]] = None,
        summary: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> tuple[ModelVersion, list[dict]]:
        parent = self.get_version(session, parent_version_id)
        model = session.get(SwmmModel, parent.model_id, with_for_update=True)
        if not model:
            raise ModelNotFoundError("工程不存在")

        runtime_dir = self.settings.resolved_runtime_dir
        runtime_dir.mkdir(parents=True, exist_ok=True)
        stored = None
        with tempfile.TemporaryDirectory(prefix="inp-adjust-", dir=runtime_dir) as directory:
            source_path = Path(directory) / "source.inp"
            target_path = Path(directory) / "model.inp"
            self.storage.download_to(
                parent.inp_object_key,
                source_path,
                bucket=parent.inp_bucket,
            )
            content, _ = INPFileHandler.read_file(str(source_path))
            if not content:
                raise ValueError("无法读取父版本 INP")
            original_sections = INPParser.parse(content)
            original_simulation = build_simulation_options(original_sections, self.settings)
            original_rainfall = build_rainfall_options(
                original_sections, original_simulation["duration_seconds"]
            )
            adjusted_content = content
            applied = []
            if changes:
                adjusted_content, parameter_changes = apply_parameter_changes(
                    adjusted_content, changes
                )
                applied.extend(parameter_changes)
            if simulation_options:
                parsed_sections = INPParser.parse(adjusted_content)
                adjusted_content, option_changes = apply_simulation_options(
                    adjusted_content,
                    parsed_sections,
                    simulation_options,
                    self.settings,
                )
                applied.extend(option_changes)
            parsed_sections = INPParser.parse(adjusted_content)
            effective_simulation = build_simulation_options(parsed_sections, self.settings)
            requested_rainfall = rainfall_options or {
                "start_seconds": original_rainfall["start_seconds"],
                "duration_seconds": original_rainfall["duration_seconds"],
                "total_rainfall_mm": original_rainfall["total_rainfall_mm"],
            }
            if rainfall_options or (
                original_rainfall["end_seconds"] > effective_simulation["duration_seconds"]
            ):
                adjusted_content, rainfall_changes = apply_rainfall_options(
                    adjusted_content,
                    parsed_sections,
                    requested_rainfall,
                    effective_simulation["duration_seconds"],
                )
                applied.extend(rainfall_changes)
            if not applied:
                raise ValueError("提交的参数没有发生变化")
            message = INPFileHandler.write_file(str(target_path), adjusted_content)
            if message.startswith("错误"):
                raise OSError(message)
            validate_inp_file(target_path)

            latest = session.scalar(
                select(func.max(ModelVersion.version)).where(ModelVersion.model_id == model.id)
            ) or 0
            version_id = uuid.uuid4()
            stored = self.storage.upload_model_version(target_path, model.id, version_id)
            version = ModelVersion(
                id=version_id,
                model_id=model.id,
                parent_version_id=parent.id,
                version=latest + 1,
                inp_bucket=stored.bucket,
                inp_object_key=stored.object_key,
                checksum=stored.checksum,
                size_bytes=stored.size_bytes,
                change_summary={
                    "source": "parameter_adjustment",
                    "summary": summary or f"调整 {len(applied)} 项常用参数",
                    "change_count": len(applied),
                },
                created_by=created_by,
            )
            session.add(version)
            session.flush()
            session.add_all(
                [
                    ModelParameterChange(
                        id=uuid.uuid4(),
                        version_id=version.id,
                        operation=item["operation"],
                        section=item["section"],
                        target=item["target"],
                        field=item["field"],
                        old_value=item["old_value"],
                        new_value=item["new_value"],
                    )
                    for item in applied
                ]
            )
            model.updated_at = datetime.now(timezone.utc)
            try:
                session.commit()
                session.refresh(version)
            except Exception:
                session.rollback()
                if stored:
                    self._delete_uploaded_object(stored.object_key)
                raise
        return version, applied

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

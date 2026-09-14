import json
import math
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import get_settings
from models.domain import ModelVersion, RunArtifact, SimulationRun, SwmmModel
from Service.LisfloodExportService import LisfloodExportService
from Service.ModelService import ModelNotFoundError, ModelService
from Service.SWMMService import SwmmService
from storage.artifact_storage import ArtifactStorageService, StoredObject
from swmm_core.result_geojson import (
    latest_time_step_layers,
    parse_result_layers,
    write_result_layers,
)
from Tools.InpTools.InpInspector import data_lines
from Tools.InpTools.InpValidator import validate_inp_file


class SimulationRunError(RuntimeError):
    pass


class SimulationService:
    LAYER_DEFINITIONS = {
        "result-subcatchments.geojson": (
            "result-subcatchments",
            "子汇水区模拟结果",
            "fill",
        ),
        "result-conduits.geojson": ("result-conduits", "管线模拟结果", "line"),
        "result-nodes.geojson": ("result-nodes", "节点模拟结果", "circle"),
    }
    FLOW_UNIT_LABELS = {
        "CFS": "ft³/s",
        "GPM": "gal/min",
        "MGD": "MGD",
        "CMS": "m³/s",
        "LPS": "L/s",
        "MLD": "ML/d",
    }

    def __init__(self, storage: ArtifactStorageService | None = None) -> None:
        self.settings = get_settings()
        self.storage = storage or ArtifactStorageService()

    def run_version(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[SimulationRun, list[dict]]:
        try:
            version = ModelService(storage=self.storage).get_version(session, version_id)
        except ModelNotFoundError as exc:
            raise SimulationRunError("工程版本不存在") from exc

        run = SimulationRun(
            id=uuid.uuid4(),
            model_id=version.model_id,
            model_version_id=version.id,
            status="running",
            progress=5,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()

        runtime = self.settings.resolved_runtime_dir
        runtime.mkdir(parents=True, exist_ok=True)
        layers: list[dict] = []
        try:
            with tempfile.TemporaryDirectory(prefix=f"run-{run.id}-", dir=runtime) as directory:
                workdir = Path(directory)
                inp_path = workdir / "model.inp"
                self.storage.download_to(
                    version.inp_object_key, inp_path, bucket=version.inp_bucket
                )
                self._record_artifact(
                    session, run, "input", self.storage.upload_run_input(inp_path, run.id)
                )
                run.progress = 20
                session.commit()

                result = SwmmService.run_model(str(inp_path))
                if not (
                    result.get("success") and result.get("out_exists") and result.get("rpt_exists")
                ):
                    raise SimulationRunError(result.get("message", "SWMM 未生成 OUT 文件"))

                out_path = Path(result["out_file"])
                rpt_path = Path(result["rpt_file"])
                layers = parse_result_layers(inp_path, out_path)
                visual_paths = write_result_layers(layers, workdir / "visual")
                run.progress = 75
                session.commit()

                self._record_artifact(
                    session,
                    run,
                    "raw_out",
                    self.storage.upload_run_artifact(out_path, run.id, "raw"),
                )
                if rpt_path.is_file():
                    self._record_artifact(
                        session,
                        run,
                        "report",
                        self.storage.upload_run_artifact(rpt_path, run.id, "raw"),
                    )
                for path in visual_paths:
                    self._record_artifact(
                        session,
                        run,
                        "visual",
                        self.storage.upload_run_artifact(path, run.id, "visual"),
                    )

                model = session.get(SwmmModel, version.model_id)
                if not model:
                    raise SimulationRunError("运行所属研究区不存在")
                lisflood_path = LisfloodExportService().write_without_sub(
                    inp_path,
                    rpt_path,
                    workdir / "lisflood",
                    model.dataset_id or model.name,
                )
                self._record_artifact(
                    session,
                    run,
                    "lisflood",
                    self.storage.upload_run_artifact(lisflood_path, run.id, "lisflood"),
                )
                run.progress = 90
                session.commit()

            run.status = "success"
            run.progress = 100
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(run)
            return run, latest_time_step_layers(layers)
        except Exception as exc:
            session.rollback()
            run = session.get(SimulationRun, run.id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)[:4000]
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
            if isinstance(exc, SimulationRunError):
                raise
            raise SimulationRunError(f"工程运行失败：{exc}") from exc

    def list_layer_artifacts(self, session: Session, run_id: uuid.UUID) -> list[dict]:
        run = session.get(SimulationRun, run_id)
        if not run:
            raise SimulationRunError("运行记录不存在")
        return self._load_layer_artifacts(session, run)

    def list_latest_successful_results(
        self, session: Session, model_id: uuid.UUID | None = None
    ) -> list[tuple[SimulationRun, ModelVersion]]:
        rank = (
            func.row_number()
            .over(
                partition_by=SimulationRun.model_version_id,
                order_by=(
                    SimulationRun.started_at.desc(),
                    SimulationRun.created_at.desc(),
                    SimulationRun.id.desc(),
                ),
            )
            .label("result_rank")
        )
        conditions = [SimulationRun.status == "success"]
        if model_id is not None:
            conditions.append(SimulationRun.model_id == model_id)
        ranked = select(SimulationRun.id.label("run_id"), rank).where(*conditions).subquery()
        return list(
            session.execute(
                select(SimulationRun, ModelVersion)
                .join(ranked, ranked.c.run_id == SimulationRun.id)
                .join(ModelVersion, ModelVersion.id == SimulationRun.model_version_id)
                .where(ranked.c.result_rank == 1)
                .order_by(ModelVersion.version.desc())
            ).all()
        )

    def get_latest_successful_result(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[SimulationRun, ModelVersion]:
        try:
            version = ModelService(storage=self.storage).get_version(session, version_id)
        except ModelNotFoundError as exc:
            raise SimulationRunError("工程版本不存在") from exc
        run = session.scalar(
            select(SimulationRun)
            .where(
                SimulationRun.model_version_id == version.id,
                SimulationRun.status == "success",
            )
            .order_by(
                SimulationRun.started_at.desc(),
                SimulationRun.created_at.desc(),
                SimulationRun.id.desc(),
            )
            .limit(1)
        )
        if not run:
            raise SimulationRunError("该版本还没有成功的模拟结果")
        return run, version

    def get_latest_version_layers(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[SimulationRun, ModelVersion, list[dict]]:
        run, version = self.get_latest_successful_result(session, version_id)
        return run, version, self._load_layer_artifacts(session, run)

    def get_lisflood_artifact(self, session: Session, run_id: uuid.UUID) -> RunArtifact:
        run = session.get(SimulationRun, run_id)
        if not run:
            raise SimulationRunError("运行记录不存在")
        artifact = session.scalar(
            select(RunArtifact)
            .where(RunArtifact.run_id == run.id, RunArtifact.artifact_type == "lisflood")
            .order_by(RunArtifact.created_at.desc())
            .limit(1)
        )
        if not artifact:
            raise SimulationRunError("该运行尚未生成 LISFLOOD 点源输入")
        return artifact

    def get_latest_lisflood_artifact(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[SimulationRun, RunArtifact]:
        run, _ = self.get_latest_successful_result(session, version_id)
        return run, self.get_lisflood_artifact(session, run.id)

    def get_latest_version_timeseries(
        self,
        session: Session,
        version_id: uuid.UUID,
        layer_id: str,
        feature_name: str,
    ) -> dict:
        run, version = self.get_latest_successful_result(session, version_id)
        filename = next(
            (
                artifact_filename
                for artifact_filename, definition in self.LAYER_DEFINITIONS.items()
                if definition[0] == layer_id
            ),
            None,
        )
        if not filename:
            raise SimulationRunError("不支持的模拟结果图层")
        artifact = session.scalar(
            select(RunArtifact).where(
                RunArtifact.run_id == run.id,
                RunArtifact.artifact_type == "visual",
                RunArtifact.filename == filename,
            )
        )
        if not artifact:
            raise SimulationRunError("该版本缺少对应的结果图层")

        runtime = self.settings.resolved_runtime_dir
        runtime.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"timeseries-{run.id}-", dir=runtime) as directory:
            path = Path(directory) / artifact.filename
            self.storage.download_to(artifact.object_key, path, bucket=artifact.bucket)
            payload = json.loads(path.read_text(encoding="utf-8"))
        features = [
            feature
            for feature in payload.get("features", [])
            if feature.get("properties", {}).get("name") == feature_name
        ]
        features.sort(
            key=lambda feature: feature.get("properties", {}).get(
                "time_index", feature.get("properties", {}).get("time", 0)
            )
        )
        metadata = self._build_result_metadata(version)
        return {
            "type": "FeatureCollection",
            "features": features,
            "field_metadata": metadata.get(layer_id, {}),
        }

    def get_latest_version_result_timeline(
        self, session: Session, version_id: uuid.UUID
    ) -> tuple[SimulationRun, ModelVersion, dict]:
        """Return time steps and numeric ranges grouped by result layer and field."""
        run, version = self.get_latest_successful_result(session, version_id)
        layers = self._load_full_layer_artifacts(session, run)
        steps: dict[int, str | None] = {}
        ranges: dict[str, dict[str, dict[str, float]]] = {}
        metadata_fields = {"time", "time_index"}

        for layer in layers:
            layer_id = layer.get("id")
            if not isinstance(layer_id, str):
                continue
            layer_ranges: dict[str, dict[str, float]] = {}
            for feature in layer.get("geojson", {}).get("features", []):
                properties = feature.get("properties", {})
                time_index = properties.get("time_index", properties.get("time"))
                if isinstance(time_index, int) and not isinstance(time_index, bool):
                    steps.setdefault(time_index, properties.get("timestamp"))

                for field, value in properties.items():
                    if field in metadata_fields or isinstance(value, bool):
                        continue
                    if not isinstance(value, (int, float)) or not math.isfinite(value):
                        continue
                    numeric_value = float(value)
                    value_range = layer_ranges.setdefault(
                        field, {"minimum": numeric_value, "maximum": numeric_value}
                    )
                    value_range["minimum"] = min(value_range["minimum"], numeric_value)
                    value_range["maximum"] = max(value_range["maximum"], numeric_value)
            if layer_ranges:
                ranges[layer_id] = layer_ranges

        return run, version, {
            "steps": [
                {"time_index": index, "timestamp": steps[index]}
                for index in sorted(steps)
            ],
            "result_ranges": ranges,
            "result_metadata": self._build_result_metadata(version),
        }

    def _build_result_metadata(self, version: ModelVersion) -> dict[str, dict[str, dict]]:
        flow_units = self._load_flow_units(version)
        flow_unit_label = self.FLOW_UNIT_LABELS.get(flow_units, flow_units)
        is_us_customary = flow_units in {"CFS", "GPM", "MGD"}
        length_unit = "ft" if is_us_customary else "m"
        volume_unit = "ft³" if is_us_customary else "m³"
        velocity_unit = "ft/s" if is_us_customary else "m/s"
        precipitation_rate_unit = "in/hr" if is_us_customary else "mm/hr"
        precipitation_depth_unit = "in" if is_us_customary else "mm"
        return {
            "result-nodes": {
                "depth": {"unit": length_unit},
                "head": {"unit": length_unit},
                "ponded_v": {"unit": volume_unit},
                "lateral_i": {"unit": flow_unit_label},
                "total_i": {"unit": flow_unit_label},
                "flooding": {"unit": flow_unit_label},
            },
            "result-conduits": {
                "rate": {"unit": flow_unit_label},
                "depth": {"unit": length_unit},
                "velocity": {"unit": velocity_unit},
                "volume": {"unit": volume_unit},
                "capacity": {"unit": None},
            },
            "result-subcatchments": {
                "rain": {"unit": precipitation_rate_unit},
                "snow": {"unit": precipitation_depth_unit},
                "evap": {"unit": precipitation_rate_unit},
                "infilt": {"unit": precipitation_rate_unit},
                "runoff": {"unit": flow_unit_label},
                "gw_flow": {"unit": flow_unit_label},
                "soil_moist": {"unit": None},
            },
        }

    def _load_flow_units(self, version: ModelVersion) -> str:
        runtime = self.settings.resolved_runtime_dir
        runtime.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"units-{version.id}-", dir=runtime) as directory:
            path = Path(directory) / "model.inp"
            self.storage.download_to(
                version.inp_object_key, path, bucket=version.inp_bucket
            )
            sections = validate_inp_file(path).sections
        for line in data_lines(sections.get("OPTIONS", [])):
            values = line.split()
            if len(values) >= 2 and values[0].upper() == "FLOW_UNITS":
                return values[1].upper()
        return ""

    def get_latest_version_result_step(
        self, session: Session, version_id: uuid.UUID, time_index: int
    ) -> tuple[SimulationRun, ModelVersion, list[dict]]:
        """Return every result layer and property for one simulation time step."""
        run, version = self.get_latest_successful_result(session, version_id)
        layers = self._load_full_layer_artifacts(session, run)
        result_layers: list[dict] = []

        for layer in layers:
            features = [
                feature
                for feature in layer.get("geojson", {}).get("features", [])
                if feature.get("properties", {}).get(
                    "time_index", feature.get("properties", {}).get("time")
                )
                == time_index
            ]
            result_layers.append(
                {
                    **layer,
                    "geojson": {**layer.get("geojson", {}), "features": features},
                }
            )

        if not result_layers or not any(
            layer["geojson"]["features"] for layer in result_layers
        ):
            raise SimulationRunError("模拟结果中不存在该时间步")
        return run, version, result_layers

    def _load_layer_artifacts(self, session: Session, run: SimulationRun) -> list[dict]:
        return latest_time_step_layers(self._load_full_layer_artifacts(session, run))

    def _load_full_layer_artifacts(self, session: Session, run: SimulationRun) -> list[dict]:
        artifacts = list(
            session.scalars(
                select(RunArtifact)
                .where(RunArtifact.run_id == run.id, RunArtifact.artifact_type == "visual")
                .order_by(RunArtifact.filename)
            )
        )
        layers = []
        runtime = self.settings.resolved_runtime_dir
        runtime.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"layers-{run.id}-", dir=runtime) as directory:
            for artifact in artifacts:
                definition = self.LAYER_DEFINITIONS.get(artifact.filename)
                if not definition:
                    continue
                path = Path(directory) / artifact.filename
                self.storage.download_to(artifact.object_key, path, bucket=artifact.bucket)
                layer_id, name, geometry_type = definition
                layers.append(
                    {
                        "id": layer_id,
                        "name": name,
                        "geometry_type": geometry_type,
                        "source": "simulation",
                        "geojson": json.loads(path.read_text(encoding="utf-8")),
                    }
                )
        return layers

    @staticmethod
    def artifact_payload(run: SimulationRun) -> list[dict]:
        return [
            {
                "type": artifact.artifact_type,
                "bucket": artifact.bucket,
                "object_key": artifact.object_key,
                "filename": artifact.filename,
                "size_bytes": artifact.size_bytes,
            }
            for artifact in run.artifacts
        ]

    @staticmethod
    def _record_artifact(
        session: Session,
        run: SimulationRun,
        artifact_type: str,
        stored: StoredObject,
    ) -> None:
        session.add(
            RunArtifact(
                id=uuid.uuid4(),
                run_id=run.id,
                artifact_type=artifact_type,
                bucket=stored.bucket,
                object_key=stored.object_key,
                filename=stored.filename,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                checksum=stored.checksum,
                status="available",
            )
        )
        session.flush()

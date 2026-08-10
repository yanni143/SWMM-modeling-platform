import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models.domain import RunArtifact, SimulationRun
from Service.ModelService import ModelNotFoundError, ModelService
from Service.SWMMService import SwmmService
from storage.artifact_storage import ArtifactStorageService, StoredObject
from swmm_core.result_geojson import (
    parse_result_layers,
    write_result_layers,
)


class SimulationRunError(RuntimeError):
    pass


class SimulationService:
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
                self.storage.download_to(version.inp_object_key, inp_path, bucket=version.inp_bucket)
                self._record_artifact(session, run, "input", self.storage.upload_run_input(inp_path, run.id))
                run.progress = 20
                session.commit()

                result = SwmmService.run_model(str(inp_path))
                if not result.get("success") or not result.get("out_exists"):
                    raise SimulationRunError(result.get("message", "SWMM 未生成 OUT 文件"))

                out_path = Path(result["out_file"])
                rpt_path = Path(result["rpt_file"])
                layers = parse_result_layers(inp_path, out_path)
                visual_paths = write_result_layers(layers, workdir / "visual")
                run.progress = 75
                session.commit()

                self._record_artifact(
                    session, run, "raw_out", self.storage.upload_run_artifact(out_path, run.id, "raw")
                )
                if rpt_path.is_file():
                    self._record_artifact(
                        session, run, "report", self.storage.upload_run_artifact(rpt_path, run.id, "raw")
                    )
                for path in visual_paths:
                    self._record_artifact(
                        session, run, "visual", self.storage.upload_run_artifact(path, run.id, "visual")
                    )

            run.status = "success"
            run.progress = 100
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(run)
            return run, layers
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
        if not run or run.model_id != self.settings.fixed_model_id:
            raise SimulationRunError("运行记录不存在")
        artifacts = list(
            session.scalars(
                select(RunArtifact)
                .where(RunArtifact.run_id == run_id, RunArtifact.artifact_type == "visual")
                .order_by(RunArtifact.filename)
            )
        )
        definitions = {
            "result-subcatchments.geojson": ("result-subcatchments", "子汇水区模拟结果", "fill"),
            "result-conduits.geojson": ("result-conduits", "管线模拟结果", "line"),
            "result-nodes.geojson": ("result-nodes", "节点模拟结果", "circle"),
        }
        layers = []
        with tempfile.TemporaryDirectory(prefix=f"layers-{run_id}-", dir=self.settings.resolved_runtime_dir) as directory:
            for artifact in artifacts:
                definition = definitions.get(artifact.filename)
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

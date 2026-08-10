"""Smoke-test the built-in model's parameter editing and simulation pipeline."""

import sys
from pathlib import Path
from uuid import UUID

PROJECT_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from Controller.controller import app
from database.session import get_session_factory
from models.domain import ModelVersion, RunArtifact, SimulationRun
from storage.artifact_storage import ArtifactStorageService


def cleanup(version_id: UUID | None, run_id: UUID | None) -> None:
    session = get_session_factory()()
    storage = ArtifactStorageService()
    try:
        artifacts = list(
            session.scalars(select(RunArtifact).where(RunArtifact.run_id == run_id))
        ) if run_id else []
        for artifact in artifacts:
            storage.client.remove_object(artifact.bucket, artifact.object_key)
        version = session.get(ModelVersion, version_id) if version_id else None
        if version:
            storage.client.remove_object(version.inp_bucket, version.inp_object_key)
        if run_id:
            session.execute(delete(RunArtifact).where(RunArtifact.run_id == run_id))
            session.execute(delete(SimulationRun).where(SimulationRun.id == run_id))
        if version_id:
            session.execute(delete(ModelVersion).where(ModelVersion.id == version_id))
        session.commit()
    finally:
        session.close()


def main() -> None:
    generated_version_id = None
    generated_run_id = None
    try:
        with TestClient(app) as client:
            models = client.get("/api/models")
            models.raise_for_status()
            model_id = models.json()[0]["id"]
            versions = client.get(f"/api/models/{model_id}/versions")
            versions.raise_for_status()
            v1 = next(item["id"] for item in versions.json() if item["version"] == 1)

            catalog = client.get(f"/api/model-versions/{v1}/editable-parameters")
            catalog.raise_for_status()
            print("CATALOG", [(g["label"], len(g["objects"])) for g in catalog.json()["groups"]])

            adjusted = client.post(
                f"/api/model-versions/{v1}/versions",
                json={
                    "summary": "验证不透水率调整",
                    "changes": [{
                        "section": "SUBCATCHMENTS",
                        "target": "S1",
                        "field": "imperv",
                        "new_value": "55",
                    }],
                },
            )
            adjusted.raise_for_status()
            generated_version_id = UUID(adjusted.json()["version"]["id"])
            print("VERSION", adjusted.json()["version"]["version"], adjusted.json()["changes"])

            detail = client.get(
                f"/api/model-versions/{generated_version_id}/sections/SUBCATCHMENTS"
            )
            detail.raise_for_status()
            assert detail.json()["section"]["records"][0]["values"]["imperv"] == "55"

            comparison = client.post(f"/api/model-versions/{generated_version_id}/runs")
            comparison.raise_for_status()
            generated_run_id = UUID(comparison.json()["run_id"])
            print("RUN", comparison.json()["status"], len(comparison.json()["layers"]))
    finally:
        cleanup(generated_version_id, generated_run_id)
        print("CLEANUP", generated_version_id, generated_run_id)


if __name__ == "__main__":
    main()

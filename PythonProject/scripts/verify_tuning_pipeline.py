"""Smoke-test safe parameter editing and remove all generated verification data."""

import sys
from pathlib import Path
from uuid import UUID, uuid4

PROJECT_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from Controller.controller import app
from database.session import get_session_factory
from models.domain import ModelVersion, RunArtifact, SimulationRun, SwmmModel
from storage.artifact_storage import ArtifactStorageService


def cleanup(model_id: UUID) -> None:
    session = get_session_factory()()
    storage = ArtifactStorageService()
    try:
        versions = list(session.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id)))
        runs = list(session.scalars(select(SimulationRun).where(SimulationRun.model_id == model_id)))
        run_ids = [run.id for run in runs]
        artifacts = (
            list(session.scalars(select(RunArtifact).where(RunArtifact.run_id.in_(run_ids))))
            if run_ids
            else []
        )
        for artifact in artifacts:
            storage.client.remove_object(artifact.bucket, artifact.object_key)
        for version in versions:
            storage.client.remove_object(version.inp_bucket, version.inp_object_key)
        if run_ids:
            session.execute(delete(RunArtifact).where(RunArtifact.run_id.in_(run_ids)))
            session.execute(delete(SimulationRun).where(SimulationRun.id.in_(run_ids)))
        session.execute(delete(ModelVersion).where(ModelVersion.model_id == model_id))
        session.execute(delete(SwmmModel).where(SwmmModel.id == model_id))
        session.commit()
    finally:
        session.close()


def main() -> None:
    client = TestClient(app)
    fixture = PROJECT_DIR / "tests" / "fixtures" / "minimal.inp"
    model_id = None
    try:
        with fixture.open("rb") as inp_file:
            upload = client.post(
                "/api/models",
                data={"name": f"调参链路验证-{uuid4().hex[:8]}"},
                files={"file": (fixture.name, inp_file, "text/plain")},
            )
        upload.raise_for_status()
        model_id = UUID(upload.json()["model"]["id"])
        v1 = upload.json()["version"]["id"]

        catalog = client.get(f"/api/model-versions/{v1}/editable-parameters")
        catalog.raise_for_status()
        print("CATALOG", [(g["label"], len(g["objects"])) for g in catalog.json()["groups"]])

        adjusted = client.post(
            f"/api/model-versions/{v1}/versions",
            json={
                "summary": "验证不透水率调整",
                "changes": [
                    {
                        "section": "SUBCATCHMENTS",
                        "target": "S1",
                        "field": "imperv",
                        "new_value": "55",
                    }
                ],
            },
        )
        adjusted.raise_for_status()
        v2 = adjusted.json()["version"]["id"]
        print("VERSION", adjusted.json()["version"]["version"], adjusted.json()["changes"])

        detail = client.get(f"/api/model-versions/{v2}/sections/SUBCATCHMENTS")
        detail.raise_for_status()
        assert detail.json()["section"]["records"][0]["values"]["imperv"] == "55"

        comparison = client.post(f"/api/model-versions/{v2}/runs")
        comparison.raise_for_status()
        print("V2_RUN", comparison.json()["status"], len(comparison.json()["layers"]))
    finally:
        if model_id:
            cleanup(model_id)
            print("CLEANUP", model_id)


if __name__ == "__main__":
    main()

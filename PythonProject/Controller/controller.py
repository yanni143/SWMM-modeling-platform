import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from Service.OutProcessService import out_process_service
from Service.SWMMService import SwmmService
from config import get_settings
from database.session import get_engine
from storage.artifact_storage import ArtifactStorageService


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunModelRequest(BaseModel):
    dataset_id: str
    project_id: str
    out_id: str
    inp_file: str
    out_filename: Optional[str] = None


@app.get("/health")
def health() -> dict:
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    try:
        storage = ArtifactStorageService()
        storage.initialize()
        checks["minio"] = "ok" if storage.is_available() else "unavailable"
    except Exception:
        checks["minio"] = "unavailable"

    return {
        "status": "ok" if all(value == "ok" for value in checks.values()) else "degraded",
        "checks": checks,
    }


@app.post("/outprocess")
def run_and_process_model(payload: RunModelRequest) -> dict:
    """Run a SWMM model and parse its output into database and visual artifacts."""
    try:
        swmm_result = SwmmService.run_model(payload.inp_file)
        if not swmm_result.get("success"):
            raise HTTPException(status_code=422, detail=swmm_result.get("message", "SWMM运行失败"))

        out_file = swmm_result.get("out_file")
        if not out_file or not swmm_result.get("out_exists"):
            raise HTTPException(status_code=422, detail="SWMM未生成OUT文件")

        result = out_process_service.process_swmm_output(
            dataset_id=payload.dataset_id,
            project_id=payload.project_id,
            out_id=payload.out_id,
            out_file=out_file,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "结果解析失败"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{exc}") from exc


@app.get("/get_simulation_result")
def get_simulation_result(project_id: str, out_id: str, filename: str) -> FileResponse:
    """Return a generated visualization file from the configured local workspace.

    This local implementation remains as a compatibility layer until run artifacts
    are persisted to MinIO in the storage refactor.
    """
    root = settings.resolved_runtime_dir
    file_path = (root / project_id / out_id / "visual" / filename).resolve()
    try:
        file_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="非法文件路径") from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="模拟结果文件不存在")
    return FileResponse(path=file_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("Controller.controller:app", host="0.0.0.0", port=8000, reload=True)

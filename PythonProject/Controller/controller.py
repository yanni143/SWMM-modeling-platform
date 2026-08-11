from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import get_settings
from Controller.model_routes import router as model_router
from Controller.run_routes import router as run_router
from database.session import get_engine, get_session_factory
from Service.ModelService import ModelService
from storage.artifact_storage import ArtifactStorageService

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    session = get_session_factory()()
    try:
        ModelService().ensure_fixed_model(session)
    finally:
        session.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(model_router)
app.include_router(run_router)


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

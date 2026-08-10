from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SWMM Modeling and Simulation API"
    app_env: str = "development"
    cors_origins: str = (
        "http://localhost:5173,http://223.2.33.21,http://223.2.33.21:5173"
    )

    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL_NEW", "PG_DSN")
    )
    database_name: str = "fenhuModel"
    runtime_dir: Path = PROJECT_DIR / ".runtime"
    swmm_input_crs: str = "EPSG:4549"
    fixed_model_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    fixed_version_id: UUID = UUID("00000000-0000-0000-0000-000000000101")
    fixed_model_name: str = "汾湖演示研究区"
    fixed_model_description: str = "系统内置的固定 SWMM 演示研究区"
    fixed_inp_path: Path = PROJECT_DIR / "resources" / "fixed-study-area.inp"

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "swmm-artifacts"
    presigned_url_expires_seconds: int = 3600
    minio_connect_timeout_seconds: float = 2.0
    minio_read_timeout_seconds: float = 10.0

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:5173"]

    @property
    def resolved_runtime_dir(self) -> Path:
        path = self.runtime_dir
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return path.resolve()

    @property
    def resolved_fixed_inp_path(self) -> Path:
        path = self.fixed_inp_path
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return path.resolve()

    @property
    def effective_database_url(self) -> str:
        """Reuse configured credentials while targeting this system's dedicated database."""
        return make_url(self.database_url).set(database=self.database_name).render_as_string(
            hide_password=False
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

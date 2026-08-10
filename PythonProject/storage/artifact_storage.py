import mimetypes
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

from minio import Minio

from config import Settings, get_settings
from storage.minio_client import (
    download_file,
    ensure_bucket,
    get_minio_client,
    presigned_get,
    upload_file,
)


SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def safe_segment(value: str | UUID) -> str:
    segment = SAFE_SEGMENT.sub("-", str(value).strip()).strip(".-")
    if not segment:
        raise ValueError("对象路径片段不能为空")
    return segment


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    filename: str
    size_bytes: Optional[int]
    checksum: Optional[str]
    content_type: str

    def to_dict(self) -> dict:
        return asdict(self)


class ArtifactKeyBuilder:
    @staticmethod
    def model_version(model_id: str | UUID, version_id: str | UUID) -> str:
        return f"models/{safe_segment(model_id)}/versions/{safe_segment(version_id)}/model.inp"

    @staticmethod
    def run_input(run_id: str | UUID) -> str:
        return f"runs/{safe_segment(run_id)}/input/model.inp"

    @staticmethod
    def run_artifact(run_id: str | UUID, category: str, filename: str) -> str:
        clean_name = safe_segment(Path(filename).name)
        return f"runs/{safe_segment(run_id)}/{safe_segment(category)}/{clean_name}"


class ArtifactStorageService:
    """Private MinIO storage for model versions and simulation artifacts."""

    def __init__(
        self,
        client: Optional[Minio] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or get_minio_client()
        self.bucket = self.settings.minio_bucket

    def initialize(self) -> None:
        ensure_bucket(self.client, self.bucket)

    def is_available(self) -> bool:
        return self.client.bucket_exists(self.bucket)

    def upload_model_version(
        self,
        local_path: str | Path,
        model_id: str | UUID,
        version_id: str | UUID,
    ) -> StoredObject:
        return self._upload(
            local_path=local_path,
            object_key=ArtifactKeyBuilder.model_version(model_id, version_id),
            content_type="text/plain",
        )

    def upload_run_input(self, local_path: str | Path, run_id: str | UUID) -> StoredObject:
        return self._upload(
            local_path=local_path,
            object_key=ArtifactKeyBuilder.run_input(run_id),
            content_type="text/plain",
        )

    def upload_run_artifact(
        self,
        local_path: str | Path,
        run_id: str | UUID,
        category: str,
        artifact_name: Optional[str] = None,
    ) -> StoredObject:
        path = Path(local_path)
        filename = artifact_name or path.name
        return self._upload(
            local_path=path,
            object_key=ArtifactKeyBuilder.run_artifact(run_id, category, filename),
        )

    def download_to(self, object_key: str, destination: str | Path) -> Path:
        path = Path(destination).resolve()
        download_file(self.client, self.bucket, object_key, str(path))
        return path

    def presigned_url(self, object_key: str, expires_seconds: Optional[int] = None) -> str:
        return presigned_get(
            self.client,
            self.bucket,
            object_key,
            expires_seconds or self.settings.presigned_url_expires_seconds,
        )

    def _upload(
        self,
        local_path: str | Path,
        object_key: str,
        content_type: Optional[str] = None,
    ) -> StoredObject:
        path = Path(local_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"待上传文件不存在：{path}")

        self.initialize()
        detected_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        metadata = upload_file(
            self.client,
            self.bucket,
            object_key,
            str(path),
            content_type=detected_type,
        )
        return StoredObject(
            bucket=self.bucket,
            object_key=object_key,
            filename=path.name,
            size_bytes=metadata.get("size"),
            checksum=metadata.get("etag"),
            content_type=detected_type,
        )

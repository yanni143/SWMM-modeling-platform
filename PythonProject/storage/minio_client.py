import os
from typing import Optional, Dict, Any
from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Retry, Timeout

from config import get_settings


def get_minio_client() -> Minio:
    settings = get_settings()
    http_client = PoolManager(
        timeout=Timeout(
            connect=settings.minio_connect_timeout_seconds,
            read=settings.minio_read_timeout_seconds,
        ),
        retries=Retry(total=1, connect=1, read=1, redirect=0),
    )
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        http_client=http_client,
    )


def ensure_bucket(client: Minio, bucket: Optional[str] = None):
    bucket = bucket or get_settings().minio_bucket
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error:
        # bubble up for caller to handle
        raise


def upload_file(
    client: Minio,
    bucket: str,
    object_key: str,
    local_path: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a local file to MinIO and return object metadata (etag, size).

    Raises exceptions from Minio client on failure.
    """
    client.fput_object(bucket, object_key, file_path=local_path, content_type=content_type)
    stat = client.stat_object(bucket, object_key)
    return {"etag": getattr(stat, "etag", None), "size": getattr(stat, "size", None)}


def download_file(client: Minio, bucket: str, object_key: str, local_path: str) -> None:
    """Download an object from MinIO to a local file path using fget_object."""
    # Ensure destination directory exists
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    client.fget_object(bucket, object_key, local_path)


def stat_object(client: Minio, bucket: str, object_key: str) -> Dict[str, Any]:
    stat = client.stat_object(bucket, object_key)
    return {"etag": getattr(stat, "etag", None), "size": getattr(stat, "size", None)}


def delete_object(client: Minio, bucket: str, object_key: str) -> None:
    client.remove_object(bucket, object_key)

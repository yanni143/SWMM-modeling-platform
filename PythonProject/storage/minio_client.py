import os
from datetime import timedelta
from typing import Optional, Dict, Any
from minio import Minio
from minio.error import S3Error


def get_minio_client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def ensure_bucket(client: Minio, bucket: Optional[str] = None):
    bucket = bucket or os.getenv("MINIO_BUCKET", "inp-files")
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error:
        # bubble up for caller to handle
        raise


def upload_file(client: Minio, bucket: str, object_key: str, local_path: str) -> Dict[str, Any]:
    """Upload a local file to MinIO and return object metadata (etag, size).

    Raises exceptions from Minio client on failure.
    """
    client.fput_object(bucket, object_key, file_path=local_path)
    stat = client.stat_object(bucket, object_key)
    return {"etag": getattr(stat, "etag", None), "size": getattr(stat, "size", None)}


def download_file(client: Minio, bucket: str, object_key: str, local_path: str) -> None:
    """Download an object from MinIO to a local file path using fget_object."""
    # Ensure destination directory exists
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    client.fget_object(bucket, object_key, local_path)


def presigned_get(client: Minio, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
    return client.presigned_get_object(bucket, object_key, expires=timedelta(seconds=expires_seconds))


def stat_object(client: Minio, bucket: str, object_key: str) -> Dict[str, Any]:
    stat = client.stat_object(bucket, object_key)
    return {"etag": getattr(stat, "etag", None), "size": getattr(stat, "size", None)}


def delete_object(client: Minio, bucket: str, object_key: str) -> None:
    client.remove_object(bucket, object_key)

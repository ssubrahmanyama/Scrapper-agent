"""
services/storage/minio_client.py
OSS replacement for AWS S3 using MinIO (Apache-2.0).
MinIO is S3-API-compatible and runs as a single container.
"""
from __future__ import annotations

import io
from datetime import timedelta

import structlog
from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = structlog.get_logger(__name__)

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        _ensure_bucket(settings.MINIO_BUCKET)
    return _client


def _ensure_bucket(bucket: str) -> None:
    try:
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket)
            logger.info("MinIO bucket created", bucket=bucket)
    except S3Error as exc:
        logger.error("MinIO bucket init failed", error=str(exc))


async def upload_report(object_name: str, data: bytes, content_type: str = "application/pdf") -> str:
    """Upload a report file and return a 1-hour presigned download URL."""
    mc = get_minio()
    mc.put_object(settings.MINIO_BUCKET, object_name, io.BytesIO(data), len(data), content_type=content_type)
    url = mc.presigned_get_object(settings.MINIO_BUCKET, object_name, expires=timedelta(hours=1))
    logger.info("Report uploaded", object=object_name, size=len(data))
    return url


async def delete_user_files(user_id: str) -> int:
    """GDPR erasure — delete all objects belonging to a user."""
    mc = get_minio()
    objects = mc.list_objects(settings.MINIO_BUCKET, prefix=f"reports/{user_id}/", recursive=True)
    deleted = 0
    for obj in objects:
        mc.remove_object(settings.MINIO_BUCKET, obj.object_name)
        deleted += 1
    logger.info("User files deleted", user_id=user_id, count=deleted)
    return deleted

"""Object storage on S3-compatible backends (MinIO in dev).

Only the object key + metadata are stored in MySQL; binary data never goes
into the database. Private assets are served through short-lived signed URLs.
User-supplied filenames are never used as storage keys.
"""
from __future__ import annotations

import logging
import uuid

from app.config import config
from app.models import new_uuid

log = logging.getLogger(__name__)


class StorageError(Exception):
    pass


def asset_key(user_id: str, kind: str, extension: str) -> str:
    ext = (extension or "bin").lstrip(".").lower()[:10] or "bin"
    return f"assets/{user_id}/{kind}/{new_uuid()}.{ext}"


class StorageService:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as exc:
            raise StorageError("boto3 is not installed") from exc
        if not (config.storage_endpoint and config.storage_bucket):
            raise StorageError("object storage is not configured")
        self._client = boto3.client(
            "s3",
            endpoint_url=config.storage_endpoint,
            aws_access_key_id=config.storage_access_key or None,
            aws_secret_access_key=config.storage_secret_key or None,
            region_name=config.storage_region,
            config=BotoConfig(signature_version="s3v4"),
        )
        return self._client

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._get_client().put_object(
                Bucket=config.storage_bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"upload failed: {exc}") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self._get_client().get_object(Bucket=config.storage_bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"download failed: {exc}") from exc

    def presigned_get_url(self, key: str, expires_seconds: int | None = None) -> str:
        try:
            return self._get_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": config.storage_bucket, "Key": key},
                ExpiresIn=expires_seconds or config.signed_url_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"signed url failed: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._get_client().delete_object(Bucket=config.storage_bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"delete failed: {exc}") from exc


storage = StorageService()

"""S3 Storage Service — MinIO-compatible object storage for documents and images.

Replaces local filesystem storage with S3-compatible object storage.
Buckets:
  - soloprac/documents/ — uploaded clinical documents (PDFs, images)
  - soloprac/images/ — clinical images (wound photos, etc.)
  - soloprac/pdfs/ — generated PDFs (prescriptions, invoices, certificates)

Usage:
    from app.services.storage import storage_service
    await storage_service.upload_file(file_bytes, "documents", "patient123/report.pdf")
    url = await storage_service.get_presigned_url("documents", "patient123/report.pdf")
"""

from __future__ import annotations

import os
import logging
from typing import Optional, BinaryIO
from datetime import timedelta

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# Bucket names
DOCUMENTS_BUCKET = "documents"
IMAGES_BUCKET = "images"
PDFS_BUCKET = "pdfs"


class StorageService:
    """S3-compatible storage service using MinIO or any S3 provider."""

    _instance: Optional["StorageService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = None
        self._resource = None
        self._init_client()

    def _init_client(self):
        """Initialize S3 client from configuration."""
        endpoint = settings.MINIO_ENDPOINT
        access_key = settings.MINIO_ACCESS_KEY
        secret_key = settings.MINIO_SECRET_KEY
        self._bucket = settings.MINIO_BUCKET

        # Use HTTPS if configured
        use_https = settings.MINIO_USE_HTTPS

        self._client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if use_https else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
            region_name="us-east-1",
        )
        self._init_buckets()

    def _init_buckets(self):
        """Create buckets if they don't exist."""
        for bucket_name in [DOCUMENTS_BUCKET, IMAGES_BUCKET, PDFS_BUCKET]:
            try:
                self._client.head_bucket(Bucket=bucket_name)
            except ClientError:
                try:
                    self._client.create_bucket(Bucket=bucket_name)
                    logger.info("Created bucket: %s", bucket_name)
                except Exception as e:
                    logger.warning("Failed to create bucket %s: %s", bucket_name, e)

    async def upload_file(
        self,
        file_data: bytes,
        bucket_type: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file to S3.

        Args:
            file_data: Raw file bytes.
            bucket_type: One of "documents", "images", "pdfs".
            key: Object key (path within bucket).
            content_type: MIME type (optional, inferred by S3 if not set).

        Returns:
            The S3 object key (for later retrieval).
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        try:
            self._client.put_object(
                Bucket=bucket_type,
                Key=key,
                Body=file_data,
                **extra_args,
            )
            logger.info("Uploaded file: %s/%s (%d bytes)", bucket_type, key, len(file_data))
            return key
        except Exception as e:
            logger.error("Upload failed: %s/%s — %s", bucket_type, key, e)
            raise

    async def download_file(self, bucket_type: str, key: str) -> bytes:
        """Download a file from S3.

        Args:
            bucket_type: One of "documents", "images", "pdfs".
            key: Object key.

        Returns:
            File bytes.
        """
        try:
            response = self._client.get_object(Bucket=bucket_type, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning("File not found: %s/%s", bucket_type, key)
                return None
            raise

    async def delete_file(self, bucket_type: str, key: str) -> bool:
        """Delete a file from S3."""
        try:
            self._client.delete_object(Bucket=bucket_type, Key=key)
            logger.info("Deleted file: %s/%s", bucket_type, key)
            return True
        except Exception as e:
            logger.error("Delete failed: %s/%s — %s", bucket_type, key, e)
            return False

    async def get_presigned_url(
        self,
        bucket_type: str,
        key: str,
        expires_in: int = 3600,
    ) -> Optional[str]:
        """Generate a presigned URL for file access.

        Args:
            bucket_type: One of "documents", "images", "pdfs".
            key: Object key.
            expires_in: URL expiry in seconds (default 1 hour).

        Returns:
            Presigned URL string, or None if file doesn't exist.
        """
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_type, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error("Presigned URL failed: %s/%s — %s", bucket_type, key, e)
            return None

    async def file_exists(self, bucket_type: str, key: str) -> bool:
        """Check if a file exists in S3."""
        try:
            self._client.head_object(Bucket=bucket_type, Key=key)
            return True
        except ClientError:
            return False

    async def list_files(self, bucket_type: str, prefix: str = "") -> list:
        """List files in a bucket with optional prefix."""
        try:
            response = self._client.list_objects_v2(
                Bucket=bucket_type,
                Prefix=prefix,
            )
            return [obj["Key"] for obj in response.get("Contents", [])]
        except Exception as e:
            logger.error("List failed: %s/%s — %s", bucket_type, prefix, e)
            return []


# Singleton instance
storage_service = StorageService()

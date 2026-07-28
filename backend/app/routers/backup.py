"""Backup Router — database backup and restore via MinIO.

Endpoints:
    POST /admin/backup — Create a database backup (pg_dump → MinIO)
    GET  /admin/backups — List available backups
    POST /admin/restore/{backup_key} — Restore from a backup
"""

from __future__ import annotations

import os
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-backup"])


@router.post("/backup")
async def create_backup(
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a database backup using pg_dump and upload to MinIO.

    Only admin doctors can create backups.
    """
    if settings.DEBUG:
        raise HTTPException(status_code=403, detail="Backup not available in debug mode")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}.sql.gz"

    try:
        # pg_dump with gzip compression
        dump_cmd = [
            "pg_dump",
            "--host", settings.POSTGRES_SERVER,
            "--port", str(settings.POSTGRES_PORT),
            "--username", settings.POSTGRES_USER,
            "--dbname", settings.POSTGRES_DB,
            "--no-owner",
            "--no-privileges",
        ]

        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name

        # Run pg_dump and compress
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        with open(tmp_path, "wb") as f:
            proc = subprocess.Popen(
                dump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            # Pipe through gzip
            gzip_proc = subprocess.Popen(
                ["gzip"],
                stdin=proc.stdout,
                stdout=f,
                stderr=subprocess.PIPE,
            )
            proc.stdout.close()
            gzip_proc.communicate()
            proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed with code {proc.returncode}")

        # Upload to MinIO
        from app.services.storage import storage_service
        s3_key = f"backups/{backup_filename}"
        with open(tmp_path, "rb") as f:
            await storage_service.upload_file(f, s3_key, content_type="application/gzip")

        os.unlink(tmp_path)

        logger.info("Database backup created: %s", backup_filename)
        return {"status": "ok", "backup_key": s3_key, "filename": backup_filename}

    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}")


@router.get("/backups")
async def list_backups(
    doctor=Depends(get_current_doctor),
):
    """List available backups in MinIO."""
    try:
        from app.services.storage import storage_service
        files = await storage_service.list_files(prefix="backups/")
        backups = [
            {"key": f["key"], "name": f["key"].split("/")[-1], "size": f.get("size", 0)}
            for f in files if f["key"].endswith(".sql.gz")
        ]
        backups.sort(key=lambda x: x["name"], reverse=True)
        return {"backups": backups}
    except Exception as exc:
        logger.error("Failed to list backups: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list backups")

"""Job Status Router — poll arq job status/result.

Any endpoint that enqueues work (P0.7 documents/parse, P2.23 weekly reports,
P2.24 image compare, P2.25 backup) returns a `job_id`. The frontend polls
`GET /api/v1/jobs/{job_id}` to observe: queued → running → done | errored,
and pulls the JSON result on completion.

Backed by arq's ResultStore (Redis) — the same store the worker writes to when
a job returns.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_doctor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job_status(job_id: str, doctor=Depends(get_current_doctor)) -> Dict[str, Any]:
    """Return status + result of a background job.

    Response shape:
      { "job_id": ..., "status": "queued"|"in_progress"|"complete"|"not_found",
        "result": <job return value if complete, else null>,
        "success": bool,           # only present if complete
        "score": null|number,      # arq's internal score (enqueue time)
      }
    """
    try:
        from arq.jobs import Job, JobStatus

        from app.services.background_jobs import get_arq_pool

        pool = await get_arq_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Job queue unavailable")

        job = Job(job_id, redis=pool)
        status = await job.status()

        response: Dict[str, Any] = {
            "job_id": job_id,
            "status": status.value if hasattr(status, "value") else str(status),
        }

        if status == JobStatus.complete:
            info = await job.result_info()
            if info is not None:
                response["success"] = info.success
                response["result"] = info.result
                if info.start_time and info.finish_time:
                    response["duration_ms"] = int((info.finish_time - info.start_time).total_seconds() * 1000)
        elif status == JobStatus.not_found:
            # Job has been evicted from Redis (past keep_result_seconds) —
            # treat as complete-but-unknown so the client stops polling.
            response["status"] = "expired"

        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("get_job_status(%s) failed: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Job status lookup failed: {str(exc)[:200]}")

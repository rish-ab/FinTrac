# =============================================================
# src/api/routes/jobs.py
#
# Status and cancellation for background jobs (see
# src/engine/job_runner.py). Jobs are started by the endpoint that
# owns the work, e.g. POST /api/v1/analysis/backtest-range/jobs.
# =============================================================

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.engine.job_runner import cancel_job, get_job, list_jobs

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/", summary="List recent background jobs")
async def get_jobs(kind: Optional[str] = Query(default=None)) -> List[dict]:
    """Most recent first. Results are omitted; fetch a job by id for them."""
    return [j.to_dict(include_result=False) for j in list_jobs(kind)]


@router.get("/{job_id}", summary="Job status, progress and result")
async def get_job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        # Unknown, expired, or lost on API restart
        raise HTTPException(404, detail="Job not found. It may have expired or the API restarted.")
    return job.to_dict()


@router.post("/{job_id}/cancel", summary="Cancel a queued or running job")
async def cancel_job_endpoint(job_id: str) -> dict:
    job = cancel_job(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found. It may have expired or the API restarted.")
    return job.to_dict(include_result=False)

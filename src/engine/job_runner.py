# =============================================================
# src/engine/job_runner.py
#
# Background jobs for long-running API work (range backtests).
#
# WHY:
# A range backtest makes one LLM call per date step — 10+ minutes
# for a year of monthly points. Holding one HTTP request open that
# long is fragile (browser/proxy timeouts, no progress, no cancel).
# Instead the API starts a job, returns its id immediately, and the
# client polls GET /jobs/{id} for progress and partial results.
#
# DESIGN:
#   - In-memory store, single process. Jobs are lost when the API
#     restarts (including uvicorn --reload on code changes). That is
#     acceptable for interactive research runs; persist to Redis/DB
#     if jobs ever need to survive restarts or multiple workers.
#   - LLM-heavy jobs share one semaphore: Ollama serves requests one
#     at a time, so running two backtests in parallel only makes both
#     slower. Extra jobs wait in 'queued'.
#   - Finished jobs are kept for JOB_TTL_SECONDS so the client can
#     fetch the result, then pruned.
# =============================================================

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from loguru import logger

JOB_TTL_SECONDS = 3600
MAX_STORED_JOBS = 200

# Status values
QUEUED = 'queued'
RUNNING = 'running'
COMPLETED = 'completed'
FAILED = 'failed'
CANCELLED = 'cancelled'
FINISHED_STATES = (COMPLETED, FAILED, CANCELLED)


@dataclass
class Job:
    id: str
    kind: str
    params: Dict[str, Any]
    status: str = QUEUED
    total: Optional[int] = None
    done: int = 0
    message: str = 'Waiting to start'
    partial: List[Any] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    task: Optional[asyncio.Task] = None

    def to_dict(self, include_result: bool = True) -> dict:
        return {
            'id': self.id,
            'kind': self.kind,
            'params': self.params,
            'status': self.status,
            'progress': {
                'done': self.done,
                'total': self.total,
                'message': self.message,
            },
            'partial': self.partial,
            'result': self.result if include_result else None,
            'error': self.error,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
        }


class JobProgress:
    """Handle passed to a job's work function to report progress."""

    def __init__(self, job: Job):
        self._job = job

    def set_total(self, total: int) -> None:
        self._job.total = total

    def step(self, message: str, partial: Any = None) -> None:
        self._job.done += 1
        self._job.message = message
        if partial is not None:
            self._job.partial.append(partial)


Work = Callable[[JobProgress], Awaitable[Any]]

_jobs: Dict[str, Job] = {}
_llm_slot = asyncio.Semaphore(1)


def _prune() -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=JOB_TTL_SECONDS)
    for job_id in [
        j.id for j in _jobs.values()
        if j.status in FINISHED_STATES and j.finished_at and j.finished_at < cutoff
    ]:
        _jobs.pop(job_id, None)
    # Hard cap: drop oldest finished jobs first
    if len(_jobs) > MAX_STORED_JOBS:
        finished = sorted(
            (j for j in _jobs.values() if j.status in FINISHED_STATES),
            key=lambda j: j.created_at,
        )
        for j in finished[: len(_jobs) - MAX_STORED_JOBS]:
            _jobs.pop(j.id, None)


async def _run(job: Job, work: Work) -> None:
    try:
        async with _llm_slot:
            job.status = RUNNING
            job.started_at = datetime.utcnow()
            job.message = 'Starting'
            logger.info(f"Job {job.id[:8]} ({job.kind}) started")
            job.result = await work(JobProgress(job))
        job.status = COMPLETED
        job.message = 'Completed'
        logger.info(f"Job {job.id[:8]} ({job.kind}) completed")
    except asyncio.CancelledError:
        job.status = CANCELLED
        job.message = 'Cancelled'
        logger.info(f"Job {job.id[:8]} ({job.kind}) cancelled")
    except Exception as e:
        job.status = FAILED
        job.error = str(e) or e.__class__.__name__
        job.message = 'Failed'
        logger.exception(f"Job {job.id[:8]} ({job.kind}) failed: {e}")
    finally:
        job.finished_at = datetime.utcnow()


def start_job(kind: str, params: Dict[str, Any], work: Work) -> Job:
    """Register a job and start it in the background. Returns immediately."""
    _prune()
    job = Job(id=str(uuid.uuid4()), kind=kind, params=params)
    _jobs[job.id] = job
    job.task = asyncio.create_task(_run(job, work))
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def cancel_job(job_id: str) -> Optional[Job]:
    """Request cancellation. The LLM call in flight finishes; no further steps run."""
    job = _jobs.get(job_id)
    if job and job.status not in FINISHED_STATES and job.task:
        job.task.cancel()
    return job


def list_jobs(kind: Optional[str] = None) -> List[Job]:
    _prune()
    jobs = [j for j in _jobs.values() if kind is None or j.kind == kind]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)

import asyncio
from datetime import datetime

import pytest

from src.engine import job_runner
from src.engine.job_runner import (
    CANCELLED, COMPLETED, FAILED, QUEUED, RUNNING,
    cancel_job, get_job, start_job,
)


@pytest.fixture(autouse=True)
def fresh_runner(monkeypatch):
    # Each test gets its own store and LLM slot (semaphores bind to a loop)
    monkeypatch.setattr(job_runner, '_jobs', {})
    monkeypatch.setattr(job_runner, '_llm_slot', asyncio.Semaphore(1))


async def _wait(job, states=(COMPLETED, FAILED, CANCELLED)):
    for _ in range(200):
        if job.status in states:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"job stuck in {job.status}")


@pytest.mark.asyncio
async def test_job_completes_with_progress_and_partials():
    async def work(progress):
        progress.set_total(3)
        for i in range(3):
            progress.step(f"step {i}", partial={'i': i})
        return {'answer': 42}

    job = start_job('demo', {'x': 1}, work)
    assert get_job(job.id) is job
    await _wait(job)
    d = job.to_dict()
    assert d['status'] == COMPLETED
    assert d['progress'] == {'done': 3, 'total': 3, 'message': 'Completed'}
    assert d['partial'] == [{'i': 0}, {'i': 1}, {'i': 2}]
    assert d['result'] == {'answer': 42}
    assert d['finished_at'] is not None


@pytest.mark.asyncio
async def test_job_failure_is_recorded():
    async def work(progress):
        raise ValueError('ticker not found')

    job = start_job('demo', {}, work)
    await _wait(job)
    assert job.status == FAILED
    assert job.error == 'ticker not found'


@pytest.mark.asyncio
async def test_cancel_running_job():
    started = asyncio.Event()

    async def work(progress):
        started.set()
        await asyncio.sleep(10)

    job = start_job('demo', {}, work)
    await started.wait()
    assert job.status == RUNNING
    cancel_job(job.id)
    await _wait(job)
    assert job.status == CANCELLED


@pytest.mark.asyncio
async def test_llm_jobs_run_one_at_a_time():
    release = asyncio.Event()

    async def slow(progress):
        await release.wait()
        return 'first'

    async def fast(progress):
        return 'second'

    first = start_job('demo', {}, slow)
    second = start_job('demo', {}, fast)
    await asyncio.sleep(0.05)
    assert first.status == RUNNING
    assert second.status == QUEUED       # waits for the single LLM slot
    release.set()
    await _wait(second)
    assert (first.result, second.result) == ('first', 'second')


@pytest.mark.asyncio
async def test_cancel_queued_job_never_runs():
    release = asyncio.Event()
    ran = []

    async def blocker(progress):
        await release.wait()

    async def never(progress):
        ran.append(True)

    start_job('demo', {}, blocker)
    queued = start_job('demo', {}, never)
    await asyncio.sleep(0.02)
    cancel_job(queued.id)
    await _wait(queued)
    release.set()
    await asyncio.sleep(0.02)
    assert queued.status == CANCELLED and ran == []


def test_unknown_job():
    assert get_job('nope') is None
    assert cancel_job('nope') is None


@pytest.mark.asyncio
async def test_range_backtest_reports_progress(monkeypatch):
    from src.engine import backtester

    async def fake_single(ticker, dt, budget, horizon):
        return backtester.BacktestResult(
            ticker=ticker, backtest_date=dt.isoformat()[:10], horizon_label=horizon,
            ai_verdict='BUY', ai_confidence=0.7, actual_return_pct=1.0, direction_correct=True,
        )

    monkeypatch.setattr(backtester, 'run_single_backtest', fake_single)
    totals, steps = [], []
    result = await backtester.run_range_backtest(
        'AAPL', datetime(2025, 1, 1), datetime(2025, 3, 31), interval_days=30,
        on_start=totals.append, on_step=steps.append,
    )
    assert totals == [3]
    assert [s.backtest_date for s in steps] == ['2025-01-01', '2025-01-31', '2025-03-02']
    assert result.successful == 3 and result.accuracy_pct == 100.0

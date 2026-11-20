import asyncio

import pytest

from tts_stt_tool.jobs.runner import JobBusyError, JobRunner, ProgressEvent


async def slow_job(emit, cancel, steps=3):
    for i in range(steps):
        if cancel.is_set():
            emit(ProgressEvent(job_id="", kind="cancelled", done=i, total=steps))
            return
        await asyncio.sleep(0.05)
        emit(ProgressEvent(job_id="", kind="progress", done=i + 1, total=steps))
    emit(ProgressEvent(job_id="", kind="done", done=steps, total=steps))


async def collect_until_end(q):
    out = []
    while True:
        e = await asyncio.wait_for(q.get(), 5)
        out.append(e)
        if e.kind in ("done", "error", "cancelled"):
            return out


async def test_events_in_order_with_job_id():
    r = JobRunner()
    q = r.subscribe()
    job_id = r.start("block1", lambda emit, cancel: slow_job(emit, cancel))
    events = await collect_until_end(q)
    assert [e.kind for e in events] == ["progress", "progress", "progress", "done"]
    assert all(e.job_id == job_id for e in events)
    assert r.current() is None


async def test_second_start_while_running_is_busy():
    r = JobRunner()
    q = r.subscribe()
    r.start("a", lambda emit, cancel: slow_job(emit, cancel))
    assert r.current()["name"] == "a"
    with pytest.raises(JobBusyError):
        r.start("b", lambda emit, cancel: slow_job(emit, cancel))
    await collect_until_end(q)


async def test_cancel():
    r = JobRunner()
    q = r.subscribe()
    job_id = r.start("a", lambda emit, cancel: slow_job(emit, cancel, steps=50))
    await asyncio.sleep(0.12)
    r.cancel(job_id)
    events = await collect_until_end(q)
    assert events[-1].kind == "cancelled"


async def test_crash_becomes_error_event():
    async def boom(emit, cancel):
        raise RuntimeError("hỏng")

    r = JobRunner()
    q = r.subscribe()
    r.start("x", boom)
    events = await collect_until_end(q)
    assert events[-1].kind == "error"
    assert "hỏng" in events[-1].message
    assert r.current() is None


async def test_unsubscribe():
    r = JobRunner()
    q = r.subscribe()
    r.unsubscribe(q)
    r.start("a", lambda emit, cancel: slow_job(emit, cancel, steps=1))
    await asyncio.sleep(0.2)
    assert q.empty()

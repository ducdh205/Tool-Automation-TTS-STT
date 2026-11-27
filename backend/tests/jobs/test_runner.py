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
    assert r.jobs() == []


async def test_second_start_while_running_is_busy():
    r = JobRunner()
    q = r.subscribe()
    r.start("a", lambda emit, cancel: slow_job(emit, cancel))
    assert r.busy()["name"] == "a"
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
    assert r.busy() is None


async def test_unsubscribe():
    r = JobRunner()
    q = r.subscribe()
    r.unsubscribe(q)
    r.start("a", lambda emit, cancel: slow_job(emit, cancel, steps=1))
    await asyncio.sleep(0.2)
    assert q.empty()


async def test_lanes_run_side_by_side_on_different_sets():
    r = JobRunner()
    q = r.subscribe()
    a = r.start("gen", lambda emit, cancel: slow_job(emit, cancel), lane="block1", set_id=1)
    b = r.start("app", lambda emit, cancel: slow_job(emit, cancel), lane="block2", set_id=2)
    assert [(j["id"], j["lane"], j["set_id"]) for j in r.jobs()] == [(a, "block1", 1), (b, "block2", 2)]
    with pytest.raises(JobBusyError):  # one job per lane
        r.start("gen2", lambda emit, cancel: slow_job(emit, cancel), lane="block1", set_id=3)
    ended = set()
    while len(ended) < 2:
        e = await asyncio.wait_for(q.get(), 5)
        assert e.lane == ("block1" if e.job_id == a else "block2")
        if e.kind == "done":
            ended.add(e.job_id)
    assert ended == {a, b} and r.jobs() == []


async def test_same_set_blocks_only_an_exclusive_job():
    r = JobRunner()
    q = r.subscribe()
    r.start("app", lambda emit, cancel: slow_job(emit, cancel), lane="block2", set_id=1)
    with pytest.raises(JobBusyError, match="cùng bộ audio"):
        r.start("regen", lambda emit, cancel: slow_job(emit, cancel), lane="block1", set_id=1, exclusive=True)
    assert r.conflict("block1", 2, exclusive=True) is None
    r.start("gen", lambda emit, cancel: slow_job(emit, cancel), lane="block1", set_id=1)  # fills other rows
    ended = 0
    while ended < 2:
        e = await asyncio.wait_for(q.get(), 5)
        ended += e.kind == "done"


async def test_block2_waits_for_an_exclusive_job_on_its_set():
    r = JobRunner()
    q = r.subscribe()
    r.start("regen", lambda emit, cancel: slow_job(emit, cancel), lane="block1", set_id=1, exclusive=True)
    with pytest.raises(JobBusyError):
        r.start("app", lambda emit, cancel: slow_job(emit, cancel), lane="block2", set_id=1)
    assert r.conflict("block2", 2) is None
    await collect_until_end(q)

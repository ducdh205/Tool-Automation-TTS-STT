"""Background jobs with progress events fan-out.

One job per lane at a time (Block 1 and Block 2 each have a lane). Jobs of both lanes may share an
audio set unless one of them is ``exclusive`` on it: "Sinh lại" swaps the WAVs Block 2 plays, while
"Sinh audio" only fills rows without audio (Block 2 never tests those) and Verify only reads WAVs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

_LOG = logging.getLogger(__name__)

EventKind = Literal["item", "progress", "log", "done", "error", "cancelled"]
Lane = Literal["block1", "block2"]
TERMINAL = ("done", "error", "cancelled")


@dataclass
class ProgressEvent:
    job_id: str
    kind: EventKind
    done: int
    total: int
    item: dict | None = None
    message: str | None = None
    lane: Lane | None = None  # filled in by the runner

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


Emit = Callable[[ProgressEvent], None]
JobFactory = Callable[[Emit, asyncio.Event], Awaitable[None]]


class JobBusyError(Exception):
    """A job that conflicts with the new one is already running."""


_PUBLIC = ("id", "name", "done", "total", "lane", "set_id", "exclusive")


class JobRunner:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[ProgressEvent]] = []
        self._jobs: dict[str, dict[str, Any]] = {}  # insertion order = start order

    def subscribe(self) -> asyncio.Queue[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[ProgressEvent]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def jobs(self) -> list[dict[str, Any]]:
        """Running jobs, oldest first."""
        return [{k: j[k] for k in _PUBLIC} for j in self._jobs.values()]

    def busy(self) -> dict[str, Any] | None:
        """Any running job (oldest), for actions that must wait for every job."""
        jobs = self.jobs()
        return jobs[0] if jobs else None

    def conflict(self, lane: Lane, set_id: int | None, exclusive: bool = False) -> dict[str, Any] | None:
        """The running job a new ``lane`` job on ``set_id`` would clash with, if any."""
        for j in self.jobs():
            if j["lane"] == lane:
                return j
            if set_id is not None and j["set_id"] == set_id and (exclusive or j["exclusive"]):
                return j
        return None

    def check(self, lane: Lane, set_id: int | None, exclusive: bool = False) -> None:
        j = self.conflict(lane, set_id, exclusive)
        if j is not None:
            same_set = set_id is not None and j["set_id"] == set_id and j["lane"] != lane
            hint = " (cùng bộ audio)" if same_set else ""
            raise JobBusyError(f"Đang chạy: {j['name']}{hint}")

    def start(self, name: str, factory: JobFactory, *, lane: Lane = "block1", set_id: int | None = None,
              exclusive: bool = False) -> str:
        """``exclusive``: no job of the other lane may run on ``set_id`` meanwhile."""
        self.check(lane, set_id, exclusive)
        job_id = uuid.uuid4().hex[:12]
        cancel = asyncio.Event()
        job: dict[str, Any] = {"id": job_id, "name": name, "done": 0, "total": 0, "lane": lane,
                               "set_id": set_id, "exclusive": exclusive, "cancel": cancel}
        self._jobs[job_id] = job

        def emit(event: ProgressEvent) -> None:
            event.job_id = job_id
            event.lane = lane
            if job_id in self._jobs:
                job["done"], job["total"] = event.done, event.total
            for q in list(self._subscribers):
                q.put_nowait(event)

        async def wrapper() -> None:
            ended = False

            def tracking_emit(event: ProgressEvent) -> None:
                nonlocal ended
                ended = ended or event.kind in TERMINAL
                if event.kind in TERMINAL:
                    self._jobs.pop(job_id, None)
                emit(event)

            try:
                await factory(tracking_emit, cancel)
            except Exception as e:  # report, never crash the server
                _LOG.exception("job %s failed", name)
                self._jobs.pop(job_id, None)
                emit(ProgressEvent(job_id, "error", job["done"], job["total"], message=str(e)))
                return
            if not ended:
                self._jobs.pop(job_id, None)
                emit(ProgressEvent(job_id, "done", 0, 0))

        job["task"] = asyncio.create_task(wrapper())
        return job_id

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job["cancel"].set()
        return True

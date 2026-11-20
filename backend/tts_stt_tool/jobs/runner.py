"""Single background job at a time, with progress events fan-out."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

_LOG = logging.getLogger(__name__)

EventKind = Literal["item", "progress", "log", "done", "error", "cancelled"]
TERMINAL = ("done", "error", "cancelled")


@dataclass
class ProgressEvent:
    job_id: str
    kind: EventKind
    done: int
    total: int
    item: dict | None = None
    message: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


Emit = Callable[[ProgressEvent], None]
JobFactory = Callable[[Emit, asyncio.Event], Awaitable[None]]


class JobBusyError(Exception):
    """Another job is already running."""


class JobRunner:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[ProgressEvent]] = []
        self._job: dict[str, Any] | None = None

    def subscribe(self) -> asyncio.Queue[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[ProgressEvent]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def current(self) -> dict[str, Any] | None:
        if self._job is None:
            return None
        return {k: self._job[k] for k in ("id", "name", "done", "total")}

    def start(self, name: str, factory: JobFactory) -> str:
        if self._job is not None:
            raise JobBusyError(f"Đang chạy: {self._job['name']}")
        job_id = uuid.uuid4().hex[:12]
        cancel = asyncio.Event()
        self._job = {"id": job_id, "name": name, "done": 0, "total": 0, "cancel": cancel}

        def emit(event: ProgressEvent) -> None:
            event.job_id = job_id
            if self._job and self._job["id"] == job_id:
                self._job["done"], self._job["total"] = event.done, event.total
            for q in list(self._subscribers):
                q.put_nowait(event)

        async def wrapper() -> None:
            ended = False

            def tracking_emit(event: ProgressEvent) -> None:
                nonlocal ended
                ended = ended or event.kind in TERMINAL
                if event.kind in TERMINAL:
                    self._job = None
                emit(event)

            try:
                await factory(tracking_emit, cancel)
            except Exception as e:  # report, never crash the server
                _LOG.exception("job %s failed", name)
                done, total = (self._job or {}).get("done", 0), (self._job or {}).get("total", 0)
                self._job = None
                emit(ProgressEvent(job_id, "error", done, total, message=str(e)))
                return
            if not ended:
                self._job = None
                emit(ProgressEvent(job_id, "done", 0, 0))

        self._job["task"] = asyncio.create_task(wrapper())
        return job_id

    def cancel(self, job_id: str) -> bool:
        if self._job and self._job["id"] == job_id:
            self._job["cancel"].set()
            return True
        return False

"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tts_stt_tool.config import Settings
from tts_stt_tool.device.adb import Adb
from tts_stt_tool.jobs.runner import JobRunner
from tts_stt_tool.store.db import Store
from tts_stt_tool.stt.server_manager import REPO_ROOT, WyomingServerManager, default_wyoming_launch
from tts_stt_tool.stt.wyoming_client import SttEngine, WyomingStt
from tts_stt_tool.tts.base import TtsEngine, VoiceInfo
from tts_stt_tool.tts.cache import AudioCache

_LOG = logging.getLogger(__name__)
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@dataclass
class AppContext:
    settings: Settings
    store: Store
    cache: AudioCache
    runner: JobRunner
    tts: TtsEngine
    stt: SttEngine
    wyoming: WyomingServerManager | None
    voices: list[VoiceInfo] | None = None
    wyoming_error: str | None = None
    background: set = field(default_factory=set)
    adb: Adb = field(default_factory=Adb)
    device_factory: Callable[[str], Awaitable[Any]] | None = None  # serial -> DeviceDriver
    player: Any = None  # AudioPlayer
    busy_serial: str | None = None  # phone driven by a running block 2 job
    exports: dict[str, tuple[Path, str]] = field(default_factory=dict)  # one-time token -> (zip, download name)

    @property
    def profiles_dir(self) -> Path:
        return self.settings.data_dir / "profiles"

    async def device(self, serial: str) -> Any:
        if self.device_factory is not None:
            return await self.device_factory(serial)
        from tts_stt_tool.pipeline.block2 import AdbDriver

        return await AdbDriver.connect(self.adb, serial)

    @property
    def uploads(self) -> Path:
        return self.settings.data_dir / "uploads"

    @property
    def reports(self) -> Path:
        return self.settings.data_dir / "reports"

    @property
    def exports_dir(self) -> Path:
        """Session zips waiting for their one-time download."""
        return self.reports / "exports"

    def run_dir(self, run_id: int) -> Path:
        """Files produced while an app run executes (screenshots)."""
        return self.settings.data_dir / "app_runs" / str(run_id)


def _wyoming_manager(settings: Settings) -> WyomingServerManager:
    if settings.wyoming_cmd:
        return WyomingServerManager(settings.wyoming_cmd, settings.wyoming_host, settings.wyoming_port,
                                    log_path=settings.data_dir / "wyoming" / "server.log")
    cmd, cwd, env = default_wyoming_launch(settings.data_dir, settings.wyoming_port)
    return WyomingServerManager(cmd, settings.wyoming_host, settings.wyoming_port, cwd=cwd, env=env,
                                log_path=settings.data_dir / "wyoming" / "server.log",
                                start_timeout_s=300)


def create_app(
    settings: Settings,
    *,
    tts: TtsEngine | None = None,
    stt: SttEngine | None = None,
    manage_wyoming: bool = True,
    device_factory: Callable[[str], Awaitable[Any]] | None = None,
    player: Any = None,
) -> FastAPI:
    from tts_stt_tool.api.routes import router
    from tts_stt_tool.api.ws import ws_router

    if tts is None:
        from tts_stt_tool.tts.vieneu_engine import VieneuEngine

        tts = VieneuEngine()
    ctx = AppContext(
        settings=settings,
        store=Store(settings.data_dir / "tool.db"),
        cache=AudioCache(settings.data_dir / "audio"),
        runner=JobRunner(),
        tts=tts,
        stt=stt or WyomingStt(settings.wyoming_host, settings.wyoming_port, settings.stt_timeout_s),
        wyoming=_wyoming_manager(settings) if manage_wyoming else None,
        device_factory=device_factory,
        player=player,
    )
    if ctx.player is None:
        from tts_stt_tool.device.player import WinSoundPlayer

        ctx.player = WinSoundPlayer()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if ctx.wyoming is not None:
            async def start() -> None:
                try:
                    await ctx.wyoming.ensure_running()
                    ctx.wyoming_error = None
                except Exception as e:  # app keeps running; /health shows it
                    ctx.wyoming_error = str(e)
                    _LOG.error("wyoming: %s", e)

            task = asyncio.create_task(start())
            ctx.background.add(task)
            task.add_done_callback(ctx.background.discard)
        yield
        if ctx.wyoming is not None:
            ctx.wyoming.stop()

    app = FastAPI(title="TTS-STT Automation Test", lifespan=lifespan)
    app.state.ctx = ctx
    app.include_router(router, prefix="/api")
    app.include_router(ws_router)
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
    return app

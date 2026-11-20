"""Start / check the wyoming-vietnamese server process."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from tts_stt_tool.stt.wyoming_client import SttError

REPO_ROOT = Path(__file__).resolve().parents[3]
VENDOR_DIR = REPO_ROOT / "vendor" / "wyoming-vietnamese"
LAUNCHER = Path(__file__).with_name("wyoming_win_launcher.py")


def default_wyoming_launch(data_dir: Path, port: int) -> tuple[list[str], Path, dict[str, str]]:
    """Command, cwd and env to run vendor/wyoming-vietnamese (see docs/spikes)."""
    python = VENDOR_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = VENDOR_DIR / ".venv" / "bin" / "python"
    wy = (data_dir / "wyoming").resolve()
    env = {
        "CACHE_DIR": str(wy / "cache"),
        "DOWNLOAD_DIR": str(wy / "models"),
        "WYOMING_PORT": str(port),
        "PYTHONIOENCODING": "utf-8",
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
    }
    return [str(python), str(LAUNCHER)], VENDOR_DIR, env


async def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


class WyomingServerManager:
    def __init__(
        self,
        cmd: list[str],
        host: str,
        port: int,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        log_path: Path | None = None,
        start_timeout_s: float = 120.0,
    ) -> None:
        self.cmd = cmd
        self.host = host
        self.port = port
        self.cwd = cwd
        self.env = env or {}
        self.log_path = log_path
        self.start_timeout_s = start_timeout_s
        self.process: subprocess.Popen | None = None

    async def is_up(self) -> bool:
        return await port_open(self.host, self.port)

    async def ensure_running(self) -> None:
        if await self.is_up():
            return
        if self.process is None or self.process.poll() is not None:
            log = subprocess.DEVNULL
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                log = self.log_path.open("ab")
            try:
                self.process = subprocess.Popen(
                    self.cmd,
                    cwd=self.cwd,
                    env={**os.environ, **self.env},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as e:
                raise SttError(f"Không khởi động được wyoming: {e}") from e
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.start_timeout_s
        while loop.time() < deadline:
            if await self.is_up():
                return
            code = self.process.poll()
            if code is not None:
                raise SttError(f"Wyoming đã thoát (mã {code}) — xem log {self.log_path or ''}")
            await asyncio.sleep(0.5)
        raise SttError(f"Wyoming không mở cổng {self.port} sau {self.start_timeout_s:g}s")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

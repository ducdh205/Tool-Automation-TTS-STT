"""GPU readiness for VieNeu: is there an NVIDIA card, does torch see CUDA, and installing PyTorch CUDA.

Everything runs as a subprocess so the answer is fresh (an in-process ``import torch`` would stick to
whatever was installed when the app started) and so tests can swap in stand-in commands.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

_LOG = logging.getLogger(__name__)

TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
LOG_TAIL = 20
_DEFAULT: Any = object()


@dataclass
class GpuProbe:
    nvidia: bool
    gpu_name: str | None
    torch_cuda: bool


def default_install_cmd() -> list[str] | None:
    uv = shutil.which("uv")
    if uv is None:
        return None
    return [uv, "pip", "install", "--python", sys.executable, "torch", "--index-url", TORCH_CUDA_INDEX]


async def _run(cmd: list[str], timeout: float = 60) -> tuple[int, str]:
    """(exit code, stdout); a missing program counts as exit code 127."""
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return 127, ""
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, ""
    return proc.returncode or 0, out.decode("utf-8", "replace")


class GpuSetup:
    def __init__(self, *, nvidia_cmd: list[str] | None = None, torch_cmd: list[str] | None = None,
                 install_cmd: list[str] | None = _DEFAULT) -> None:
        self.nvidia_cmd = nvidia_cmd or ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
        self.torch_cmd = torch_cmd or [sys.executable, "-c",
                                       "import sys, torch; sys.exit(0 if torch.cuda.is_available() else 1)"]
        self.install_cmd = default_install_cmd() if install_cmd is _DEFAULT else install_cmd
        self._probe: GpuProbe | None = None
        self._probe_lock = asyncio.Lock()
        self._state = "idle"
        self._log: deque[str] = deque(maxlen=LOG_TAIL)
        self._error: str | None = None
        self._task: asyncio.Task | None = None

    @property
    def can_install(self) -> bool:
        return self.install_cmd is not None

    async def probe(self, refresh: bool = False) -> GpuProbe:
        async with self._probe_lock:
            if self._probe is None or refresh:
                code, out = await _run(self.nvidia_cmd, timeout=15)
                name = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else None
                torch_code, _ = await _run(self.torch_cmd)
                self._probe = GpuProbe(nvidia=name is not None, gpu_name=name, torch_cuda=torch_code == 0)
            return self._probe

    def install_state(self) -> dict:
        return {"state": self._state, "log_tail": list(self._log), "error": self._error}

    def start_install(self, on_done: Callable[[], None]) -> bool:
        """Start installing PyTorch CUDA in the background; False when an install is already running."""
        if self._state == "running":
            return False
        self._state, self._error = "running", None
        self._log.clear()
        self._task = asyncio.get_running_loop().create_task(self._install(on_done))
        return True

    async def _install(self, on_done: Callable[[], None]) -> None:
        try:
            if self.install_cmd is None:
                return self._fail("Không tìm thấy uv")
            proc = await asyncio.create_subprocess_exec(*self.install_cmd, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT)
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self._log.append(line)
            code = await proc.wait()
            if code != 0:
                return self._fail(f"Cài PyTorch CUDA thất bại (mã {code})")
            if not (await self.probe(refresh=True)).torch_cuda:
                return self._fail("Đã cài PyTorch nhưng không dùng được CUDA — kiểm tra driver NVIDIA")
            self._state = "done"
            on_done()
        except Exception as e:  # never leave the panel stuck on "running"
            _LOG.exception("install torch cuda")
            self._fail(f"Cài PyTorch CUDA thất bại: {e}")

    def _fail(self, error: str) -> None:
        self._state, self._error = "failed", error

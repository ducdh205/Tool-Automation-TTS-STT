"""The "Kết nối iPhone" button: start WebDriverAgent on a USB iPhone from Windows.

What used to be typed by hand, in order:

1. ``pymobiledevice3 mounter auto-mount``                       developer disk image (one-shot)
2. ``pymobiledevice3 developer dvt xcuitest <WDA> --userspace`` keeps WDA running on the phone
3. ``ios.exe forward 8100 8100``                                 keeps the port forwarded

then wait until WDA answers ``/status``. Processes 2 and 3 belong to the tool and stop with it.
pymobiledevice3 runs in the tool's own Python (``sys.executable -m pymobiledevice3``), so the
portable folder needs nothing extra installed except Apple's USB driver (Apple Devices / iTunes).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from tts_stt_tool.device.goios import GoIos, GoIosError, last_json
from tts_stt_tool.device.wda import WdaClient
from tts_stt_tool.stt.winjob import kill_with_this_process

_LOG = logging.getLogger(__name__)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WDA_DEVICE_PORT = 8100
PYMD3 = [sys.executable, "-m", "pymobiledevice3"]


class Proc(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


Spawn = Callable[[list[str], Path], Proc]  # long-running process, output appended to the log file
Run = Callable[[list[str], float], Awaitable[tuple[int, str]]]  # one-shot: (exit code, output)


def _spawn(args: list[str], log: Path) -> Proc:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as f:
        proc = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=_NO_WINDOW)
    kill_with_this_process(proc)  # closing the tool's window must not leave port 8100 taken
    return proc


async def _run(args: list[str], timeout_s: float) -> tuple[int, str]:
    def go() -> tuple[int, str]:
        try:
            r = subprocess.run(args, capture_output=True, timeout=timeout_s, stdin=subprocess.DEVNULL,
                               creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return -1, "quá thời gian"
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")

    return await asyncio.to_thread(go)


# (pieces of pymobiledevice3 / go-ios output, what the user should do). First match wins.
_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("developermode", "developer mode"),
     "Chưa bật Chế độ nhà phát triển trên iPhone: Cài đặt → Quyền riêng tư & Bảo mật → "
     "Chế độ nhà phát triển → Bật, máy khởi động lại rồi bấm Bật lần nữa."),
    (("passwordprotected", "device is locked"), "Mở khóa iPhone rồi bấm Kết nối lại."),
    (("pairingdialogresponsepending", "notpaired", "userdeniedpairing", "invalidhostid", "pairing"),
     "Mở khóa iPhone, bấm “Tin cậy” máy tính này (nhập mật mã nếu được hỏi) rồi bấm Kết nối lại."),
    (("usbmux", "apple mobile device", "connectionrefusederror", "no such file or directory: '//./pipe"),
     "Không kết nối được dịch vụ USB của Apple: cài app “Apple Devices” (Microsoft Store) "
     "hoặc iTunes, rồi cắm lại iPhone."),
    (("tss request", "personalized image", "getaddrinfo", "nodename nor servname"),
     "Không tải/ký được ảnh đĩa nhà phát triển: lần đầu (và sau mỗi lần iPhone khởi động lại) "
     "máy tính cần có Internet."),
    (("not been explicitly trusted", "untrusted", "invalid code signature", "profile has expired",
      "failed to launch", "unable to launch", "requestdenied", "launch failed"),
     "iPhone không mở được WebDriverAgent: chữ ký WDA có thể đã hết hạn (cài lại WDA) hoặc chưa tin cậy "
     "nhà phát triển (Cài đặt → Cài đặt chung → Quản lý VPN & thiết bị → Tin cậy)."),
]


def explain(output: str) -> str | None:
    low = output.lower()
    for needles, hint in _HINTS:
        if any(n in low for n in needles):
            return hint
    return None


def _tail(text: str, n: int = 400) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-6:])[-n:]


def find_wda_bundle(apps_output: str) -> str | None:
    """The installed WDA runner in ``ios apps`` output (bundle id varies with who signed it)."""
    ids = [a.get("CFBundleIdentifier", "") for a in last_json(apps_output) or [] if isinstance(a, dict)]
    wda = [i for i in ids if "webdriveragentrunner" in i.lower()]
    return next((i for i in wda if "xctrunner" in i.lower()), wda[0] if wda else None)


class LaunchError(RuntimeError):
    pass


@dataclass
class LauncherStatus:
    state: str = "idle"  # idle | starting | running | error
    step: str | None = None  # what is happening now (Vietnamese, shown under the button)
    error: str | None = None
    detail: str | None = None  # last lines of the failing command, for "Chi tiết"
    udid: str | None = None
    bundle: str | None = None
    external: bool = False  # WDA already answered before we started anything

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


class WdaLauncher:
    def __init__(self, goios: GoIos, wda: WdaClient, log_dir: Path, *, wda_url: str = "http://127.0.0.1:8100",
                 spawn: Spawn = _spawn, run: Run = _run, ready_timeout_s: float = 90.0,
                 mount_timeout_s: float = 300.0, poll_s: float = 1.0) -> None:
        self.goios, self.wda, self.log_dir = goios, wda, log_dir
        self.local_port = urlparse(wda_url).port or WDA_DEVICE_PORT
        self._spawn, self._run = spawn, run
        self.ready_timeout_s, self.mount_timeout_s, self.poll_s = ready_timeout_s, mount_timeout_s, poll_s
        self.status = LauncherStatus()
        self._procs: dict[str, Proc] = {}
        self._task: asyncio.Task | None = None

    @property
    def available(self) -> bool:
        return self.goios.available

    # -- public -----------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Status for the UI; notices WDA dying after a successful start (cable pulled, phone locked…)."""
        s = self.status
        if s.state == "running" and not s.external:
            dead = [name for name, p in self._procs.items() if p.poll() is not None]
            if dead:
                log = self._read_log("xcuitest" if "xcuitest" in dead else "forward")
                self._kill()
                self.status = LauncherStatus(
                    "error", error=explain(log) or "WebDriverAgent đã dừng (rút cáp hoặc iPhone khóa?) — bấm Kết nối lại.",
                    detail=_tail(log), udid=s.udid, bundle=s.bundle)
        return self.status.to_json()

    def start(self) -> dict[str, Any]:
        """Begin connecting in the background (no-op while already starting)."""
        if self._task is None or self._task.done():
            self.status = LauncherStatus("starting", step="Đang tìm iPhone…")
            self._task = asyncio.create_task(self._connect())
        return self.snapshot()

    async def wait(self) -> None:
        if self._task is not None:
            await asyncio.shield(self._task)

    def stop(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._kill()
        self.status = LauncherStatus()
        return self.status.to_json()

    # -- steps --------------------------------------------------------------------
    def _step(self, text: str) -> None:
        self.status.step = text
        _LOG.info("iPhone: %s", text)

    async def _connect(self) -> None:
        try:
            await self._connect_steps()
        except asyncio.CancelledError:
            self._kill()
            raise
        except LaunchError as e:
            self._kill()
            self.status.state, self.status.step = "error", None
            self.status.error = str(e)
        except Exception as e:  # noqa: BLE001 — anything else still ends in a readable state
            _LOG.exception("iPhone: kết nối lỗi")
            self._kill()
            self.status.state, self.status.step, self.status.error = "error", None, f"Lỗi không mong đợi: {e}"

    async def _connect_steps(self) -> None:
        if await self.wda.ready():
            self.status = LauncherStatus("running", external=True)
            return
        self._kill()  # leftovers of an earlier attempt

        try:
            devices = await self.goios.devices()
        except GoIosError as e:
            raise LaunchError(explain(str(e)) or f"Không đọc được danh sách iPhone: {e}") from e
        if not devices:
            raise LaunchError("Chưa thấy iPhone: cắm cáp USB, mở khóa máy và bấm “Tin cậy” máy tính này. "
                              "Nếu vẫn không thấy, cài app “Apple Devices” (Microsoft Store) hoặc iTunes.")
        udid = devices[0].udid
        self.status.udid = udid

        self._step("Đang tìm WebDriverAgent trên iPhone…")
        try:
            bundle = find_wda_bundle(await self.goios.run("apps", f"--udid={udid}"))
        except GoIosError as e:
            raise LaunchError(explain(str(e)) or f"Không đọc được danh sách app trên iPhone: {e}") from e
        if not bundle:
            raise LaunchError("iPhone chưa cài WebDriverAgent: cài file WDA.ipa (Sideloadly) theo hướng dẫn rồi thử lại.")
        self.status.bundle = bundle

        self._step("Đang gắn ảnh đĩa nhà phát triển (lần đầu có thể mất 1–2 phút)…")
        rc, out = await self._run([*PYMD3, "mounter", "auto-mount", "--udid", udid], self.mount_timeout_s)
        if rc != 0 and "already mounted" not in out.lower():
            raise LaunchError(self._fail("Gắn ảnh đĩa nhà phát triển lỗi", out))

        self._step("Đang mở WebDriverAgent trên iPhone…")
        self._start_proc("xcuitest", [*PYMD3, "developer", "dvt", "xcuitest", bundle, "--userspace", "--udid", udid])
        self._step("Đang chuyển cổng kết nối…")
        self._start_proc("forward", [str(self.goios.path), "forward", str(self.local_port), str(WDA_DEVICE_PORT),
                                     f"--udid={udid}"])

        self._step("Đang chờ WebDriverAgent sẵn sàng…")
        deadline = time.monotonic() + self.ready_timeout_s
        while time.monotonic() < deadline:
            if await self.wda.ready():
                self.status.state, self.status.step = "running", None
                return
            for name, p in self._procs.items():
                if p.poll() is not None:
                    what = "WebDriverAgent" if name == "xcuitest" else "Chuyển cổng"
                    raise LaunchError(self._fail(f"{what} dừng ngay khi khởi động", self._read_log(name)))
            await asyncio.sleep(self.poll_s)
        raise LaunchError(self._fail("WebDriverAgent không trả lời sau "
                                     f"{int(self.ready_timeout_s)} giây — mở khóa iPhone rồi thử lại",
                                     self._read_log("xcuitest")))

    # -- helpers --------------------------------------------------------------------
    def _fail(self, what: str, output: str) -> str:
        self.status.detail = _tail(output) or None
        hint = explain(output)
        return f"{what}. {hint}" if hint else f"{what}."

    def _log(self, name: str) -> Path:
        return self.log_dir / f"{name}.log"

    def _read_log(self, name: str) -> str:
        try:
            return self._log(name).read_text(encoding="utf-8", errors="replace")[-20000:]
        except OSError:
            return ""

    def _start_proc(self, name: str, args: list[str]) -> None:
        log = self._log(name)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")  # one attempt per log file
        self._procs[name] = self._spawn(args, log)

    def _kill(self) -> None:
        for p in self._procs.values():
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        self._procs.clear()

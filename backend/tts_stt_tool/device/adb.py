"""Android device access through the stock ``adb`` binary (no APK installed on the phone)."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tts_stt_tool.stt.server_manager import REPO_ROOT

VENDOR_ADB = REPO_ROOT / "vendor" / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UI_DUMP_PATH = "/sdcard/tts_stt_ui.xml"


class AdbError(RuntimeError):
    pass


@dataclass
class DeviceInfo:
    serial: str
    state: str  # device | unauthorized | offline | ...
    model: str | None = None

    def to_json(self) -> dict:
        return {"serial": self.serial, "state": self.state, "model": self.model}


def find_adb() -> Path | None:
    if VENDOR_ADB.exists():
        return VENDOR_ADB
    found = shutil.which("adb")
    return Path(found) if found else None


def parse_devices(output: str) -> list[DeviceInfo]:
    """Parse ``adb devices -l``."""
    out: list[DeviceInfo] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), None)
        out.append(DeviceInfo(parts[0], parts[1], model))
    return out


class Adb:
    def __init__(self, path: Path | None = None, timeout_s: float = 10.0) -> None:
        self.path = path or find_adb()
        self.timeout_s = timeout_s
        self._screen_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self.path is not None

    def _run(self, *args: str) -> bytes:
        if self.path is None:
            raise AdbError("Không tìm thấy adb (đặt platform-tools vào vendor/platform-tools)")
        try:
            r = subprocess.run([str(self.path), *args], capture_output=True, timeout=self.timeout_s,
                               creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"adb {' '.join(args)}: quá thời gian") from e
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).decode("utf-8", "replace").strip()
            raise AdbError(msg or f"adb {' '.join(args)} lỗi {r.returncode}")
        return r.stdout

    async def run(self, *args: str) -> bytes:
        return await asyncio.to_thread(self._run, *args)

    async def devices(self) -> list[DeviceInfo]:
        return parse_devices((await self.run("devices", "-l")).decode("utf-8", "replace"))

    async def screencap(self, serial: str) -> bytes:
        """PNG of the current screen."""
        async with self._screen_lock:  # one capture at a time; phones choke on parallel screencap
            png = await self.run("-s", serial, "exec-out", "screencap", "-p")
        if not png.startswith(b"\x89PNG"):
            raise AdbError("screencap không trả về ảnh PNG")
        return png

    async def dump_ui(self, serial: str, attempts: int = 3) -> str:
        """``uiautomator dump`` XML; retries because it fails while the screen animates."""
        last = ""
        for _ in range(attempts):
            try:
                await self.run("-s", serial, "shell", "uiautomator", "dump", UI_DUMP_PATH)
                xml = (await self.run("-s", serial, "exec-out", "cat", UI_DUMP_PATH)).decode("utf-8", "replace")
            except AdbError as e:
                last = str(e)
                continue
            if "<hierarchy" in xml:
                return xml
            last = xml.strip()[:200]
        raise AdbError(f"uiautomator dump lỗi sau {attempts} lần: {last}")

    async def mic_active(self, serial: str) -> bool:
        """~0.1 s, unlike a UI dump (~2.5 s): used to start playback the moment the app listens."""
        return parse_mic_active((await self.run("-s", serial, "shell", "dumpsys", "audio")).decode("utf-8", "replace"))

    async def screen_size(self, serial: str) -> tuple[int, int]:
        return parse_wm_size((await self.run("-s", serial, "shell", "wm", "size")).decode("utf-8", "replace"))

    async def launch(self, serial: str, package: str) -> None:
        await self.run("-s", serial, "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

    async def app_version(self, serial: str, package: str) -> str | None:
        out = (await self.run("-s", serial, "shell", "dumpsys", "package", package)).decode("utf-8", "replace")
        m = re.search(r"versionName=(\S+)", out)
        return m.group(1) if m else None

    async def tap(self, serial: str, x: int, y: int) -> None:
        await self.run("-s", serial, "shell", "input", "tap", str(x), str(y))

    async def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        await self.run("-s", serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    async def key(self, serial: str, keycode: str) -> None:
        await self.run("-s", serial, "shell", "input", "keyevent", keycode)

    async def text(self, serial: str, text: str) -> None:
        """Type ASCII text (``input text`` cannot type Vietnamese diacritics)."""
        await self.run("-s", serial, "shell", "input", "text", escape_input_text(text))


_MIC_ACTIVE = re.compile(r"riid \d+; active\? true")


def parse_mic_active(dumpsys_audio: str) -> bool:
    """True while some app records from the microphone (``dumpsys audio`` RecordActivityMonitor)."""
    return bool(_MIC_ACTIVE.search(dumpsys_audio))


def parse_wm_size(output: str) -> tuple[int, int]:
    """``wm size`` -> (w, h); an "Override size" wins over the physical one."""
    sizes = dict(re.findall(r"(Physical|Override) size: (\d+x\d+)", output))
    raw = sizes.get("Override") or sizes.get("Physical")
    if not raw:
        raise AdbError(f"Không đọc được kích thước màn hình: {output.strip()[:100]}")
    w, h = raw.split("x")
    return int(w), int(h)


KEYS = {"back": "KEYCODE_BACK", "home": "KEYCODE_HOME", "recents": "KEYCODE_APP_SWITCH",
        "enter": "KEYCODE_ENTER", "del": "KEYCODE_DEL", "power": "KEYCODE_POWER",
        "volup": "KEYCODE_VOLUME_UP", "voldown": "KEYCODE_VOLUME_DOWN"}


def escape_input_text(text: str) -> str:
    """Escape for ``adb shell input text`` (runs through the device's sh)."""
    out = []
    for ch in text:
        if ch == " ":
            out.append("%s")
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch.isascii() and ch.isprintable():
            out.append("\\" + ch)
        else:
            raise AdbError("Chỉ gõ được chữ không dấu (adb input text không hỗ trợ tiếng Việt có dấu)")
    return "".join(out)

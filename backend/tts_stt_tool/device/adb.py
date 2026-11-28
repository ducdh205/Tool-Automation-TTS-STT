"""Android device access through the stock ``adb`` binary (no APK installed on the phone)."""

from __future__ import annotations

import asyncio
import os
import re
import struct
import uuid
import zlib
import xml.etree.ElementTree as ET
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tts_stt_tool.stt.server_manager import REPO_ROOT

VENDOR_ADB = REPO_ROOT / "vendor" / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


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
        self._dump_locks: dict[str, asyncio.Lock] = {}
        # serial -> whether ``uiautomator dump /dev/tty`` works there (absent = not tried yet)
        self._tty_dump: dict[str, bool] = {}

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
        """PNG of the current screen.

        Raw pixels are encoded on the PC: the phone's own PNG encoder (``screencap -p``) takes
        most of the time a capture costs. A raw frame this code cannot read falls back to it.
        """
        async with self._screen_lock:  # one capture at a time; phones choke on parallel screencap
            raw = await self.run("-s", serial, "exec-out", "screencap")
            try:
                return await asyncio.to_thread(raw_to_png, raw)
            except ValueError:
                png = await self.run("-s", serial, "exec-out", "screencap", "-p")
        if not png.startswith(b"\x89PNG"):
            raise AdbError("screencap không trả về ảnh PNG")
        return png

    def _serial_lock(self, serial: str) -> asyncio.Lock:
        return self._dump_locks.setdefault(serial, asyncio.Lock())

    async def dump_ui(self, serial: str, attempts: int = 3) -> str:
        """``uiautomator dump`` XML. One dump per phone at a time (only one UiAutomation client can run).

        Fast path: ``exec-out uiautomator dump /dev/tty`` prints the XML in one adb call instead
        of four (rm, dump, cat, rm). A phone where that has never worked uses the sdcard file from
        then on; once it has worked, a failure is a flaky dump (screen animating) and is retried,
        with the file as a last resort.
        """
        async with self._serial_lock(serial):
            works = self._tty_dump.get(serial)
            if works is not False:
                for _ in range(attempts if works else 1):
                    try:
                        out = await self.run("-s", serial, "exec-out", "uiautomator", "dump", "/dev/tty")
                        xml = tty_dump_xml(out.decode("utf-8", "replace"))
                    except (AdbError, ValueError, ET.ParseError):
                        continue
                    self._tty_dump[serial] = True
                    return xml
                if works is None:
                    self._tty_dump[serial] = False
            return await self._dump_via_file(serial, attempts)

    async def _dump_via_file(self, serial: str, attempts: int) -> str:
        """A failed dump ("could not get idle state" while the screen animates) still exits 0 and
        leaves the previous file behind, so: own file per call, delete it first, require the
        "dumped to" confirmation and a parsable document; retry otherwise.
        """
        path = f"/sdcard/tts_stt_ui_{uuid.uuid4().hex[:8]}.xml"
        last = ""
        try:
            for _ in range(attempts):
                try:
                    await self.run("-s", serial, "shell", "rm", "-f", path)
                    out = (await self.run("-s", serial, "shell", "uiautomator", "dump", path)).decode("utf-8", "replace")
                    if "dumped to" not in out:
                        last = out.strip()[:200]
                        continue
                    xml = (await self.run("-s", serial, "exec-out", "cat", path)).decode("utf-8", "replace")
                    ET.fromstring(xml[xml.index("<"):])
                    return xml
                except (AdbError, ValueError, ET.ParseError) as e:
                    last = str(e)[:200]
        finally:
            try:
                await self.run("-s", serial, "shell", "rm", "-f", path)
            except AdbError:
                pass
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


_HIERARCHY_END = "</hierarchy>"


def tty_dump_xml(out: str) -> str:
    """The XML in ``uiautomator dump /dev/tty`` output (the XML, then "UI hierchary dumped to: …")."""
    if "dumped to" not in out:
        raise ValueError(out.strip()[:200] or "uiautomator dump: không có kết quả")
    xml = out[out.index("<"):out.rindex(_HIERARCHY_END) + len(_HIERARCHY_END)]
    ET.fromstring(xml)
    return xml


def raw_to_png(raw: bytes) -> bytes:
    """``screencap`` raw frame (w, h, format[, colour space] + RGBA/RGBX pixels) -> PNG.

    Pixels are forced opaque: RGBX frames leave the 4th byte undefined.
    """
    if len(raw) < 12:
        raise ValueError("screencap: khung ảnh quá ngắn")
    w, h, fmt = struct.unpack_from("<III", raw)
    size = w * h * 4
    header = len(raw) - size
    if fmt not in (1, 2) or not w or not h or header not in (12, 16):
        raise ValueError(f"screencap: không đọc được khung ảnh raw (format {fmt}, {w}x{h})")
    px = bytearray(raw[header:])
    px[3::4] = b"\xff" * (w * h)
    stride = w * 4
    rows = b"".join(b"\x00" + px[i:i + stride] for i in range(0, size, stride))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 3)) + chunk(b"IEND", b""))


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

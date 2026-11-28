"""Live H.264 mirror of an Android screen through scrcpy-server (view only).

``vendor/scrcpy/scrcpy-server`` (scrcpy v5.0.1, Apache-2.0) is pushed to /data/local/tmp and run
with ``app_process``: nothing is installed. The phone's hardware encoder produces the stream;
the PC only relays the packets to the browser, which decodes them (WebCodecs).

The server runs with audio, control and clipboard sync off and never touches the screen power,
so a test run sees the phone exactly as without it. In particular an audio capture would show up
in ``dumpsys audio`` as a recording client and fool :meth:`Adb.mic_active`.

Wire format: https://github.com/Genymobile/scrcpy/blob/v5.0.1/doc/develop.md (forward tunnel,
video socket only): dummy byte, 64-byte device name, u32 codec id, then 12-byte headers. A header
whose first bit is set is a session packet (u32 flags, u32 width, u32 height, sent per capture
session: start and each rotation); otherwise it is u64 PTS + flags (config, key frame) and the
u32 size of the payload that follows.
"""

from __future__ import annotations

import asyncio
import collections
import secrets
import struct
import subprocess
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass

from tts_stt_tool.device.adb import _NO_WINDOW, Adb, AdbError
from tts_stt_tool.stt.server_manager import REPO_ROOT

SERVER_VERSION = "5.0.1"  # must match the jar exactly
VENDOR_SERVER = REPO_ROOT / "vendor" / "scrcpy" / "scrcpy-server"
DEVICE_JAR = "/data/local/tmp/tts-stt-scrcpy.jar"

CODEC_H264 = 0x68323634
_SESSION = 1 << 63
_CONFIG = 1 << 62
_KEY = 1 << 61
_PTS_MASK = _KEY - 1
DEVICE_NAME_LEN = 64


class ScrcpyError(RuntimeError):
    pass


@dataclass
class Session:
    """A capture session: the stream's frame size (changes on rotation)."""
    width: int
    height: int


@dataclass
class Packet:
    data: bytes
    pts: int
    key: bool
    config: bool  # SPS/PPS (codec config); see :func:`merge_config`


def server_args(scid: str, max_size: int = 1024, max_fps: int = 30, bit_rate: int = 4_000_000) -> list[str]:
    return [
        f"CLASSPATH={DEVICE_JAR}", "app_process", "/", "com.genymobile.scrcpy.Server", SERVER_VERSION,
        f"scid={scid}", "log_level=info", "tunnel_forward=true",
        "video=true", "video_codec=h264", f"max_size={max_size}", f"max_fps={max_fps}",
        f"video_bit_rate={bit_rate}",
        # Test safety: no audio capture (would look like a mic client), no input, no clipboard,
        # no screen power changes.
        "audio=false", "control=false", "clipboard_autosync=false",
        "power_on=false", "stay_awake=false", "show_touches=false", "power_off_on_close=false",
    ]


async def read_handshake(reader: asyncio.StreamReader) -> str:
    """After the dummy byte: device name + codec id. Returns the device name."""
    name = (await reader.readexactly(DEVICE_NAME_LEN)).split(b"\0", 1)[0].decode("utf-8", "replace")
    (codec,) = struct.unpack(">I", await reader.readexactly(4))
    if codec in (0, 1):
        raise ScrcpyError("scrcpy-server không mở được luồng video" + (" (lỗi cấu hình)" if codec else ""))
    if codec != CODEC_H264:
        raise ScrcpyError(f"scrcpy-server trả về codec lạ 0x{codec:08x}")
    return name


async def read_stream(reader: asyncio.StreamReader) -> AsyncIterator[Session | Packet]:
    """Session and media packets until the server closes the socket."""
    while True:
        try:
            head = await reader.readexactly(12)
        except asyncio.IncompleteReadError:
            return
        (first,) = struct.unpack_from(">Q", head)
        if first & _SESSION:
            w, h = struct.unpack_from(">II", head, 4)
            yield Session(w, h)
            continue
        (size,) = struct.unpack_from(">I", head, 8)
        try:
            data = await reader.readexactly(size)
        except asyncio.IncompleteReadError:
            return
        yield Packet(data, first & _PTS_MASK, bool(first & _KEY), bool(first & _CONFIG))


async def merge_config(items: AsyncIterator[Session | Packet]) -> AsyncIterator[Session | Packet]:
    """Glue each config packet (SPS/PPS) to the frame after it, as the scrcpy client does.

    The merged packet keeps ``config=True`` so the browser (re)configures its decoder from it.
    """
    pending: bytes | None = None
    async for item in items:
        if isinstance(item, Packet):
            if item.config:
                pending = (pending or b"") + item.data
                continue
            if pending is not None:
                item = Packet(pending + item.data, item.pts, item.key, True)
                pending = None
        yield item


class ScrcpyStream:
    """One scrcpy-server on one phone; :meth:`close` stops it and removes the adb forward."""

    def __init__(self, adb: Adb, serial: str) -> None:
        self.adb = adb
        self.serial = serial
        self.scid = f"{secrets.randbits(31):08x}"
        self.port: int | None = None
        self.proc: subprocess.Popen | None = None
        self.output: collections.deque[str] = collections.deque(maxlen=20)  # server log tail
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.device_name = ""

    @staticmethod
    def available() -> bool:
        return VENDOR_SERVER.exists()

    async def start(self, connect_timeout_s: float = 8.0) -> None:
        if not self.available():
            raise ScrcpyError("Không tìm thấy vendor/scrcpy/scrcpy-server")
        if self.adb.path is None:
            raise ScrcpyError("Không tìm thấy adb")
        s = self.serial
        await self.adb.run("-s", s, "push", str(VENDOR_SERVER), DEVICE_JAR)
        out = await self.adb.run("-s", s, "forward", "tcp:0", f"localabstract:scrcpy_{self.scid}")
        self.port = int(out.decode().strip())
        self.proc = await asyncio.to_thread(
            subprocess.Popen, [str(self.adb.path), "-s", s, "shell", *server_args(self.scid)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW)
        threading.Thread(target=self._drain, args=(self.proc,), daemon=True).start()
        await self._connect(connect_timeout_s)
        assert self.reader is not None
        self.device_name = await read_handshake(self.reader)

    def _drain(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self.output.append(line.decode("utf-8", "replace").rstrip())

    async def _connect(self, timeout_s: float) -> None:
        """The forward accepts before the server listens: the dummy byte proves the server is there."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            if self.proc is not None and self.proc.poll() is not None:
                raise ScrcpyError(f"scrcpy-server đã thoát: {self.tail()}")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                try:
                    await asyncio.wait_for(reader.readexactly(1), 2.0)
                except BaseException:
                    writer.close()
                    raise
                self.reader, self.writer = reader, writer
                return
            except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
                if loop.time() > deadline:
                    raise ScrcpyError(f"Không kết nối được scrcpy-server: {self.tail()}") from None
                await asyncio.sleep(0.1)

    def tail(self) -> str:
        return " | ".join(self.output)[-300:] or "không có log"

    def packets(self) -> AsyncIterator[Session | Packet]:
        assert self.reader is not None
        return merge_config(read_stream(self.reader))

    async def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            self.writer = None
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.kill()  # the server also exits on its own once its socket closes
            self.proc = None
        if self.port is not None:
            try:
                await self.adb.run("-s", self.serial, "forward", "--remove", f"tcp:{self.port}")
            except AdbError:
                pass
            self.port = None

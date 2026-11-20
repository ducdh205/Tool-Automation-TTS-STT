import asyncio
import socket
import sys
import time

import numpy as np
import pytest
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.server import AsyncEventHandler, AsyncTcpServer

from tts_stt_tool.stt.server_manager import WyomingServerManager
from tts_stt_tool.stt.wyoming_client import SttError, WyomingStt


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeHandler(AsyncEventHandler):
    def __init__(self, *args, mode: str, received: dict, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.received = received

    async def handle_event(self, event: Event) -> bool:
        if AudioStart.is_type(event.type):
            s = AudioStart.from_event(event)
            self.received["rate"] = s.rate
            self.received["width"] = s.width
            self.received["channels"] = s.channels
            self.received["bytes"] = 0
        elif AudioChunk.is_type(event.type):
            self.received["bytes"] += len(AudioChunk.from_event(event).audio)
        elif AudioStop.is_type(event.type):
            if self.mode == "ok":
                await self.write_event(Transcript(text="bật điều hòa").event())
                return False
            await asyncio.sleep(30)  # "silent": never answers
        return True


@pytest.fixture
async def fake_server(request):
    mode = getattr(request, "param", "ok")
    port = free_port()
    received: dict = {}
    server = AsyncTcpServer("127.0.0.1", port)
    task = asyncio.create_task(
        server.run(lambda *a, **k: FakeHandler(*a, mode=mode, received=received, **k))
    )
    await asyncio.sleep(0.2)
    yield port, received
    task.cancel()
    await server.stop()


def one_second_48k() -> np.ndarray:
    return (np.sin(np.linspace(0, 2000, 48000)) * 0.3).astype("float32")


async def test_transcribe_returns_text_and_sends_16k(fake_server):
    port, received = fake_server
    stt = WyomingStt("127.0.0.1", port, timeout_s=5)
    text = await stt.transcribe(one_second_48k(), 48000)
    assert text == "bật điều hòa"
    assert (received["rate"], received["width"], received["channels"]) == (16000, 2, 1)
    assert abs(received["bytes"] - 32000) < 200  # 1 s of 16 kHz int16


@pytest.mark.parametrize("fake_server", ["silent"], indirect=True)
async def test_timeout_raises(fake_server):
    port, _ = fake_server
    stt = WyomingStt("127.0.0.1", port, timeout_s=1)
    t = time.monotonic()
    with pytest.raises(SttError, match="Hết thời gian"):
        await stt.transcribe(one_second_48k(), 48000)
    assert time.monotonic() - t < 2.5


async def test_closed_port_raises():
    stt = WyomingStt("127.0.0.1", free_port(), timeout_s=2)
    with pytest.raises(SttError, match="Không kết nối được"):
        await stt.transcribe(one_second_48k(), 48000)


LISTENER = (
    "import socket,sys,time\n"
    "s=socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen()\n"
    "time.sleep(60)\n"
)


async def test_server_manager_starts_and_stops_process():
    port = free_port()
    mgr = WyomingServerManager([sys.executable, "-c", LISTENER, str(port)], "127.0.0.1", port,
                               start_timeout_s=20)
    assert not await mgr.is_up()
    await mgr.ensure_running()
    assert await mgr.is_up()
    mgr.stop()
    for _ in range(50):
        if not await mgr.is_up():
            break
        await asyncio.sleep(0.1)
    assert not await mgr.is_up()


async def test_server_manager_reuses_running_server(fake_server):
    port, _ = fake_server
    mgr = WyomingServerManager(["does-not-exist.exe"], "127.0.0.1", port)
    await mgr.ensure_running()  # port already open -> no spawn, no error
    assert mgr.process is None


async def test_server_manager_reports_dead_process():
    port = free_port()
    mgr = WyomingServerManager([sys.executable, "-c", "raise SystemExit(3)"], "127.0.0.1", port,
                               start_timeout_s=10)
    with pytest.raises(SttError, match="thoát"):
        await mgr.ensure_running()


@pytest.mark.live
async def test_live_default_launch_transcribes_vieneu_wav(tmp_path):
    """Manual: uv run python -m pytest -m live (needs vendor/wyoming-vietnamese + models in data/)."""
    import soundfile as sf

    from tts_stt_tool.stt.server_manager import REPO_ROOT, default_wyoming_launch

    port = free_port()
    cmd, cwd, env = default_wyoming_launch(REPO_ROOT / "data", port)
    mgr = WyomingServerManager(cmd, "127.0.0.1", port, cwd=cwd, env=env,
                               log_path=tmp_path / "wy.log", start_timeout_s=180)
    try:
        await mgr.ensure_running()
        audio, sr = sf.read(REPO_ROOT / "data" / "spike" / "t1.wav", dtype="float32")
        text = await WyomingStt("127.0.0.1", port, timeout_s=30).transcribe(audio, sr)
        assert text == "chỉnh nhiệt độ ghế lái lên hai mươi tư độ"
    finally:
        mgr.stop()

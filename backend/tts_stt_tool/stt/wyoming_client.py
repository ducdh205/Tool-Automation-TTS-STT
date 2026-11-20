"""Reference STT: a client for a Wyoming ASR server (wyoming-vietnamese)."""

from __future__ import annotations

import asyncio
from typing import Protocol

import numpy as np
import soxr
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient

RATE = 16000
WIDTH = 2
CHANNELS = 1
CHUNK_BYTES = 2048


class SttError(Exception):
    """Reference STT failed (connection, timeout, protocol)."""


class SttEngine(Protocol):
    async def transcribe(self, audio: np.ndarray, sr: int) -> str: ...


def to_pcm16(audio: np.ndarray, sr: int) -> bytes:
    a = np.asarray(audio, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != RATE:
        a = soxr.resample(a, sr, RATE)
    return (np.clip(a, -1.0, 1.0) * 32767).astype("<i2").tobytes()


class WyomingStt:
    def __init__(self, host: str, port: int, timeout_s: float = 30.0, language: str = "vi") -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.language = language

    async def _connect(self) -> AsyncTcpClient:
        client = AsyncTcpClient(self.host, self.port)
        try:
            # Windows takes ~2 s to refuse a closed localhost port: own timeout, own message.
            await asyncio.wait_for(client.connect(), timeout=min(5.0, self.timeout_s))
        except (OSError, TimeoutError) as e:
            raise SttError(f"Không kết nối được wyoming tại {self.host}:{self.port}") from e
        return client

    async def _run(self, client: AsyncTcpClient, pcm: bytes) -> str:
        try:
            await client.write_event(Transcribe(language=self.language).event())
            await client.write_event(AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event())
            for i in range(0, len(pcm), CHUNK_BYTES):
                chunk = AudioChunk(rate=RATE, width=WIDTH, channels=CHANNELS, audio=pcm[i : i + CHUNK_BYTES])
                await client.write_event(chunk.event())
            await client.write_event(AudioStop().event())
            while True:
                event = await client.read_event()
                if event is None:
                    raise SttError("Wyoming đóng kết nối trước khi trả kết quả")
                if Transcript.is_type(event.type):
                    return Transcript.from_event(event).text or ""
        finally:
            await client.disconnect()

    async def transcribe(self, audio: np.ndarray, sr: int) -> str:
        pcm = to_pcm16(audio, sr)
        client = await self._connect()
        try:
            return await asyncio.wait_for(self._run(client, pcm), timeout=self.timeout_s)
        except TimeoutError as e:
            raise SttError(f"Hết thời gian chờ STT ({self.timeout_s:g}s)") from e
        except OSError as e:
            raise SttError(f"Lỗi kết nối wyoming: {e}") from e

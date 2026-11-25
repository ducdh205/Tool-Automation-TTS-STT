"""On-disk WAV cache keyed by (text, voice, attempt, engine version, speed)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

from tts_stt_tool.tts.base import TtsEngine
from tts_stt_tool.tts.speed import change_speed, is_normal


def cache_key(text_tts: str, voice: str, attempt: int, engine_version: str, speed: float = 1.0) -> str:
    # Light normalization only: "24" and "hai mươi tư" must produce different audio.
    text = " ".join(unicodedata.normalize("NFC", text_tts).split())
    parts = [text, voice, str(attempt), engine_version]
    if not is_normal(speed):  # normal speed keeps the keys of audio cached before speeds existed
        parts.append(f"speed={speed:g}")
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class AudioCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    async def get_or_synthesize(self, tts: TtsEngine, text: str, voice: str, attempt: int,
                                speed: float = 1.0) -> Path:
        key = cache_key(text, voice, attempt, tts.version, speed)
        if self.exists(key):
            return self.path_for(key)
        audio, sr = await asyncio.to_thread(tts.synthesize, text, voice, attempt)
        if not is_normal(speed):
            audio = await asyncio.to_thread(change_speed, audio, speed)
        return await asyncio.to_thread(self.write, key, audio, sr)

    def write(self, key: str, audio: np.ndarray, sr: int) -> Path:
        final = self.path_for(key)
        tmp = final.with_suffix(".wav.tmp")
        sf.write(tmp, np.asarray(audio, dtype="float32"), sr, subtype="PCM_16", format="WAV")
        os.replace(tmp, final)
        return final

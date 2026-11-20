"""On-disk WAV cache keyed by (text, voice, attempt, engine version)."""

from __future__ import annotations

import hashlib
import os
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf


def cache_key(text_tts: str, voice: str, attempt: int, engine_version: str) -> str:
    # Light normalization only: "24" and "hai mươi tư" must produce different audio.
    text = " ".join(unicodedata.normalize("NFC", text_tts).split())
    raw = "\x1f".join([text, voice, str(attempt), engine_version])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class AudioCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def write(self, key: str, audio: np.ndarray, sr: int) -> Path:
        final = self.path_for(key)
        tmp = final.with_suffix(".wav.tmp")
        sf.write(tmp, np.asarray(audio, dtype="float32"), sr, subtype="PCM_16", format="WAV")
        os.replace(tmp, final)
        return final

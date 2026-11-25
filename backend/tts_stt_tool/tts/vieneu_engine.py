"""VieNeu-TTS v3 Turbo engine (CPU via ONNX, GPU when torch+CUDA is installed)."""

from __future__ import annotations

import random
import threading
from typing import Any

import numpy as np

from tts_stt_tool.tts.base import VoiceInfo

SAMPLE_RATE = 48000


class VieneuEngine:
    version = "vieneu-v3turbo"

    def __init__(self, mode: str = "v3turbo", device: str = "cpu") -> None:
        self._mode = mode
        self._device = device
        self._tts: Any = None
        self._lock = threading.Lock()
        self.active_device: str | None = None  # what the loaded model runs on (None = not loaded yet)
        self.load_error: str | None = None  # why CUDA could not be used, when it fell back to CPU

    def set_device(self, device: str) -> None:
        """Switch CPU/CUDA: drop the loaded model so the next call reloads it."""
        with self._lock:
            self._device = device
            self._tts = None
            self.active_device = None
            self.load_error = None

    def _model(self) -> Any:
        with self._lock:
            if self._tts is None:
                from vieneu import Vieneu  # heavy import, load lazily

                device = self._device
                if device == "cuda":
                    try:
                        self._tts = Vieneu(mode=self._mode, device="cuda")
                    except Exception as e:  # torch/driver missing: keep working on CPU
                        self.load_error = str(e)
                        device = "cpu"
                if self._tts is None:
                    self._tts = Vieneu(mode=self._mode, device=device)
                self.active_device = device
            return self._tts

    @staticmethod
    def temperature_for(attempt: int) -> float:
        """Default 0.8; each retry lowers it by 0.1 down to 0.4 (spike notes)."""
        return max(0.4, round(0.8 - 0.1 * attempt, 2))

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id=vid, label=label) for label, vid in self._model().list_preset_voices()]

    def synthesize(self, text: str, voice: str, attempt: int) -> tuple[np.ndarray, int]:
        tts = self._model()
        with self._lock:  # the model is not thread-safe
            random.seed(attempt)
            np.random.seed(attempt)
            audio = tts.infer(text, voice=voice, temperature=self.temperature_for(attempt))
        audio = np.asarray(audio, dtype="float32").reshape(-1)
        return audio, int(getattr(tts, "sample_rate", SAMPLE_RATE))

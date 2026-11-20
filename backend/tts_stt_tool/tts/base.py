"""TTS engine interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class VoiceInfo:
    id: str
    label: str


class TtsEngine(Protocol):
    version: str

    def voices(self) -> list[VoiceInfo]: ...

    def synthesize(self, text: str, voice: str, attempt: int) -> tuple[np.ndarray, int]:
        """Return (mono float32 audio, sample rate). ``attempt > 0`` must vary the output."""
        ...

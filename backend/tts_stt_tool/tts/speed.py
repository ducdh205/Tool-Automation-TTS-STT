"""Voice speed: VieNeu v3 Turbo has no speed knob, so the synthesized audio is time-stretched.

The phase vocoder keeps the pitch (no "chipmunk" voice); past ~0.7x-1.3x it starts to sound
smeared, hence the narrow range.
"""

from __future__ import annotations

import numpy as np

MIN_SPEED = 0.7
MAX_SPEED = 1.3


def is_normal(speed: float) -> bool:
    return abs(speed - 1.0) < 1e-6


def change_speed(audio: np.ndarray, speed: float) -> np.ndarray:
    """Return ``audio`` played ``speed`` times faster (``1.0`` = unchanged), same pitch and sample rate."""
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"Tốc độ giọng phải trong khoảng {MIN_SPEED}–{MAX_SPEED}")
    audio = np.asarray(audio, dtype="float32").reshape(-1)
    if is_normal(speed) or audio.size == 0:
        return audio
    import librosa  # heavy import, only when the speed is changed

    return librosa.effects.time_stretch(audio, rate=float(speed)).astype("float32")

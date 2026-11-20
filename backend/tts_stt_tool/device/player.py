"""Play a WAV on the PC's default speakers (the phone listens with its real microphone)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AudioPlayer(Protocol):
    def play(self, path: Path) -> None:
        """Block until playback ends."""
        ...


class WinSoundPlayer:
    def play(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        import winsound

        # NODEFAULT: an unplayable file must fail, not play the system beep and "succeed"
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)

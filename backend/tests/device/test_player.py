import time

import numpy as np
import pytest
import soundfile as sf

from tts_stt_tool.device.player import WinSoundPlayer


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        WinSoundPlayer().play(tmp_path / "nope.wav")


@pytest.mark.live
def test_plays_blocking(tmp_path):
    p = tmp_path / "a.wav"
    sf.write(p, np.zeros(4800, dtype="float32"), 16000, subtype="PCM_16")
    t = time.monotonic()
    WinSoundPlayer().play(p)
    assert time.monotonic() - t >= 0.25

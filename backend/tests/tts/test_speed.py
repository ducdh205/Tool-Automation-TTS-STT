import numpy as np
import pytest

from tts_stt_tool.tts.speed import change_speed


def test_normal_speed_is_unchanged():
    a = np.ones(100, dtype="float32")
    assert np.array_equal(change_speed(a, 1.0), a)


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        change_speed(np.zeros(10, dtype="float32"), 2.0)
    with pytest.raises(ValueError):
        change_speed(np.zeros(10, dtype="float32"), 0.5)


def test_empty_audio():
    assert change_speed(np.zeros(0, dtype="float32"), 1.2).size == 0

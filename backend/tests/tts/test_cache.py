import numpy as np
import soundfile as sf

from tts_stt_tool.tts.cache import AudioCache, cache_key


def test_cache_key_changes_with_inputs():
    base = cache_key("bật đèn", "Ngọc Huyền", 0, "v1")
    assert cache_key("tắt đèn", "Ngọc Huyền", 0, "v1") != base
    assert cache_key("bật đèn", "Mai Anh", 0, "v1") != base
    assert cache_key("bật đèn", "Ngọc Huyền", 1, "v1") != base
    assert cache_key("bật đèn", "Ngọc Huyền", 0, "v2") != base
    assert len(base) == 16


def test_cache_key_ignores_whitespace_only():
    assert cache_key("  bật   đèn ", "v", 0, "e") == cache_key("bật đèn", "v", 0, "e")


def test_cache_key_keeps_digits_distinct_from_words():
    assert cache_key("24 độ", "v", 0, "e") != cache_key("hai mươi tư độ", "v", 0, "e")


def test_write_and_read_back(tmp_path):
    cache = AudioCache(tmp_path)
    audio = (np.sin(np.linspace(0, 100, 4800)) * 0.5).astype("float32")
    path = cache.write("abc", audio, 48000)
    assert cache.exists("abc")
    assert path == cache.path_for("abc")
    data, sr = sf.read(path)
    assert sr == 48000
    assert len(data) == 4800


def test_leftover_tmp_is_not_a_cache_hit(tmp_path):
    cache = AudioCache(tmp_path)
    cache.path_for("k").with_suffix(".wav.tmp").write_bytes(b"partial")
    assert not cache.exists("k")


def test_cache_key_speed():
    base = cache_key("bật đèn", "v", 0, "e")
    # Normal speed keeps the keys of audio cached before the speed setting existed.
    assert cache_key("bật đèn", "v", 0, "e", 1.0) == base
    assert cache_key("bật đèn", "v", 0, "e", 1.2) != base
    assert cache_key("bật đèn", "v", 0, "e", 1.2) != cache_key("bật đèn", "v", 0, "e", 0.8)


class _Tone:
    version = "tone"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice, attempt):
        self.calls += 1
        return (np.sin(np.linspace(0, 2000, 48000)) * 0.5).astype("float32"), 48000


async def test_get_or_synthesize_applies_speed(tmp_path):
    cache = AudioCache(tmp_path)
    tts = _Tone()
    normal = await cache.get_or_synthesize(tts, "bật đèn", "v", 0)
    fast = await cache.get_or_synthesize(tts, "bật đèn", "v", 0, speed=1.25)
    slow = await cache.get_or_synthesize(tts, "bật đèn", "v", 0, speed=0.8)
    assert len({normal, fast, slow}) == 3
    n, f, s = (len(sf.read(p)[0]) for p in (normal, fast, slow))
    assert n == 48000
    assert abs(f - n / 1.25) < 1000 and abs(s - n / 0.8) < 1000
    assert sf.read(fast)[1] == 48000
    await cache.get_or_synthesize(tts, "bật đèn", "v", 0, speed=1.25)
    assert tts.calls == 3  # second fast request is a cache hit

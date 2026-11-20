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

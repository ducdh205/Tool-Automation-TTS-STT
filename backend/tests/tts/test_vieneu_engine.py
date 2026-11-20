import pytest

from tts_stt_tool.tts.vieneu_engine import VieneuEngine


@pytest.mark.gpu
def test_vieneu_synthesizes_and_lists_voices():
    eng = VieneuEngine()
    voices = eng.voices()
    assert voices
    assert any(v.id == "Ngọc Huyền" for v in voices)
    audio, sr = eng.synthesize("Bật đồng bộ nhiệt độ", "Ngọc Huyền", 0)
    assert sr == 48000
    assert len(audio) / sr > 0.5
    audio2, _ = eng.synthesize("Bật đồng bộ nhiệt độ", "Ngọc Huyền", 1)
    assert len(audio2) > 0


def test_temperature_schedule():
    assert VieneuEngine.temperature_for(0) == 0.8
    assert VieneuEngine.temperature_for(1) == pytest.approx(0.7)
    assert VieneuEngine.temperature_for(10) == 0.4

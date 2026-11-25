import sys
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


class _FakeVieneuModule:
    def __init__(self, fail_cuda: bool = False):
        self.calls: list[dict] = []
        self.fail_cuda = fail_cuda

    def Vieneu(self, mode, device):  # noqa: N802 - mirrors vieneu.Vieneu
        self.calls.append({"mode": mode, "device": device})
        if device == "cuda" and self.fail_cuda:
            raise RuntimeError("no cuda")
        return object()


@pytest.fixture
def fake_vieneu(monkeypatch):
    def install(fail_cuda: bool = False) -> _FakeVieneuModule:
        mod = _FakeVieneuModule(fail_cuda)
        monkeypatch.setitem(sys.modules, "vieneu", mod)
        return mod

    return install


def test_device_passed_to_model(fake_vieneu):
    mod = fake_vieneu()
    eng = VieneuEngine(device="cuda")
    assert eng.active_device is None
    eng._model()
    assert mod.calls == [{"mode": "v3turbo", "device": "cuda"}]
    assert eng.active_device == "cuda"


def test_set_device_reloads(fake_vieneu):
    mod = fake_vieneu()
    eng = VieneuEngine()
    eng._model()
    eng.set_device("cuda")
    eng._model()
    assert [c["device"] for c in mod.calls] == ["cpu", "cuda"]
    assert eng.active_device == "cuda"


def test_cuda_load_failure_falls_back_to_cpu(fake_vieneu):
    mod = fake_vieneu(fail_cuda=True)
    eng = VieneuEngine(device="cuda")
    assert eng._model() is not None
    assert [c["device"] for c in mod.calls] == ["cuda", "cpu"]
    assert eng.active_device == "cpu"
    assert "no cuda" in eng.load_error

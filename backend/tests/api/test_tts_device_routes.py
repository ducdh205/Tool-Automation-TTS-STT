import json
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.tests.api.test_routes import EchoStt, create_set, wait_job_end
from backend.tests.pipeline.test_block1 import FakeTts
from tts_stt_tool.api.app import create_app
from tts_stt_tool.config import Settings
from tts_stt_tool.tts.gpu import GpuSetup

PY = sys.executable
NVIDIA = [PY, "-c", "print('NVIDIA GeForce RTX 3060')"]
NO_NVIDIA = ["khong-co-lenh-nay"]


def exits(code):
    return [PY, "-c", f"import sys; sys.exit({code})"]


def flag_check(path):
    return [PY, "-c", f"import os, sys; sys.exit(0 if os.path.exists({str(path)!r}) else 1)"]


class DeviceTts(FakeTts):
    def __init__(self):
        super().__init__()
        self.devices: list[str] = []
        self.gate = threading.Event()
        self.gate.set()

    def set_device(self, device):
        self.devices.append(device)

    def synthesize(self, text, voice, attempt):
        self.gate.wait(5)
        return super().synthesize(text, voice, attempt)


def make_client(tmp_path, gpu):
    tts = DeviceTts()
    app = create_app(Settings(data_dir=tmp_path), tts=tts, stt=EchoStt(tts), manage_wyoming=False, gpu=gpu)
    return TestClient(app), tts


@pytest.fixture
def setup(tmp_path):
    clients = []

    def make(gpu):
        c, tts = make_client(tmp_path, gpu)
        clients.append(c.__enter__())
        return c, tts

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def saved_device(tmp_path):
    p = tmp_path / "settings.json"
    return json.loads(p.read_text(encoding="utf-8"))["tts_device"] if p.exists() else "cpu"


def test_get_device_reports_probe(setup):
    c, _ = setup(GpuSetup(nvidia_cmd=NO_NVIDIA, torch_cmd=exits(1), install_cmd=exits(0)))
    d = c.get("/api/tts/device").json()
    assert d["device"] == "cpu"
    assert d["nvidia"] is False
    assert d["gpu_name"] is None
    assert d["torch_cuda"] is False
    assert d["uv"] is True
    assert d["install"] == {"state": "idle", "log_tail": [], "error": None}
    assert "active" in d and "load_error" in d


def test_put_cuda_without_nvidia_409(setup):
    c, _ = setup(GpuSetup(nvidia_cmd=NO_NVIDIA, torch_cmd=exits(0), install_cmd=exits(0)))
    r = c.put("/api/tts/device", json={"device": "cuda"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Máy không có GPU NVIDIA"


def test_put_cuda_without_torch_409(setup, tmp_path):
    c, tts = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=exits(1), install_cmd=exits(0)))
    r = c.put("/api/tts/device", json={"device": "cuda"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Chưa có PyTorch CUDA"
    assert tts.devices == []
    assert saved_device(tmp_path) == "cpu"


def test_put_cuda_reprobes(setup, tmp_path):
    flag = tmp_path / "cuda-ready"
    c, _ = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=flag_check(flag), install_cmd=exits(0)))
    assert c.get("/api/tts/device").json()["torch_cuda"] is False
    flag.touch()  # installed by hand meanwhile
    r = c.put("/api/tts/device", json={"device": "cuda"})
    assert r.status_code == 200, r.text
    assert r.json()["device"] == "cuda"


def test_put_cuda_ok_persists(setup, tmp_path):
    c, tts = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=exits(0), install_cmd=exits(0)))
    r = c.put("/api/tts/device", json={"device": "cuda"})
    assert r.status_code == 200, r.text
    assert saved_device(tmp_path) == "cuda"
    assert tts.devices == ["cuda"]
    r = c.put("/api/tts/device", json={"device": "cpu"})
    assert r.status_code == 200
    assert saved_device(tmp_path) == "cpu"
    assert tts.devices == ["cuda", "cpu"]


def test_put_bad_device_422(setup):
    c, _ = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=exits(0), install_cmd=exits(0)))
    assert c.put("/api/tts/device", json={"device": "tpu"}).status_code == 422


def test_put_device_while_job_running_409(setup, tmp_path):
    c, tts = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=exits(0), install_cmd=exits(0)))
    set_id = create_set(c, tmp_path)
    tts.gate.clear()
    assert c.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
    try:
        r = c.put("/api/tts/device", json={"device": "cuda"})
        assert r.status_code == 409
        assert r.json()["detail"] == "Đang có tác vụ chạy, đợi xong rồi đổi"
        assert saved_device(tmp_path) == "cpu"
    finally:
        tts.gate.set()
        wait_job_end(c)


def test_install_cuda_then_device_is_cuda(setup, tmp_path):
    flag = tmp_path / "cuda-ready"
    install = [PY, "-c", f"import pathlib; print('ok'); pathlib.Path({str(flag)!r}).touch()"]
    c, tts = setup(GpuSetup(nvidia_cmd=NVIDIA, torch_cmd=flag_check(flag), install_cmd=install))
    r = c.post("/api/tts/install-cuda")
    assert r.status_code == 200, r.text
    assert r.json()["install"]["state"] in ("running", "done")
    for _ in range(100):
        d = c.get("/api/tts/device").json()
        if d["install"]["state"] != "running":
            break
        time.sleep(0.05)
    assert d["install"]["state"] == "done", d
    assert d["device"] == "cuda"
    assert d["torch_cuda"] is True
    assert tts.devices == ["cuda"]
    assert saved_device(tmp_path) == "cuda"


def test_install_cuda_without_nvidia_400(setup):
    c, _ = setup(GpuSetup(nvidia_cmd=NO_NVIDIA, torch_cmd=exits(1), install_cmd=exits(0)))
    r = c.post("/api/tts/install-cuda")
    assert r.status_code == 400
    assert r.json()["detail"] == "Máy không có GPU NVIDIA"

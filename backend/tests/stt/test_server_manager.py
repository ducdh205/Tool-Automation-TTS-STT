import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tts_stt_tool.stt import server_manager
from tts_stt_tool.stt.server_manager import default_wyoming_launch


def test_launch_uses_data_dir_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("TTS_STT_WYOMING_DIR", raising=False)
    _, _, env = default_wyoming_launch(tmp_path, 10300)
    assert env["DOWNLOAD_DIR"] == str((tmp_path / "wyoming" / "models").resolve())
    assert env["CACHE_DIR"] == str((tmp_path / "wyoming" / "cache").resolve())
    assert env["WYOMING_PORT"] == "10300"


def test_launch_model_dir_from_env(monkeypatch, tmp_path):
    """Installed copies ship the wyoming models next to the app, not in the data dir."""
    monkeypatch.setenv("TTS_STT_WYOMING_DIR", str(tmp_path / "bundled"))
    _, _, env = default_wyoming_launch(tmp_path / "data", 10300)
    assert env["DOWNLOAD_DIR"] == str((tmp_path / "bundled" / "models").resolve())


def test_launch_uses_gipformer_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("STT_ENGINE", raising=False)
    _, _, env = default_wyoming_launch(tmp_path, 10300)
    assert env["STT_ENGINE"] == "gipformer"


def test_launch_stt_engine_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STT_ENGINE", "zipformer")
    _, _, env = default_wyoming_launch(tmp_path, 10300)
    assert env["STT_ENGINE"] == "zipformer"


def test_bundled_runtime_preferred(monkeypatch, tmp_path):
    bundled = tmp_path / "runtime" / "py314" / "python.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()
    monkeypatch.setattr(server_manager, "REPO_ROOT", tmp_path)
    assert server_manager.wyoming_python() == bundled


def test_venv_python_without_bundled_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(server_manager, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server_manager, "VENDOR_DIR", tmp_path / "vendor" / "wy")
    assert server_manager.wyoming_python().parent.parent == tmp_path / "vendor" / "wy" / ".venv"


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@pytest.mark.skipif(os.name != "nt", reason="job objects are Windows-only")
def test_child_dies_when_parent_is_killed(tmp_path):
    """Closing the console kills the tool abruptly; wyoming must not outlive it."""
    backend = Path(server_manager.__file__).resolve().parents[2]
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"sys.path.insert(0, {str(backend)!r})\n"
        "from tts_stt_tool.stt.winjob import kill_with_this_process\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid, kill_with_this_process(child), flush=True)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(parent)], stdout=subprocess.PIPE, text=True)
    pid_s, assigned = proc.stdout.readline().split()
    child_pid = int(pid_s)
    try:
        assert assigned == "True"
        assert _alive(child_pid)
        proc.kill()  # like closing the console window: no cleanup runs
        proc.wait(10)
        deadline = time.monotonic() + 10
        while _alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _alive(child_pid)
    finally:
        subprocess.run(["taskkill", "/F", "/PID", str(child_pid)], capture_output=True)

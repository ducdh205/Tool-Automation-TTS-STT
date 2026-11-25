"""Build step: start the staged app exactly like the shortcut does, offline, and check it works.

    <stage>/runtime/py312/python.exe smoke_test.py <stage>

Starts launch.py with a fresh data dir, then checks: web UI served, wyoming up,
VieNeu voices load, a voice preview is synthesized, and wyoming transcribes it.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 8799
WYOMING_PORT = 10398  # not 10300: a running dev copy may hold it


def get(path: str, timeout: float = 600) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return r.read()


def wait_health(proc: subprocess.Popen, timeout_s: float = 600) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"Tool đã thoát (mã {proc.returncode})")
        try:
            last = json.loads(get("/api/health", timeout=5))
            if last.get("wyoming") or last.get("wyoming_error"):
                return last
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f"Hết thời gian chờ tool khởi động: {last}")


async def transcribe(wav: bytes) -> str:
    import soundfile as sf

    from tts_stt_tool.stt.wyoming_client import WyomingStt

    audio, sr = sf.read(io.BytesIO(wav), dtype="float32")
    return await WyomingStt("127.0.0.1", WYOMING_PORT, timeout_s=60).transcribe(audio, sr)


def port_busy(port: int) -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    stage = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(stage / "backend"))
    python = stage / "runtime" / "py312" / "python.exe"
    for port in (PORT, WYOMING_PORT):  # something else would answer instead of the staged app
        if port_busy(port):
            raise SystemExit(f"Cổng {port} đang bận — tắt tool/wyoming đang chạy rồi build lại")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as data:
        (Path(data) / "settings.json").write_text(json.dumps({"wyoming_port": WYOMING_PORT}), encoding="utf-8")
        env = {**os.environ, "TTS_STT_DATA_DIR": data, "PYTHONIOENCODING": "utf-8"}
        env.pop("VIRTUAL_ENV", None)
        log = Path(data) / "smoke.log"
        with log.open("wb") as out:
            proc = subprocess.Popen([str(python), str(stage / "launch.py"), "--no-browser", "--port", str(PORT)],
                                    env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            health = wait_health(proc)
            assert health["wyoming"], f"wyoming lỗi: {health.get('wyoming_error')}"
            assert b"<html" in get("/").lower(), "giao diện không được phục vụ"
            voices = json.loads(get("/api/voices"))
            assert voices, "không có giọng VieNeu"
            voice = next((v for v in voices if v["label"] == "Ngọc Huyền"), voices[0])
            wav = get("/api/voices/preview?voice_id=" + urllib.parse.quote(voice["id"]))
            text = asyncio.run(transcribe(wav))
            print(f"OK: {len(voices)} giọng; '{voice['label']}' → wyoming nghe: {text!r}")
            assert text.strip(), "wyoming trả về rỗng"
        except BaseException:
            print(log.read_text(encoding="utf-8", errors="replace")[-6000:])
            raise
        finally:
            proc.terminate()
            proc.wait(30)
            time.sleep(2)  # the job object ends wyoming with the tool
            if port_busy(WYOMING_PORT):
                raise SystemExit("wyoming vẫn chạy sau khi tắt tool")


if __name__ == "__main__":
    main()

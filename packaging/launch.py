"""Start a portable copy of TTS-STT Tool (TTS-STT-Tool.bat runs this).

Folder layout (built by packaging/build.ps1), next to this file:

    TTS-STT-Tool.bat           double-click to start
    data/                      user data: database, audio, reports, app profiles (created on first run)
    backend/tts_stt_tool/      the tool's source
    frontend/dist/             built web UI
    vendor/platform-tools/     adb
    vendor/wyoming-vietnamese/ wyoming source (STT)
    runtime/py312/             Python 3.12 + the tool's libraries (runs this file)
    runtime/py314/             Python 3.14.8 + wyoming's libraries
    models/hf/                 VieNeu models (Hugging Face cache)
    models/wyoming/            wyoming models

The whole folder is self-contained: copy it anywhere writable (not Program Files) and it
runs offline, data included. Set TTS_STT_DATA_DIR to keep data somewhere else.
"""

from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
import traceback
import webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent
DEFAULT_DATA = APP / "data"


def configure_env() -> Path:
    data = Path(os.environ.setdefault("TTS_STT_DATA_DIR", str(DEFAULT_DATA)))
    os.environ["HF_HOME"] = str(APP / "models" / "hf")
    os.environ["HF_HUB_OFFLINE"] = "1"  # VieNeu: never call Hugging Face
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["OFFLINE"] = "1"  # wyoming-vietnamese: load models from disk only
    os.environ["TTS_STT_WYOMING_DIR"] = str(APP / "models" / "wyoming")
    sys.path.insert(0, str(APP / "backend"))
    return data


def configured_port(data: Path) -> int:
    try:
        port = json.loads((data / "settings.json").read_text(encoding="utf-8")).get("port", 8765)
        return int(port)
    except (OSError, ValueError, TypeError, AttributeError):
        return 8765


def already_running(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetConsoleTitleW("TTS-STT Tool — đóng cửa sổ này để tắt tool")
    data = configure_env()
    args = sys.argv[1:]
    if not args:
        port = configured_port(data)
        if already_running(port):
            print(f"Tool đang chạy — mở http://127.0.0.1:{port}")
            webbrowser.open(f"http://127.0.0.1:{port}")
            return
    from tts_stt_tool.cli import main as tool_main

    tool_main(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        sys.exit(1)  # TTS-STT-Tool.bat pauses so the error stays readable

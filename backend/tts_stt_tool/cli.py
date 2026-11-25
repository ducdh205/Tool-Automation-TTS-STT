"""Entry point: ``uv run tts-stt-tool`` starts the server and opens the browser."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import webbrowser
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tts-stt-tool", description="TTS → STT automation test tool")
    p.add_argument("--data-dir", type=Path, default=Path(os.environ.get("TTS_STT_DATA_DIR") or "data"),
                   help="thư mục dữ liệu (mặc định ./data, hoặc biến TTS_STT_DATA_DIR)")
    p.add_argument("--port", type=int, default=None, help="cổng web (mặc định theo Cài đặt, 8765)")
    p.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    return p.parse_args(argv)


def utf8_console(*streams: object) -> None:
    """Windows consoles/redirects default to cp1252: switch to UTF-8 so Vietnamese logs print."""
    import sys

    for s in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(s, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    from tts_stt_tool.api.app import create_app
    from tts_stt_tool.config import load_settings

    utf8_console()
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings(args.data_dir.resolve())
    if args.port:
        settings.port = args.port
    app = create_app(settings)
    url = f"http://127.0.0.1:{settings.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"TTS-STT tool: {url}  (Ctrl+C để dừng)")
    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

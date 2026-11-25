"""Build step: make sure every model the installed tool needs is inside <stage>/models.

Run with the staged Python 3.12 (packaging/build.ps1 does this):

    <stage>/runtime/py312/python.exe prefetch_models.py <stage>

Network is allowed here; files already present (copied from the build machine's caches)
are reused. The smoke test afterwards proves the result works offline.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


def prefetch_vieneu(stage: Path) -> None:
    os.environ["HF_HOME"] = str(stage / "models" / "hf")
    os.environ.pop("HF_HUB_OFFLINE", None)
    from vieneu import Vieneu

    tts = Vieneu(mode="v3turbo")  # same mode as tts_stt_tool.tts.vieneu_engine
    voices = tts.list_preset_voices()
    tts.infer("xin chào", voice=voices[0][1])
    print(f"VieNeu: {len(voices)} giọng, model trong {os.environ['HF_HOME']}", flush=True)


async def prefetch_wyoming(stage: Path) -> None:
    os.environ["TTS_STT_WYOMING_DIR"] = str(stage / "models" / "wyoming")
    os.environ.pop("OFFLINE", None)
    from tts_stt_tool.stt.server_manager import WyomingServerManager, default_wyoming_launch, wyoming_python

    assert wyoming_python().is_relative_to(stage), wyoming_python()
    port = 10399
    with tempfile.TemporaryDirectory() as tmp:
        cmd, cwd, env = default_wyoming_launch(Path(tmp), port)
        log = Path(tmp) / "wyoming.log"
        mgr = WyomingServerManager(cmd, "127.0.0.1", port, cwd=cwd, env=env, log_path=log, start_timeout_s=900)
        try:
            await mgr.ensure_running()
        except Exception:
            print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            mgr.stop()
    print(f"Wyoming: model trong {os.environ['TTS_STT_WYOMING_DIR']}", flush=True)


def main() -> None:
    stage = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(stage / "backend"))
    prefetch_vieneu(stage)
    asyncio.run(prefetch_wyoming(stage))


if __name__ == "__main__":
    main()

"""Run wyoming-vietnamese on Windows.

wyoming-vietnamese only imports the Unix-only ``fcntl`` module to take an
exclusive file lock while downloading models. On Windows we run a single
server process, so a no-op lock is safe. This script is executed with the
*wyoming-vietnamese* virtualenv's Python (stdlib only, no imports from this
package):

    uv run --project vendor/wyoming-vietnamese --no-dev python <this file>
"""

from __future__ import annotations

import os
import runpy
import sys
import types

if sys.platform == "win32" and "fcntl" not in sys.modules:
    shim = types.ModuleType("fcntl")
    shim.LOCK_EX = 2  # type: ignore[attr-defined]
    shim.LOCK_UN = 8  # type: ignore[attr-defined]
    shim.flock = lambda fd, op: None  # type: ignore[attr-defined]
    sys.modules["fcntl"] = shim


def _stub_piper_phonemize_if_blocked() -> None:
    """Replace piper_phonemize when Windows Application Control blocks its DLL.

    The server always initializes and warms up its own TTS engine. This tool only
    uses the server's STT, so a stub that yields a single phoneme is enough for
    startup. The server's TTS output is meaningless with the stub, and this tool
    never calls it.
    """
    try:
        import piper_phonemize  # noqa: F401
    except ImportError:
        stub = types.ModuleType("piper_phonemize")
        stub.phonemize_espeak = lambda text, voice: [["a"]]  # type: ignore[attr-defined]
        sys.modules["piper_phonemize"] = stub
        print("[launcher] piper_phonemize blocked -> stub (wyoming TTS disabled)", flush=True)


if __name__ == "__main__":
    _stub_piper_phonemize_if_blocked()
    # sys.path[0] is this script's folder; the wyoming source lives in the cwd.
    sys.path.insert(0, os.getcwd())
    runpy.run_module("wyoming_vietnamese", run_name="__main__", alter_sys=True)

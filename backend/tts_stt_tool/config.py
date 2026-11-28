"""User settings persisted in ``<data_dir>/settings.json``."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

_LOG = logging.getLogger(__name__)
SETTINGS_FILE = "settings.json"


@dataclass
class Settings:
    data_dir: Path
    voice: str | None = "Ngọc Huyền"  # Miền Bắc, also used for rows whose region is blank or unknown
    voice_trung: str | None = "Quang Sơn"
    voice_nam: str | None = "Thùy Dung"
    voice_speed: float = 1.0  # 1.0 = as synthesized; see tts/speed.py
    wer_threshold: float = 0.0  # Block 1: STT check of the generated audio
    app_wer_threshold: float = 0.0  # Block 2: what a new app run starts with (each run keeps its own)
    reject_warn_ratio: float = 0.10
    wyoming_host: str = "127.0.0.1"
    wyoming_port: int = 10300
    stt_timeout_s: float = 30.0
    # Empty = start vendor/wyoming-vietnamese via the Windows launcher (see stt/server_manager.py).
    wyoming_cmd: list[str] = field(default_factory=list)
    port: int = 8765
    tts_device: str = "cpu"  # "cpu" | "cuda" — VieNeu backend, switched from the test bench panel
    # WebDriverAgent on the iPhone, forwarded by `go-ios forward 8100 8100` (see device/wda.py)
    wda_url: str = "http://127.0.0.1:8100"

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("data_dir")
        return d


_EDITABLE = {f.name for f in fields(Settings)} - {"data_dir"}


def load_settings(data_dir: Path) -> Settings:
    s = Settings(data_dir=data_dir)
    path = data_dir / SETTINGS_FILE
    if not path.exists():
        return s
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings.json is not an object")
    except (ValueError, OSError) as e:
        _LOG.warning("settings.json hỏng, dùng mặc định: %s", e)
        return s
    for key, value in raw.items():
        if key in _EDITABLE:
            setattr(s, key, value)
    return s


def save_settings(s: Settings) -> None:
    s.data_dir.mkdir(parents=True, exist_ok=True)
    tmp = s.data_dir / (SETTINGS_FILE + ".tmp")
    tmp.write_text(json.dumps(s.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(s.data_dir / SETTINGS_FILE)

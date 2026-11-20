"""App profiles: which on-screen labels drive the voice flow of the app under test."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

_LOG = logging.getLogger(__name__)


@dataclass
class AppProfile:
    name: str = "Vita Work (dev)"
    package: str = "com.vita.suite.dev"
    open_label: str = "Nói để tạo việc"  # home-screen mic
    stop_label: str = "Dừng nghe"  # mic button while listening
    idle_label: str = "Bấm để nói"  # mic button when not listening
    close_label: str = "Đóng"  # closes the voice sheet
    sheet_label: str = "Tạo việc"
    pre_delay_s: float = 1.0
    post_delay_s: float = 1.0
    listen_timeout_s: float = 6.0
    result_timeout_s: float = 10.0

    def to_json(self) -> dict:
        return asdict(self)


DEFAULT_PROFILE = AppProfile()
_FIELDS = {f.name for f in fields(AppProfile)}


def _slug(name: str) -> str:
    return re.sub(r"[^\w-]+", "_", name).strip("_").lower() or "profile"


def from_dict(d: dict) -> AppProfile:
    return AppProfile(**{k: v for k, v in d.items() if k in _FIELDS})


def list_profiles(directory: Path) -> list[AppProfile]:
    found: dict[str, AppProfile] = {DEFAULT_PROFILE.name: AppProfile()}
    if directory.is_dir():
        for f in sorted(directory.glob("*.json")):
            try:
                p = from_dict(json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, TypeError, OSError) as e:
                _LOG.warning("bỏ qua hồ sơ hỏng %s: %s", f.name, e)
                continue
            found[p.name] = p
    return list(found.values())


def get_profile(directory: Path, name: str) -> AppProfile:
    for p in list_profiles(directory):
        if p.name == name:
            return p
    raise KeyError(name)


def save_profile(directory: Path, p: AppProfile) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{_slug(p.name)}.json").write_text(
        json.dumps(p.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")

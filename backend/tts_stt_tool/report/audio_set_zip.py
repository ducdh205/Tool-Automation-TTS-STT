"""One audio set as a zip: ``manifest.json`` + ``audio/<name>.wav``, to keep a set and load it back later."""

from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tts_stt_tool.report.layout import safe_component
from tts_stt_tool.store.db import ItemStatus, Store

FORMAT = "tts-stt-audio-set"
VERSION = 1
MANIFEST = "manifest.json"
_WAV_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.wav$")
# Rows in these states claim to have a WAV: without one they are not what they say.
_NEEDS_AUDIO = (ItemStatus.GENERATED.value, ItemStatus.PASSED.value, ItemStatus.AUDIO_FAILED.value)


class PackError(ValueError):
    """The file to load is not a usable audio set zip; the message is shown to the user."""


def pack_name(audio_set: dict[str, Any]) -> str:
    return f"{safe_component(audio_set.get('name') or 'bo-audio')}_{date.today().isoformat()}.zip"


def build_audio_set_zip(store: Store, audio_set_id: int, out: Path) -> None:
    """Write the set to ``out``. A row whose WAV is gone from disk is exported without audio."""
    data = store.export_audio_set(audio_set_id)
    if data is None:
        raise KeyError(audio_set_id)
    wavs: dict[str, Path] = {}
    items = []
    for row in data["items"]:
        row = dict(row)
        path = row.pop("audio_path", None)
        entry = None
        if path and _WAV_NAME.match(Path(path).name) and Path(path).is_file():
            wavs.setdefault(Path(path).name, Path(path))
            entry = f"audio/{Path(path).name}"
        row["audio"] = entry
        items.append(row)
    manifest = {"format": FORMAT, "version": VERSION, "exported_at": datetime.now().isoformat(timespec="seconds"),
                "audio_set": data["audio_set"], "items": items}
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False), zipfile.ZIP_DEFLATED)
        for name, path in wavs.items():
            z.write(path, f"audio/{name}", zipfile.ZIP_STORED)  # WAV is stored: the zip stays quick to build


def _audio_entry(value: Any) -> str | None:
    """The WAV file name an item points to; PackError for anything but ``audio/<safe name>.wav``."""
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("audio/") and _WAV_NAME.match(value[6:]):
        return value[6:]
    raise PackError("File không đúng định dạng: đường dẫn audio không hợp lệ")


def _read_manifest(z: zipfile.ZipFile) -> dict[str, Any]:
    names = z.namelist()
    if MANIFEST not in names:
        raise PackError("File không phải gói bộ audio (thiếu manifest.json)")
    for name in names:  # every entry is checked before anything is written
        if name not in (MANIFEST, "audio/") and not (name.startswith("audio/") and _WAV_NAME.match(name[6:])):
            raise PackError(f"File không đúng định dạng: mục không hợp lệ trong zip ({name})")
    try:
        manifest = json.loads(z.read(MANIFEST))
    except (ValueError, zipfile.BadZipFile) as e:
        raise PackError("manifest.json không đọc được") from e
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise PackError("File không phải gói bộ audio của tool này")
    if manifest.get("version") != VERSION:
        raise PackError(f"Phiên bản gói không được hỗ trợ ({manifest.get('version')})")
    if not isinstance(manifest.get("audio_set"), dict) or not isinstance(manifest.get("items"), list) \
            or not all(isinstance(i, dict) for i in manifest["items"]):
        raise PackError("manifest.json thiếu thông tin bộ audio hoặc danh sách câu")
    return manifest


def import_audio_set_zip(store: Store, zip_path: Path, audio_dir: Path) -> dict[str, int]:
    """Create a new set from the zip; returns ``{"id", "missing_audio"}``.

    WAVs go to ``audio_dir`` (a name that already exists is kept as is: the cache is content-addressed).
    A row that needs a WAV the zip does not have goes back to "Chờ" and is counted in ``missing_audio``.
    """
    try:
        z = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as e:
        raise PackError("File không phải zip hợp lệ") from e
    with z:
        manifest = _read_manifest(z)
        names = set(z.namelist())
        rows = []
        for item in manifest["items"]:
            rows.append((dict(item), _audio_entry(item.get("audio"))))
        audio_dir.mkdir(parents=True, exist_ok=True)
        present: set[str] = set()
        for _, name in rows:
            if name and f"audio/{name}" in names and name not in present:
                present.add(name)
                target = audio_dir / name
                if not target.exists():
                    tmp = target.with_suffix(".wav.tmp")
                    tmp.write_bytes(z.read(f"audio/{name}"))
                    os.replace(tmp, target)
    items, missing = [], 0
    for item, name in rows:
        item.pop("audio", None)
        item["audio_path"] = str(audio_dir / name) if name in present else None
        if item["audio_path"] is None and (name or item.get("status") in _NEEDS_AUDIO):
            missing += 1
            item.update(status=ItemStatus.PENDING.value, attempts=0, ref_text=None, wer=None, cer=None,
                        ops_json=None, error=None)
        items.append(item)
    return {"id": store.import_audio_set(manifest["audio_set"], items), "missing_audio": missing}

"""iPhone discovery through go-ios (``vendor/go-ios/ios.exe``): device list, name, app version."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tts_stt_tool.stt.server_manager import REPO_ROOT

VENDOR_GOIOS = REPO_ROOT / "vendor" / "go-ios" / ("ios.exe" if os.name == "nt" else "ios")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GoIosError(RuntimeError):
    pass


@dataclass
class IosDeviceInfo:
    udid: str
    product_type: str | None = None  # "iPhone15,4"
    version: str | None = None  # iOS version


def find_goios() -> Path | None:
    if VENDOR_GOIOS.exists():
        return VENDOR_GOIOS
    found = shutil.which("ios")
    return Path(found) if found else None


def last_json(output: str) -> Any:
    """go-ios prints log lines (JSON objects with "level") before the answer: take the last other one."""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and "level" in data and "msg" in data:
            continue
        return data
    raise GoIosError(f"go-ios không trả về JSON: {output.strip()[:200]}")


def parse_list(output: str) -> list[IosDeviceInfo]:
    data = last_json(output)
    return [IosDeviceInfo(d["Udid"], d.get("ProductType"), d.get("ProductVersion"))
            for d in (data or {}).get("deviceList") or [] if d.get("Udid")]


def parse_app_version(output: str, bundle_id: str) -> str | None:
    """``ios apps`` -> "0.1.0 (15)" (CFBundleShortVersionString + CFBundleVersion)."""
    for app in last_json(output) or []:
        if isinstance(app, dict) and app.get("CFBundleIdentifier") == bundle_id:
            short, build = app.get("CFBundleShortVersionString"), app.get("CFBundleVersion")
            if short and build and build != short:
                return f"{short} ({build})"
            return short or build
    return None


class GoIos:
    def __init__(self, path: Path | None = None, timeout_s: float = 15.0, enabled: bool = True) -> None:
        self.path = (path or find_goios()) if enabled else None
        self.timeout_s = timeout_s
        self._names: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return self.path is not None

    def _run(self, *args: str) -> str:
        if self.path is None:
            raise GoIosError("Không tìm thấy go-ios (đặt ios.exe vào vendor/go-ios)")
        try:
            r = subprocess.run([str(self.path), *args], capture_output=True, timeout=self.timeout_s,
                               creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired as e:
            raise GoIosError(f"ios {' '.join(args)}: quá thời gian") from e
        out = r.stdout.decode("utf-8", "replace")
        if r.returncode != 0:
            msg = (r.stderr.decode("utf-8", "replace") or out).strip()
            raise GoIosError(msg[-300:] or f"ios {' '.join(args)} lỗi {r.returncode}")
        return out

    async def run(self, *args: str) -> str:
        return await asyncio.to_thread(self._run, *args)

    async def devices(self) -> list[IosDeviceInfo]:
        return parse_list(await self.run("list", "--details"))

    async def device_name(self, udid: str) -> str | None:
        """"iPhone 15" (cached: ``ios info`` takes ~0.5 s)."""
        if udid not in self._names:
            info = last_json(await self.run("info", f"--udid={udid}"))
            name = (info or {}).get("DeviceName") if isinstance(info, dict) else None
            if not name:
                return None
            self._names[udid] = name
        return self._names[udid]

    async def app_version(self, udid: str, bundle_id: str) -> str | None:
        return parse_app_version(await self.run("apps", f"--udid={udid}"), bundle_id)

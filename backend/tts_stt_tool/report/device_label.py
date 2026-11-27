"""How exports name the phone of a Block 2 run (two phones of one job must not look alike)."""

from __future__ import annotations

import re
from typing import Any

# iPhone UDIDs: 00008120-000C09D8266B601E (2018+) or 40 hex digits (older); Android serials are neither.
_IOS_UDID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}$|^[0-9A-Fa-f]{40}$")
PLATFORM_LABEL = {"android": "Android", "ios": "iPhone"}


def platform_of(run: dict[str, Any]) -> str:
    """"android" or "ios": as stored, or guessed from the serial for runs made before it was stored."""
    if run.get("platform") in PLATFORM_LABEL:
        return run["platform"]
    return "ios" if _IOS_UDID.match(run.get("serial") or "") else "android"


def platform_label(run: dict[str, Any]) -> str:
    return PLATFORM_LABEL[platform_of(run)]


def device_name(run: dict[str, Any]) -> str:
    return run.get("device_model") or run.get("serial") or ""


def device_tag(run: dict[str, Any]) -> str:
    """``Android_22120RN86G`` / ``iPhone_iPhone 15``: the phone, in file and folder names."""
    return f"{platform_label(run)}_{device_name(run)}"

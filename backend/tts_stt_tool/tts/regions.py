"""Map a sheet's region cell (\"Bắc\", \"BAC-HN\", \"Miền Nam\", \"HCM\"…) to the voice chosen for that region."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

REGIONS = ("bac", "trung", "nam")

_TOKENS = {
    "bac": {"bac", "hn", "hanoi", "north", "northern"},
    "trung": {"trung", "hue", "dn", "danang", "central"},
    "nam": {"nam", "hcm", "tphcm", "sg", "saigon", "south", "southern"},
}
_PHRASES = {"bac": ("ha noi",), "trung": ("da nang",), "nam": ("sai gon", "ho chi minh")}


def _fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def region_key(region: str | None) -> str | None:
    """``"bac" | "trung" | "nam"`` for a recognised region cell, else None."""
    if not region:
        return None
    folded = _fold(region)
    tokens = set(re.findall(r"[a-z0-9]+", folded))
    joined = " ".join(re.findall(r"[a-z0-9]+", folded))
    for key in REGIONS:
        if tokens & _TOKENS[key] or any(p in joined for p in _PHRASES[key]):
            return key
    return None


def voice_for(region: str | None, source: Any) -> str:
    """Voice for a row: the region's voice, else the Bắc/default voice (``source.voice`` or ``source["voice"]``)."""
    get = source.get if isinstance(source, dict) else lambda k: getattr(source, k, None)
    default = get("voice") or ""
    key = region_key(region)
    if key is None or key == "bac":
        return default
    return get(f"voice_{key}") or default


def voices_label(source: Any) -> str:
    """\"Bắc: A · Trung: B · Nam: C\" for reports (a region without its own voice shows the Bắc voice)."""
    return " · ".join(f"{name}: {voice_for(name, source) or 'mặc định'}" for name in ("Bắc", "Trung", "Nam"))

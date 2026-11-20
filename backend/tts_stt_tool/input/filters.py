"""Decide which input rows become spoken test sentences."""

from __future__ import annotations

import re
import unicodedata

from tts_stt_tool.compare.normalize import normalize
from tts_stt_tool.models import InputItem

REASON_SYSTEM = "Dòng hệ thống"
REASON_EMPTY = "Ô trống"
REASON_ANNOTATION = "Chú thích trong ngoặc"
REASON_UNREADABLE = "Ký tự không đọc được"
REASON_WAKE_ONLY = "Chỉ có từ đánh thức"

_WAKE = re.compile(r"^\s*hey\s+vi(?:ta)?\b\s*[,.!:]?\s*", re.IGNORECASE)
_UNREADABLE = re.compile(r"[<>{}\[\]…→|#]")
_SYSTEM_MARK = "Hệ thống"


def strip_wake_word(text: str) -> str:
    """Remove a leading "Hey Vita" / "Hey Vi" (and its punctuation)."""
    return _WAKE.sub("", text, count=1)


def clean_text(text: str) -> str:
    """NFC (TTS needs composed tones), collapse whitespace incl. line breaks, trim."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def has_words(text: str) -> bool:
    """True when the text still has something to say after scoring normalization."""
    return bool(normalize(text))


def classify(item: InputItem) -> tuple[str | None, str | None]:
    """Return ``(text_tts, None)`` for a speakable row or ``(None, reason)``."""
    if _SYSTEM_MARK in item.speaker:
        return None, REASON_SYSTEM
    text = clean_text(item.text_raw)
    if not text:
        return None, REASON_EMPTY
    if "(" in text or ")" in text:
        return None, REASON_ANNOTATION
    if _UNREADABLE.search(text):
        return None, REASON_UNREADABLE
    spoken = clean_text(strip_wake_word(text))
    if not has_words(spoken):
        # Nothing to say: either only the wake word, or only symbols/emoji ("-", "👍").
        return None, REASON_WAKE_ONLY if spoken != text else REASON_UNREADABLE
    return spoken, None

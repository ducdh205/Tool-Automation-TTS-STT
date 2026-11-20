"""Normalize Vietnamese text before WER/CER scoring.

One function for Block 1 and Block 2 so both blocks score the same way.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from tts_stt_tool.compare.vi_numbers import DIGITS, number_to_words

_TENS_DIGITS = set(DIGITS[2:])  # "hai".."chín" can start a short-form tens number

RULES_PATH = Path(__file__).with_name("rules.json")

_TONES = "̣̀́̃̉"  # huyền, sắc, ngã, hỏi, nặng
# Two tone-placement conventions exist: "hòa / khỏe / thủy" and "hoà / khoẻ / thuỷ".
# Canonical form: tone on the second vowel ("hoà"), open syllables only
# (the vowel pair ends the word).
_OLD_TONE = re.compile(rf"(o)([{_TONES}])(a|e)(?!\w)|(u)([{_TONES}])(y)(?!\w)")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_THOUSANDS = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")
_DECIMAL = re.compile(r"(\d+),(\d+)")
_PERCENT = re.compile(r"(\d+)\s*%")
_HOUR_MIN = re.compile(r"(\d+)\s*h\s*(\d+)\b")
_HOUR = re.compile(r"(\d+)\s*h\b")
_NUMBER = re.compile(r"\d+")
_NON_WORD = re.compile(r"[^\w\s]|_")
_AFTER_TENS = {"mốt": "một", "tư": "bốn", "lăm": "năm", "nhăm": "năm"}
_ALWAYS = {"lẻ": "linh", "ngàn": "nghìn"}


@lru_cache(maxsize=1)
def _equivalents() -> list[tuple[re.Pattern[str], str]]:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    pairs = sorted(data.get("equivalents", {}).items(), key=lambda kv: -len(kv[0]))
    return [(re.compile(rf"(?<!\w){re.escape(k.lower())}(?!\w)"), v.lower()) for k, v in pairs]


def _fix_old_tones(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group(1):
            return m.group(1) + m.group(3) + m.group(2)
        return m.group(4) + m.group(6) + m.group(5)

    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize("NFC", _OLD_TONE.sub(repl, decomposed))


def _number_words(m: re.Match[str]) -> str:
    digits = m.group(0)
    if len(digits) > 9 or (len(digits) > 1 and digits[0] == "0"):
        # phone numbers, codes, leading zeros: read digit by digit
        return " " + " ".join(DIGITS[int(d)] for d in digits) + " "
    return f" {number_to_words(int(digits))} "


def _fold_number_variants(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for tok in tokens:
        prev = out[-1] if out else ""
        if tok in _AFTER_TENS:
            if prev in ("mươi", "mười"):
                tok = _AFTER_TENS[tok]
            elif prev in _TENS_DIGITS:  # short form "hai mốt" = "hai mươi mốt"
                out.append("mươi")
                tok = _AFTER_TENS[tok]
        out.append(_ALWAYS.get(tok, tok))
    return out


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFC", text).lower()
    s = _fix_old_tones(s)
    for pattern, value in _equivalents():
        s = pattern.sub(value, s)
    s = _CLOCK.sub(r"\1 giờ \2", s)
    s = _THOUSANDS.sub(lambda m: m.group(0).replace(".", ""), s)
    s = _DECIMAL.sub(r"\1 phẩy \2", s)
    s = _PERCENT.sub(r"\1 phần trăm", s)
    s = _HOUR_MIN.sub(r"\1 giờ \2", s)
    s = _HOUR.sub(r"\1 giờ", s)
    s = _NUMBER.sub(_number_words, s)
    s = _NON_WORD.sub(" ", s)
    return " ".join(_fold_number_variants(s.split()))

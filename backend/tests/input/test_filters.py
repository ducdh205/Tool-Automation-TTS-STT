import pytest

from tts_stt_tool.input.filters import (
    REASON_ANNOTATION,
    REASON_EMPTY,
    REASON_SYSTEM,
    REASON_UNREADABLE,
    REASON_WAKE_ONLY,
    classify,
    strip_wake_word,
)
from tts_stt_tool.models import InputItem


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hey Vita, bật ionizer nhé", "bật ionizer nhé"),
        ("hey vi bật ionizer", "bật ionizer"),
        ("HEY VITA: tắt đèn", "tắt đèn"),
        ("Bật ionizer", "Bật ionizer"),
        ("Heyy Vita bật", "Heyy Vita bật"),
        ("Hey Vitamin", "Hey Vitamin"),
    ],
)
def test_strip_wake_word(raw, expected):
    assert strip_wake_word(raw) == expected


def _item(speaker, text):
    return InputItem(sheet="s", tc_id="TC-1", turn="1", feature="f", priority="P1", region="BAC-HN",
                     speaker=speaker, text_raw=text, expected="", source_row=5)


USER = "👤 Người dùng"


@pytest.mark.parametrize(
    ("speaker", "text", "reason"),
    [
        ("🚗 Hệ thống (sự kiện)", "Xe chuyển số D", REASON_SYSTEM),
        (USER, "   ", REASON_EMPTY),
        (USER, "", REASON_EMPTY),
        (USER, "(không nói gì, chờ quá 8 giây)", REASON_ANNOTATION),
        (USER, "Mở cổng sạc (lặp 20 lần với 20 cách nói khác nhau)", REASON_ANNOTATION),
        (USER, "Bật ionizer <script>alert(1)</script>", REASON_ANNOTATION),
        (USER, "Bật ionizer <script>", REASON_UNREADABLE),
        (USER, "Mở gương ra đi (nói lần 1) … Mở gương", REASON_ANNOTATION),
        (USER, "Mở gương ra đi … Mở gương", REASON_UNREADABLE),
        (USER, "Phát lại toàn bộ câu nói TC-SYN-001 → TC-SYN-079", REASON_UNREADABLE),
        (USER, "Hey Vita", REASON_WAKE_ONLY),
        (USER, "Hey Vita, ", REASON_WAKE_ONLY),
    ],
)
def test_classify_skips(speaker, text, reason):
    text_tts, skip = classify(_item(speaker, text))
    assert text_tts is None
    assert skip == reason


@pytest.mark.parametrize(
    ("speaker", "text", "expected"),
    [
        ("👤 Người dùng (nữ, giọng Hà Nội, nói nhanh)", "Hey Vita, tắt ionizer đi", "tắt ionizer đi"),
        (USER, "  Bật điều hoà\r\n", "Bật điều hoà"),
        ("👤 Trẻ em", "Mở cửa kính 30%", "Mở cửa kính 30%"),
    ],
)
def test_classify_keeps(speaker, text, expected):
    assert classify(_item(speaker, text)) == (expected, None)

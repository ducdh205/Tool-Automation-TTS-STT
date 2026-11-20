import unicodedata

import pytest

from tts_stt_tool.compare.normalize import normalize


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Chỉnh nhiệt độ ghế lái lên 24 độ", "chỉnh nhiệt độ ghế lái lên hai mươi tư độ"),
        ("Mở cửa kính 30%", "mở cửa kính ba mươi phần trăm"),
        ("Mở cửa kính 30 phần trăm", "Mở cửa kính ba mươi phần trăm."),
        ("Họp lúc 9h", "họp lúc chín giờ"),
        ("Đặt 21 độ", "đặt hai mươi mốt độ"),
        ("Đặt 25 độ", "đặt hai mươi lăm độ"),
        ("Đặt 15 độ", "đặt mười lăm độ"),
        ("một trăm lẻ năm", "105"),
        ("hai ngàn", "2000"),
        ("Bật  điều hoà\r\n", "bật điều hòa"),
        (unicodedata.normalize("NFD", "Bật điều hòa"), "Bật điều hòa"),
        ("SĐT của anh", "số điện thoại của anh"),
        ("Hey Vita, bật đèn!", "hey vita bật đèn"),
        ("thuỷ", "thủy"),
    ],
)
def test_equivalent(a, b):
    assert normalize(a) == normalize(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("mua sữa", "mua sửa"),
        ("bật đèn", "tắt đèn"),
        ("năm mươi", "lăm mươi"),
    ],
)
def test_not_equivalent(a, b):
    assert normalize(a) != normalize(b)


def test_output_is_lowercase_single_spaced():
    assert normalize("  Bật,   ĐÈN  trần.  ") == "bật đèn trần"


# --- final review fixes (review #5) ------------------------------------------
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1.000 người", "một nghìn người"),
        ("2.500.000 đồng", "hai triệu năm trăm nghìn đồng"),
        ("3,5 độ", "ba phẩy năm độ"),
        ("9:30", "chín giờ ba mươi"),
        ("0912345678", "không chín một hai ba bốn năm sáu bảy tám"),
        ("gọi 0912", "gọi không chín một hai"),
        ("hai mốt độ", "21 độ"),
        ("hai tư độ", "24 độ"),
        ("hai lăm độ", "25 độ"),
    ],
)
def test_more_number_forms(a, b):
    assert normalize(a) == normalize(b)


def test_digit_by_digit_is_space_padded():
    assert normalize("abc0912").split()[-4:] == ["không", "chín", "một", "hai"]

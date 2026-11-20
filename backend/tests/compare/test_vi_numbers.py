import pytest

from tts_stt_tool.compare.vi_numbers import number_to_words


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "không"),
        (5, "năm"),
        (10, "mười"),
        (15, "mười năm"),
        (21, "hai mươi một"),
        (24, "hai mươi bốn"),
        (25, "hai mươi năm"),
        (30, "ba mươi"),
        (100, "một trăm"),
        (105, "một trăm linh năm"),
        (110, "một trăm mười"),
        (1000, "một nghìn"),
        (1005, "một nghìn không trăm linh năm"),
        (2024, "hai nghìn không trăm hai mươi bốn"),
        (15000, "mười năm nghìn"),
        (1000000, "một triệu"),
        (1200300, "một triệu hai trăm nghìn ba trăm"),
    ],
)
def test_number_to_words(n, words):
    assert number_to_words(n) == words


def test_out_of_range():
    with pytest.raises(ValueError):
        number_to_words(10**9)
    with pytest.raises(ValueError):
        number_to_words(-1)

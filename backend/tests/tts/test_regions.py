import pytest

from tts_stt_tool.tts.regions import region_key, voice_for, voices_label


@pytest.mark.parametrize("cell, key", [
    ("Bắc", "bac"), ("BAC-HN", "bac"), ("Miền Bắc", "bac"), ("Hà Nội", "bac"), ("north", "bac"),
    ("Trung", "trung"), ("MIỀN TRUNG", "trung"), ("Huế", "trung"), ("Đà Nẵng", "trung"),
    ("Nam", "nam"), ("NAM-HCM", "nam"), ("Sài Gòn", "nam"), ("TP.HCM", "nam"),
    ("", None), (None, None), ("khác", None),
])
def test_region_key(cell, key):
    assert region_key(cell) == key


def test_voice_for_falls_back_to_the_bac_voice():
    src = {"voice": "A", "voice_trung": None, "voice_nam": "C"}
    assert voice_for("Trung", src) == "A"
    assert voice_for("Nam", src) == "C"
    assert voices_label(src) == "Bắc: A · Trung: A · Nam: C"

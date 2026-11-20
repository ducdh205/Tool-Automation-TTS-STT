import pytest

from backend.tests.helpers import FORM_SHEET, SAMPLE_XLSX
from tts_stt_tool.input.testcase_form import (
    InputError,
    is_testcase_form,
    list_sheets,
    read_testcase_items,
)


def test_list_sheets_marks_only_form_sheets_with_data(mini_form):
    infos = {s.name: s for s in list_sheets(mini_form)}
    assert infos[FORM_SHEET].is_testcase
    assert infos[FORM_SHEET].item_count == 3
    assert not infos["Tổng hợp"].is_testcase
    assert infos["Hướng dẫn"].item_count == 0


def test_is_testcase_form(mini_form):
    assert is_testcase_form(mini_form, FORM_SHEET)
    assert not is_testcase_form(mini_form, "Tổng hợp")


def test_read_items_maps_columns_and_keeps_turn(mini_form):
    items = read_testcase_items(mini_form, [FORM_SHEET])
    assert [(i.tc_id, i.turn, i.text_raw) for i in items] == [
        ("TC-SYN-001", "1", "Đồng bộ nhiệt độ tất cả các vùng"),
        ("TC-DLG-001", "2", "Bật"),
        ("TC-SYN-002", "1", ""),
    ]
    first = items[0]
    assert first.source_row == 5
    assert first.region == "BAC-HN"
    assert first.sheet == FORM_SHEET
    assert first.feature == "Climate Sync"
    assert first.priority == "P0 - Smoke"
    assert first.speaker == "👤 Người dùng"
    assert first.expected == "expected"


def test_missing_file_raises_input_error(tmp_path):
    with pytest.raises(InputError):
        list_sheets(tmp_path / "nope.xlsx")


@pytest.mark.sample
@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="sample file missing")
def test_sample_file_has_3986_items():
    sheets = [s.name for s in list_sheets(SAMPLE_XLSX) if s.is_testcase and s.item_count > 0]
    assert len(sheets) == 14
    assert len(read_testcase_items(SAMPLE_XLSX, sheets)) == 3986

import openpyxl
import pytest

from backend.tests.helpers import FORM_SHEET, HEADER
from tts_stt_tool.input.generic import (
    DEFAULT_SPEAKER,
    ColumnMapping,
    header_labels,
    preview_sheet,
    read_items,
    sheet_names,
    suggest_mapping,
)
from tts_stt_tool.input.testcase_form import InputError

FORM_MAPPING = ColumnMapping(
    text_col="Câu nói (utterance)", header_row=4, id_col="TC_ID", region_col="Vùng miền",
    expected_col="Kết quả mong đợi", turn_col="Bước / Lượt",
)


def test_read_csv_with_mapping(tmp_path):
    p = tmp_path / "cau_lenh.csv"
    p.write_text("id,cau\n1,Bật điều hòa\n2,\n", encoding="utf-8-sig")
    items = read_items(p, [], ColumnMapping(text_col="cau", id_col="id"))
    assert [(i.tc_id, i.text_raw) for i in items] == [("1", "Bật điều hòa"), ("2", "")]
    assert items[0].sheet == "cau_lenh"
    assert items[0].speaker == DEFAULT_SPEAKER
    assert items[0].turn == "1"
    assert items[0].source_row == 2


def test_csv_without_id_uses_row_number(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("text\nTắt đèn\n", encoding="utf-8")
    items = read_items(p, [], ColumnMapping(text_col="text"))
    assert items[0].tc_id == "2"


def test_xlsx_generic_and_preview(tmp_path):
    p = tmp_path / "b.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lệnh"
    ws.append(["Mã", "Câu"])
    ws.append(["L1", "Mở cốp"])
    wb.save(p)
    assert preview_sheet(p, "Lệnh", 1).columns == ["Mã", "Câu"]
    items = read_items(p, ["Lệnh"], ColumnMapping(text_col="Câu", id_col="Mã"))
    assert [(i.sheet, i.tc_id, i.text_raw) for i in items] == [("Lệnh", "L1", "Mở cốp")]


def test_preview_csv(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("x,y\n1,2\n", encoding="utf-8")
    assert preview_sheet(p, None, 1).columns == ["x", "y"]


def test_sheet_names(mini_form):
    assert sheet_names(mini_form) == ["Tổng hợp", "Hướng dẫn", FORM_SHEET]


def test_header_labels():
    assert header_labels(["Mã", "", "Câu", "Câu", "", ""]) == ["Mã", "Cột B", "Câu", "Câu (2)"]


def test_suggest_mapping_on_form_headers():
    assert suggest_mapping(HEADER) == {
        "text_col": "Câu nói (utterance)", "id_col": "TC_ID", "region_col": "Vùng miền",
        "expected_col": "Kết quả mong đợi", "turn_col": "Bước / Lượt",
    }


def test_preview_sheet_header_row_4(mini_form):
    p = preview_sheet(mini_form, FORM_SHEET, 4)
    assert p.columns[:2] == ["TC_ID", "Cụm tính năng"]
    assert p.row_count == 4 and len(p.rows) == 4
    assert p.rows[1][8] == "2"
    assert p.suggestions["text_col"] == "Câu nói (utterance)"


def test_preview_limit(tmp_path):
    p = tmp_path / "many.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["cau"])
    for i in range(25):
        wb.active.append([f"c{i}"])
    wb.save(p)
    pv = preview_sheet(p, None, 1)
    assert len(pv.rows) == 20 and pv.row_count == 25


def test_preview_header_row_out_of_range(mini_form):
    with pytest.raises(InputError, match="không có dòng 99"):
        preview_sheet(mini_form, FORM_SHEET, 99)


def test_form_header_keeps_form_cells(mini_form):
    items = read_items(mini_form, [FORM_SHEET], FORM_MAPPING)
    assert [(i.tc_id, i.turn, i.text_raw) for i in items] == [
        ("TC-SYN-001", "1", "Đồng bộ nhiệt độ tất cả các vùng"),
        ("TC-DLG-001", "2", "Bật"),
        ("TC-SYN-002", "1", ""),
    ]
    first = items[0]
    assert (first.source_row, first.region, first.expected, first.feature, first.priority) == (
        5, "BAC-HN", "expected", "Climate Sync", "P0 - Smoke")
    assert first.speaker == DEFAULT_SPEAKER
    assert len(first.form) == 36 and first.form[2] == "UC" and first.form[35] == ""


def test_blank_id_rows_skipped_when_id_mapped(mini_form):
    assert len(read_items(mini_form, [FORM_SHEET], FORM_MAPPING)) == 3
    no_id = ColumnMapping(text_col="Câu nói (utterance)", header_row=4)
    assert len(read_items(mini_form, [FORM_SHEET], no_id)) == 4


def test_region_value_and_defaults(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("cau\nBật đèn\n", encoding="utf-8")
    i = read_items(p, [], ColumnMapping(text_col="cau", region_value="NAM-HCM"))[0]
    assert (i.region, i.turn, i.tc_id, i.expected, i.form, i.speaker) == ("NAM-HCM", "1", "2", "", [], DEFAULT_SPEAKER)


def test_multiple_sheets_and_missing_column(tmp_path):
    p = tmp_path / "m.xlsx"
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "A"
    a.append(["Mã", "Câu"]); a.append(["1", "x"])
    b = wb.create_sheet("B")
    b.append(["Mã", "Câu"]); b.append(["2", "y"])
    c = wb.create_sheet("C")
    c.append(["Mã", "Lệnh"]); c.append(["3", "z"])
    wb.save(p)
    m = ColumnMapping(text_col="Câu", id_col="Mã")
    assert [i.sheet for i in read_items(p, ["A", "B"], m)] == ["A", "B"]
    with pytest.raises(InputError, match="Sheet 'C' không có cột 'Câu'"):
        read_items(p, ["A", "C"], m)


def test_csv_header_row_2(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("ghi chú\nid,cau\n1,Mở cốp\n", encoding="utf-8")
    items = read_items(p, [], ColumnMapping(text_col="cau", id_col="id", header_row=2))
    assert len(items) == 1 and items[0].source_row == 3


def test_header_labels_never_collide():
    assert len(set(header_labels(["X", "X", "X (2)"]))) == 3
    labels = header_labels(["a", "Cột A", "", "Cột C"])
    assert len(set(labels)) == len(labels)


def test_suggest_mapping_ignores_loose_matches():
    s = suggest_mapping(["Use case / Req ID", "Các bước thực hiện", "Câu nói (utterance)"])
    assert "id_col" not in s and "turn_col" not in s
    assert s["text_col"] == "Câu nói (utterance)"

from pathlib import Path

import openpyxl

from tts_stt_tool.report.result_export import (
    OVERVIEW_SHEET,
    RESULT_HEADERS,
    build_result_report,
    result_suffix,
    result_values,
)
from tts_stt_tool.store.db import AppStatus, Store

from .conftest import HEADER_FILL, SHEET, input_item, make_session, write_source


def build(session, tmp_path):
    out = build_result_report(session.store, session.run_id, tmp_path / "out" / "kq.xlsx")
    return openpyxl.load_workbook(out)


def test_result_values(session):
    ok, wrong, broken = (session.by_tc[t] for t in ("TC1", "TC2", "TC3"))
    assert result_values(ok) == ("bật ionizer", "Pass", "WER 0% · CER 0%")
    text, verdict, note = result_values(wrong)
    assert (text, verdict) == ("mở cửa số", "Fail")
    assert note.startswith("WER ") and " · CER " in note and "sai: sổ→số" in note
    assert result_values(broken) == ("", "Lỗi thao tác: Mic không bật", "")
    assert result_values({**ok, "status": AppStatus.PENDING.value}) == ("", "", "")
    assert result_values({**ok, "app_text": None})[0] == "(app không trả câu)"


def test_note_names_the_spoken_text_when_it_differs(session):
    r = {**session.by_tc["TC1"], "text_raw": "Hey Vita, bật ionizer", "text_tts": "bật ionizer"}
    assert result_values(r)[2].endswith(" · câu đã đọc: bật ionizer")


def test_keeps_source_format(tmp_path, session):
    wb = build(session, tmp_path)
    assert wb.sheetnames == [OVERVIEW_SHEET, SHEET]
    ws = wb[SHEET]
    assert "A1:C1" in {str(r) for r in ws.merged_cells.ranges}
    assert ws.column_dimensions["C"].width == 33
    assert [ws[f"{c}4"].value for c in "DEFG"] == RESULT_HEADERS
    assert ws["D4"].font.bold and ws["D4"].fill.fgColor.rgb == HEADER_FILL
    assert ws["D5"].value == "bật ionizer" and ws["E5"].value == "Pass"
    assert ws["E6"].value == "Fail"
    assert ws["E7"].value.startswith("Lỗi thao tác")
    assert [[ws.cell(r, c).value for c in (1, 2, 3)] for r in (5, 6)] == [
        ["TC1", 1, "Bật ionizer"], ["TC2", 1, "Hey Vita, mở cửa sổ"]]
    assert ws.auto_filter.ref == "A4:G8"
    assert ws.column_dimensions["D"].width == 40 and ws.column_dimensions["F"].width == 50


def test_untested_rows_blank(tmp_path, session):
    ws = build(session, tmp_path)[SHEET]
    assert ws["A8"].value == "TC4"
    assert [ws[f"{c}8"].value for c in "DEFG"] == [None, None, None, None]


def test_overview_first(tmp_path, session):
    ws = build(session, tmp_path)[OVERVIEW_SHEET]
    labels = [ws.cell(r, 1).value for r in range(1, ws.max_row + 1)]
    assert labels[0] == "Bộ audio" and "Tỉ lệ đúng của app" in labels


def test_overview_name_clash(tmp_path):
    store = Store(tmp_path / "t.db")
    item = input_item("TC1", "1", "Bật ionizer", 5)
    item.sheet = OVERVIEW_SHEET
    set_id = store.create_audio_set("b", "b.xlsx", [OVERVIEW_SHEET], "v", [item])
    store.set_source(set_id, str(write_source(tmp_path / "s.xlsx", (OVERVIEW_SHEET,))), 4)
    run_id = store.create_app_run(set_id, "S", "Pixel", "p", None)
    wb = openpyxl.load_workbook(build_result_report(store, run_id, tmp_path / "kq.xlsx"))
    assert wb.sheetnames == [f"{OVERVIEW_SHEET} (2)", OVERVIEW_SHEET]
    assert wb[OVERVIEW_SHEET]["A5"].value == "TC1"


def _check_fallback(wb):
    assert wb.sheetnames == [OVERVIEW_SHEET, SHEET]
    ws = wb[SHEET]
    assert [c.value for c in ws[1]] == ["TC_ID", "Lượt", "Vùng miền", "Câu gốc", "Kết quả mong đợi", *RESULT_HEADERS]
    assert [ws.cell(r, 1).value for r in range(2, ws.max_row + 1)] == ["TC1", "TC2", "TC3"]
    assert ws["G3"].value == "Fail"


def test_fallback_without_source(tmp_path):
    s = make_session(tmp_path, source=False)
    _check_fallback(build(s, tmp_path))


def test_fallback_when_file_missing(tmp_path, session):
    Path(session.store.get_audio_set(session.set_id)["source_path"]).unlink()
    _check_fallback(build(session, tmp_path))


def test_result_suffix(tmp_path):
    xlsm = tmp_path / "a.xlsm"
    xlsm.write_bytes(b"x")
    assert result_suffix({"source_path": str(xlsm)}) == ".xlsm"
    assert result_suffix({"source_path": str(tmp_path / "gone.xlsm")}) == ".xlsx"
    assert result_suffix({"source_path": None}) == ".xlsx"


def test_unheaded_columns_are_not_overwritten(tmp_path, session):
    src = Path(session.store.get_audio_set(session.set_id)["source_path"])
    wb = openpyxl.load_workbook(src)
    ws = wb[SHEET]
    ws["D6"] = "ghi chú tay"
    ws["E7"] = "=A7"
    ws.auto_filter.ref = "A4:E8"
    wb.save(src)
    out = build(session, tmp_path)[SHEET]
    assert out["D6"].value == "ghi chú tay" and out["E7"].value == "=A7"
    assert [out[f"{c}4"].value for c in "FGHI"] == RESULT_HEADERS
    assert out["G6"].value == "Fail"
    assert out.auto_filter.ref == "A4:I8"


def test_only_overview_tab_selected(tmp_path, session):
    wb = build(session, tmp_path)
    assert [bool(ws.sheet_view.tabSelected) for ws in wb.worksheets] == [True, False]


def _source_with_lookups(session):
    """Kept sheet uses: a formula on 'Danh mục', a dropdown via the name ListTT on 'Tra cứu'; 'Rác' is unused."""
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    src = Path(session.store.get_audio_set(session.set_id)["source_path"])
    wb = openpyxl.load_workbook(src)
    wb.create_sheet("Danh mục")["A1"] = "x"
    wb.create_sheet("Tra cứu")["A1"] = "Pass"
    wb.create_sheet("Rác")["A1"] = "y"
    wb.defined_names["ListTT"] = DefinedName("ListTT", attr_text="'Tra cứu'!$A$1:$A$2")
    ws = wb[SHEET]
    ws["C9"] = "='Danh mục'!A1"
    dv = DataValidation(type="list", formula1="=ListTT")
    dv.add("B5:B8")
    ws.add_data_validation(dv)
    wb.save(src)


def test_referenced_unselected_sheets_kept_hidden(tmp_path, session):
    _source_with_lookups(session)
    wb = build(session, tmp_path)
    assert wb.sheetnames == [OVERVIEW_SHEET, SHEET, "Danh mục", "Tra cứu"]
    assert [wb[s].sheet_state for s in wb.sheetnames] == ["visible", "visible", "hidden", "hidden"]
    assert wb[SHEET]["C9"].value == "='Danh mục'!A1"


def _real_png(path, size=(1080, 2400)):
    from PIL import Image

    Image.new("RGB", size, (200, 30, 30)).save(path)


def _images_by_cell(ws):
    return {f"{chr(65 + img.anchor._from.col)}{img.anchor._from.row + 1}": img for img in ws._images}


def test_screenshot_embedded_for_fail_and_op_error(tmp_path, session):
    for tc in ("TC2", "TC3"):
        _real_png(session.by_tc[tc]["screenshot_path"])
    ws = build(session, tmp_path)[SHEET]
    assert ws["G4"].value == "Ảnh màn hình"
    images = _images_by_cell(ws)
    assert set(images) == {"G6", "G7"}
    assert images["G6"].height == 240 and images["G6"].width == 108
    assert ws.row_dimensions[6].height >= 180
    assert ws.row_dimensions[5].height is None  # Pass row keeps its height
    assert ws.column_dimensions["G"].width == 22


def test_screenshot_missing_or_unreadable(tmp_path, session):
    Path(session.by_tc["TC3"]["screenshot_path"]).unlink()  # TC2's file is not a real PNG
    ws = build(session, tmp_path)[SHEET]
    assert not ws._images
    assert ws["G6"].value == ws["G7"].value == "(không tìm thấy ảnh)"
    assert ws["G5"].value is None


def test_screenshot_in_plain_sheet(tmp_path):
    s = make_session(tmp_path, source=False)
    _real_png(s.by_tc["TC2"]["screenshot_path"])
    ws = build(s, tmp_path)[SHEET]
    assert set(_images_by_cell(ws)) == {"I3"}

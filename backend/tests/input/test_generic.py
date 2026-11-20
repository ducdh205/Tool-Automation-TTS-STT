import openpyxl

from tts_stt_tool.input.generic import ColumnMapping, preview_columns, read_generic


def test_read_csv_with_mapping(tmp_path):
    p = tmp_path / "cau_lenh.csv"
    p.write_text("id,cau\n1,Bật điều hòa\n2,\n", encoding="utf-8-sig")
    items = read_generic(p, None, ColumnMapping(text_col="cau", id_col="id"))
    assert [(i.tc_id, i.text_raw) for i in items] == [("1", "Bật điều hòa"), ("2", "")]
    assert items[0].sheet == "cau_lenh"
    assert items[0].speaker == "👤 Người dùng"
    assert items[0].turn == "1"
    assert items[0].source_row == 2


def test_csv_without_id_uses_row_number(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("text\nTắt đèn\n", encoding="utf-8")
    items = read_generic(p, None, ColumnMapping(text_col="text", id_col=None))
    assert items[0].tc_id == "2"


def test_xlsx_generic_and_preview(tmp_path):
    p = tmp_path / "b.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lệnh"
    ws.append(["Mã", "Câu"])
    ws.append(["L1", "Mở cốp"])
    wb.save(p)
    assert preview_columns(p, "Lệnh", 1) == ["Mã", "Câu"]
    items = read_generic(p, "Lệnh", ColumnMapping(text_col="Câu", id_col="Mã"))
    assert [(i.sheet, i.tc_id, i.text_raw) for i in items] == [("Lệnh", "L1", "Mở cốp")]


def test_preview_csv(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("x,y\n1,2\n", encoding="utf-8")
    assert preview_columns(p, None, 1) == ["x", "y"]

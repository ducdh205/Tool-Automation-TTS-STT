import csv

import openpyxl
import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.models import InputItem
from tts_stt_tool.report.excel import (
    DETAIL_HEADERS,
    SHEET_ERRORS,
    SHEET_FAILED,
    SHEET_OVERVIEW,
    SHEET_SKIPPED,
    SHEET_VERIFY,
    build_block1_report,
    export_block1_csv,
    format_ops,
)
from tts_stt_tool.store.db import ItemStatus, Store


def _item(i, text, sheet):
    return InputItem(sheet=sheet, tc_id=f"TC-{i}", turn="1", feature="Climate", priority="P1",
                     region="BAC-HN", speaker="👤 Người dùng", text_raw=text, expected="", source_row=5 + i)


@pytest.fixture
def populated(tmp_path):
    store = Store(tmp_path / "t.db")
    texts = [f"câu số {i}" for i in range(9)] + ["(không nói gì)"]
    items = [_item(i, t, "Sheet A" if i < 5 else "Sheet B") for i, t in enumerate(texts)]
    set_id = store.create_audio_set("bộ test", "DieuKhienXe_Pre.xlsx", ["Sheet A", "Sheet B"], "Ngọc Huyền", items)
    rows = store.get_items(set_id, ItemStatus.PENDING)
    for n, row in enumerate(rows):
        store.record_generated(row["id"], f"{n}.wav", 1)
        if n < 7:
            store.record_verify(row["id"], row["text_tts"], compare(row["text_tts"], row["text_tts"]), ItemStatus.PASSED)
        else:
            store.record_verify(row["id"], "sai rồi", compare(row["text_tts"], "sai rồi"), ItemStatus.AUDIO_FAILED)
    return store, set_id, Settings(data_dir=tmp_path)


def find_value(ws, label):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == label:
                return ws.cell(row=cell.row, column=cell.column + 1)
    raise AssertionError(f"label not found: {label}")


def test_report_sheets_and_overview(populated, tmp_path):
    store, set_id, settings = populated
    out = build_block1_report(store, set_id, settings, tmp_path / "r.xlsx")
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == [SHEET_OVERVIEW, SHEET_VERIFY, SHEET_FAILED, SHEET_SKIPPED, SHEET_ERRORS]
    ov = wb[SHEET_OVERVIEW]
    reject = find_value(ov, "Tỉ lệ audio bị loại")
    assert reject.value == pytest.approx(2 / 9)
    assert reject.fill.fgColor.rgb.endswith("FFC7CE")
    assert find_value(ov, "Giọng").value == "Bắc: Ngọc Huyền · Trung: Ngọc Huyền · Nam: Ngọc Huyền"
    assert find_value(ov, "Đạt").value == 7


def test_overview_no_warning_under_threshold(tmp_path):
    store = Store(tmp_path / "t.db")
    set_id = store.create_audio_set("b", "f.xlsx", ["S"], "v", [_item(0, "bật đèn", "S")])
    row = store.get_items(set_id)[0]
    store.record_verify(row["id"], "bật đèn", compare("bật đèn", "bật đèn"), ItemStatus.PASSED)
    out = build_block1_report(store, set_id, Settings(data_dir=tmp_path), tmp_path / "r.xlsx")
    cell = find_value(openpyxl.load_workbook(out)[SHEET_OVERVIEW], "Tỉ lệ audio bị loại")
    assert cell.value == 0
    assert not cell.fill.fgColor.rgb.endswith("FFC7CE")


def test_detail_sheets(populated, tmp_path):
    store, set_id, settings = populated
    wb = openpyxl.load_workbook(build_block1_report(store, set_id, settings, tmp_path / "r.xlsx"))
    verify = wb[SHEET_VERIFY]
    assert [c.value for c in verify[1]] == DETAIL_HEADERS
    assert verify.max_row == 1 + 9
    assert wb[SHEET_FAILED].max_row == 1 + 2
    skipped = wb[SHEET_SKIPPED]
    assert skipped.max_row == 2
    assert "Chú thích trong ngoặc" in [c.value for c in skipped[2]]
    assert verify.freeze_panes == "A2"


def test_per_sheet_breakdown(populated, tmp_path):
    store, set_id, settings = populated
    ov = openpyxl.load_workbook(build_block1_report(store, set_id, settings, tmp_path / "r.xlsx"))[SHEET_OVERVIEW]
    labels = [c.value for c in ov["A"]]
    assert "Sheet A" in labels
    assert "Sheet B" in labels


def test_csv_export(populated, tmp_path):
    store, set_id, _ = populated
    out = export_block1_csv(store, set_id, tmp_path / "r.csv")
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == DETAIL_HEADERS
    assert len(rows) == 1 + 9


def test_format_ops():
    ops = compare("mua sữa tươi", "mua sửa").ops
    assert format_ops([o.__dict__ for o in ops]) in ("sữa→sửa; -tươi", "-sữa; tươi→sửa")
    assert format_ops([]) == ""
